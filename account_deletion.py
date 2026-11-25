"""Account deletion with a grace period, then a permanent purge (feat-delete, feat-purge).

Owner decision: 30-day grace (DHASHU_DELETE_GRACE_DAYS, default 30).

Request (app: Settings -> Delete account; web: /account/delete), confirmed with the
password or a one-time code sent to the member's own phone:
- every session is revoked at once;
- the member is hidden from REACH, weekly matching and discovery immediately
  (hidden_ids), and a partner sees a neutral "No longer available" (named_for);
- one 'account_purge' job is queued for the due date.
Signing in during the grace period shows "scheduled for deletion on <date>" with
Cancel deletion; cancelling restores everything (nothing was removed yet).

Purge (worker, provider_jobs, idempotent): every table is scanned for the member id.
- Rows that are only the member's are deleted (children first, via foreign keys).
- Shared rows (a lock-in, couple or match with another member) are kept for the
  partner's history, re-pointed to an anonymous tombstone id, and the member's side
  of shared text (Debrief reasons and flags, exit feedback, next-level answers, a
  shared contact) is cleared. Shared Guru discussions are deleted.
- Payment records (law) stay with amounts and status only, re-pointed to the tombstone.
- SecurityEvent / MemberLockEvent stay, re-pointed to the tombstone, until the
  retention job removes them (DHASHU_SECURITY_RETENTION_DAYS, default 180).
- One anonymous DeletionRecord keeps the counts. Nothing holds the member id afterwards.
"""
import hashlib
import hmac
import os
import re
import uuid

import auth_sessions as sessions
import db
import provider_jobs

JOB_KIND = 'account_purge'
DAY = 86400

KEEP_FOR_LAW = {'BillingPurchase', 'BillingEntitlement', 'Payment', 'DateCharge'}
KEEP_UNTIL_RETENTION = {'SecurityEvent', 'MemberLockEvent'}
DELETE_WHEN_SHARED = {'GuruDiscussion'}
# The member's side of shared rows: (table, how to find the side, columns per side, cleared value)
SIDE_TEXT = [
    ('DateOutcome', 'dateplan', ('{s}_reason',), None),
    ('DateOutcome', 'dateplan', ('{s}_green_flags_json', '{s}_red_flags_json'), '[]'),
    ('NextLevelThread', 'pair', ('answer_{s}',), None),
    ('Exit', 'couple', ('feedback_{s}_raw',), None),
]


def grace_days():
    try:
        return max(1, min(365, int(os.environ.get('DHASHU_DELETE_GRACE_DAYS', '30'))))
    except ValueError:
        return 30


def retention_days():
    try:
        return max(7, int(os.environ.get('DHASHU_SECURITY_RETENTION_DAYS', '180')))
    except ValueError:
        return 180


# ── status ────────────────────────────────────────────────────────────────

def scheduled(conn, uid):
    row = sessions.sql(conn, 'SELECT deletion_requested_at, deletion_due_at FROM "Account" WHERE user_id = ?', (uid,)).fetchone()
    if row and row['deletion_due_at'] is not None:
        return {'requested_at': int(row['deletion_requested_at']), 'due_at': int(row['deletion_due_at'])}
    return None


def hidden_ids(conn):
    """Members who asked to be deleted: never shown to anyone from the request on."""
    return {r['user_id'] for r in sessions.sql(conn, 'SELECT user_id FROM "Account" WHERE deletion_due_at IS NOT NULL').fetchall()}


# ── request / cancel ──────────────────────────────────────────────────────

def request_deletion(conn, uid):
    with sessions.transaction(conn):
        db.lock_user_rows(conn, uid)
        account = sessions.sql(conn, 'SELECT id, deletion_due_at FROM "Account" WHERE user_id = ?', (uid,)).fetchone()
        if not account:
            raise LookupError('No sign-in account.')
        if account['deletion_due_at'] is not None:
            return scheduled(conn, uid)
        now = sessions.now()
        due = now + grace_days() * DAY
        sessions.sql(conn, 'UPDATE "Account" SET deletion_requested_at = ?, deletion_due_at = ? WHERE id = ?', (now, due, account['id']))
        sessions.sql(conn, 'UPDATE "AuthSession" SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL', (now, uid))
        job = provider_jobs.enqueue(conn, JOB_KIND, uid, 'purge', f'purge:{uid}:{now}')
        sessions.sql(conn, 'UPDATE "ProviderJob" SET run_after = ? WHERE id = ?', (due, job))
        sessions.record_security_event(conn, uid, 'deletion_requested', f'due in {grace_days()} days')
    return {'requested_at': now, 'due_at': due}


def cancel_deletion(conn, uid):
    with sessions.transaction(conn):
        db.lock_user_rows(conn, uid)
        if scheduled(conn, uid) is None:
            return False
        sessions.sql(conn, 'UPDATE "Account" SET deletion_requested_at = NULL, deletion_due_at = NULL WHERE user_id = ?', (uid,))
        sessions.sql(conn, '''UPDATE "ProviderJob" SET state = 'failed', last_error = 'cancelled', updated_at = ?
            WHERE kind = ? AND user_id = ? AND state = 'queued\'''', (sessions.now(), JOB_KIND, uid))
        sessions.record_security_event(conn, uid, 'deletion_cancelled', None)
    return True


# ── schema introspection (SQLite and PostgreSQL) ──────────────────────────

def _columns(conn, table):
    if db._is_postgres_connection(conn):
        return [r['column_name'] for r in conn.execute(
            'SELECT column_name FROM information_schema.columns WHERE table_schema = current_schema() AND table_name = %s '
            'ORDER BY ordinal_position', (table,)).fetchall()]
    return [r[1] for r in conn.execute(f'PRAGMA table_info("{table}")').fetchall()]


def _foreign_keys(conn, table):
    """[(column, parent_table, parent_column)]"""
    if db._is_postgres_connection(conn):
        rows = conn.execute('''SELECT kcu.column_name AS col, ccu.table_name AS parent, ccu.column_name AS pcol
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu ON tc.constraint_name = ccu.constraint_name AND tc.table_schema = ccu.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_schema = current_schema() AND tc.table_name = %s''', (table,)).fetchall()
        return [(r['col'], r['parent'], r['pcol']) for r in rows]
    return [(r[3], r[2], r[4]) for r in conn.execute(f'PRAGMA foreign_key_list("{table}")').fetchall()]


def _primary_key(conn, table):
    if db._is_postgres_connection(conn):
        rows = conn.execute('''SELECT kcu.column_name AS col FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY' AND tc.table_schema = current_schema() AND tc.table_name = %s''', (table,)).fetchall()
        return [r['col'] for r in rows]
    return [r[1] for r in sorted(conn.execute(f'PRAGMA table_info("{table}")').fetchall(), key=lambda r: r[5]) if r[5]]


def _tables(conn):
    return sorted(db.TABLES | {'AdminIdentity', 'AdminSession', 'AdminThrottle', 'AdminAudit'}
                  if _exists(conn, 'AdminAudit') else db.TABLES)


def _exists(conn, table):
    try:
        conn.execute(f'SELECT 1 FROM "{table}" WHERE 1 = 0').fetchall()
        return True
    except Exception:   # noqa: BLE001
        if db._is_postgres_connection(conn):
            conn.rollback()
        return False


class Schema:
    def __init__(self, conn):
        self.conn = conn
        self.tables = [t for t in _tables(conn) if _exists(conn, t)]
        self.columns = {t: _columns(conn, t) for t in self.tables}
        self.fks = {t: _foreign_keys(conn, t) for t in self.tables}
        self.pk = {t: _primary_key(conn, t) or ['id'] for t in self.tables}
        self.user_cols = {t: [c for c, parent, _ in self.fks[t] if parent == 'User'] for t in self.tables}
        self.children = {}
        for t in self.tables:
            for col, parent, pcol in self.fks[t]:
                self.children.setdefault(parent, []).append((t, col, pcol))


def _p(conn):
    return db._placeholder(conn)


def _rows_mentioning(conn, schema, table, uid):
    p = _p(conn)
    cast = lambda c: f'CAST("{c}" AS TEXT)'   # noqa: E731
    pattern = '%' + uid.replace('%', r'\%').replace('_', r'\_') + '%'
    escape = " ESCAPE '\\'"
    where = ' OR '.join(f'{cast(c)} LIKE {p}{escape}' for c in schema.columns[table])
    return [dict(r) for r in conn.execute(f'SELECT * FROM "{table}" WHERE {where}', tuple(pattern for _ in schema.columns[table])).fetchall()]


def _delete(conn, schema, table, row, counts):
    for child, ccol, pcol in schema.children.get(table, []):
        if row.get(pcol) is None:
            continue
        for crow in [dict(r) for r in conn.execute(f'SELECT * FROM "{child}" WHERE "{ccol}" = {_p(conn)}', (row[pcol],)).fetchall()]:
            _delete(conn, schema, child, crow, counts)
    keys = schema.pk[table]
    conn.execute(f'DELETE FROM "{table}" WHERE ' + ' AND '.join(f'"{k}" = {_p(conn)}' for k in keys), tuple(row[k] for k in keys))
    counts['deleted'] += 1


def _anonymise(conn, schema, table, row, uid, tomb, counts):
    changes = {c: (v.replace(uid, tomb) if isinstance(v, str) and uid in v else v) for c, v in row.items()}
    changes = {c: v for c, v in changes.items() if v != row[c]}
    if not changes:
        return
    keys = schema.pk[table]
    sets = ', '.join(f'"{c}" = {_p(conn)}' for c in changes)
    conn.execute(f'UPDATE "{table}" SET {sets} WHERE ' + ' AND '.join(f'"{k}" = {_p(conn)}' for k in keys),
                 (*changes.values(), *(row[k] for k in keys)))
    counts['anonymised'] += 1


def _clear_sides(conn, uid):
    """Before anonymising: clear the member's side of shared text."""
    p = _p(conn)
    sides = []
    for lock in conn.execute(f'SELECT id, user_a, user_b FROM "LockIn" WHERE user_a = {p} OR user_b = {p}', (uid, uid)).fetchall():
        sides.append(('pair', lock['id'], 'a' if lock['user_a'] == uid else 'b'))
        for plan in conn.execute(f'SELECT id FROM "DatePlan" WHERE lockin_id = {p}', (lock['id'],)).fetchall():
            sides.append(('dateplan', plan['id'], 'a' if lock['user_a'] == uid else 'b'))
    for couple in conn.execute(f'SELECT id, partner_a_id FROM "Couple" WHERE partner_a_id = {p} OR partner_b_id = {p}', (uid, uid)).fetchall():
        sides.append(('couple', couple['id'], 'a' if couple['partner_a_id'] == uid else 'b'))
    link = {'pair': 'pair_id', 'dateplan': 'dateplan_id', 'couple': 'couple_id'}
    for table, kind, columns, cleared in SIDE_TEXT:
        for side_kind, ref, side in sides:
            if side_kind == kind:
                sets = ', '.join(f'"{c.format(s=side)}" = {p}' for c in columns)
                column = link[kind]                      # fixed internal names only (SIDE_TEXT), never request data
                conn.execute(f'UPDATE "{table}" SET {sets} WHERE "{column}" = {p}', (*([cleared] * len(columns)), ref))
    conn.execute(f'UPDATE "ContactRequest" SET shared_contact = NULL WHERE requester_id = {p}', (uid,))


def tombstone_id(uid):
    secret = os.environ.get('SECRET_KEY', 'dhashu-local').encode()
    return 'deleted_' + hmac.new(secret, uid.encode(), hashlib.sha256).hexdigest()[:20]


def purge(conn, uid):
    """Permanently remove the member. Idempotent. Returns the anonymous counts, or None."""
    schema = Schema(conn)
    tomb = tombstone_id(uid)
    counts = {'deleted': 0, 'anonymised': 0}
    with sessions.transaction(conn):
        if not sessions.sql(conn, 'SELECT id FROM "User" WHERE id = ?', (uid,)).fetchone():
            return None
        db.lock_user_rows(conn, uid)
        if not sessions.sql(conn, 'SELECT id FROM "User" WHERE id = ?', (tomb,)).fetchone():
            sessions.sql(conn, '''INSERT INTO "User" (id, journey_state, bgv_status, stats_json, vision_json, skills_json, preferences_json)
                VALUES (?, 'exiting', 'declared', '{"deleted": true}', '[]', '{}', '{}')''', (tomb,))
        _clear_sides(conn, uid)
        for table in schema.tables:
            if table == 'User':
                continue
            for row in _rows_mentioning(conn, schema, table, uid):
                user_cells = [row.get(c) for c in schema.user_cols[table]]
                shared = any(v not in (None, uid) and not str(v).startswith('deleted_') for v in user_cells)
                if table in KEEP_FOR_LAW or table in KEEP_UNTIL_RETENTION or table == 'ProviderJob':
                    _anonymise(conn, schema, table, row, uid, tomb, counts)
                elif table in DELETE_WHEN_SHARED or not shared:
                    _delete(conn, schema, table, row, counts)
                else:
                    _anonymise(conn, schema, table, row, uid, tomb, counts)
        user = dict(sessions.sql(conn, 'SELECT * FROM "User" WHERE id = ?', (uid,)).fetchone())
        _delete(conn, schema, 'User', user, counts)
        sessions.sql(conn, 'INSERT INTO "DeletionRecord" (id, purged_at, rows_deleted, rows_anonymised) VALUES (?, ?, ?, ?)',
                     (uuid.uuid4().hex, sessions.now(), counts['deleted'], counts['anonymised']))
    return counts


def apply_retention(conn):
    """Remove SecurityEvent / MemberLockEvent rows older than the retention period."""
    cutoff = sessions.now() - retention_days() * DAY
    with sessions.transaction(conn):
        a = sessions.sql(conn, 'DELETE FROM "SecurityEvent" WHERE created_at < ?', (cutoff,)).rowcount or 0
        b = sessions.sql(conn, 'DELETE FROM "MemberLockEvent" WHERE created_at < ?', (cutoff,)).rowcount or 0
    return a + b


# ── worker job ────────────────────────────────────────────────────────────

def _job_run(conn, job):
    uid = job['user_id']
    if not re.fullmatch(r'[\w\-.:@]{1,200}', uid or '') or uid.startswith('deleted_'):
        return
    state = scheduled(conn, uid)
    conn.commit()
    if state is None or state['due_at'] > sessions.now():
        return                                           # cancelled, or not due yet: nothing to do
    purge(conn, uid)


provider_jobs.register_kind(JOB_KIND, _job_run, max_attempts=5, lease=300)


# ── API (member, owner only) ──────────────────────────────────────────────

def _confirmed(conn, uid, body):
    """Password, or a one-time code sent to the member's own phone. Raises ApiError."""
    from api_contract import ApiError
    from werkzeug.security import check_password_hash
    import auth
    if not sessions.throttle(conn, [auth.key('delete-confirm:' + uid)], 5, 900):
        raise ApiError('rate_limited', 'Please wait 15 minutes before trying again.', 429)
    account = sessions.sql(conn, 'SELECT * FROM "Account" WHERE user_id = ?', (uid,)).fetchone()
    if not account:
        raise ApiError('not_found', 'No sign-in account.', 404)
    if body.get('password') is not None:
        if account['password_hash'] and isinstance(body['password'], str) and check_password_hash(account['password_hash'], body['password']):
            return
        raise ApiError('invalid_credentials', 'That password was not accepted.', 400)
    if body.get('challenge_id') and body.get('code'):
        import auth_delivery
        with sessions.transaction(conn):
            row = sessions.sql(conn, 'SELECT * FROM "AuthChallenge" WHERE id = ? AND account_id = ? AND consumed_at IS NULL AND expires_at > ?',
                               (sessions.digest(str(body['challenge_id'])[:200]), account['id'], sessions.now())).fetchone()
            if row and auth_delivery.check(row['provider_sid'], str(body['code'])[:12]):
                sessions.sql(conn, 'UPDATE "AuthChallenge" SET consumed_at = ? WHERE id = ?', (sessions.now(), row['id']))
                return
        raise ApiError('invalid_code', 'That code was not accepted.', 400)
    raise ApiError('validation_error', 'Confirm with your password or a code.', 400)


def view(conn, uid):
    state = scheduled(conn, uid)
    return {'scheduled': state is not None, 'due_at': state['due_at'] if state else None, 'grace_days': grace_days()}


def register(api, get_db):
    from flask import g, jsonify
    from api_contract import ApiError, json_object
    import auth

    def uid():
        return g.api_user['user_id']

    @api.get('/account/deletion')
    def account_deletion_view():
        return jsonify(view(get_db(), uid()))

    @api.post('/account/deletion/code')
    def account_deletion_code():
        json_object()
        account = sessions.sql(get_db(), 'SELECT phone FROM "Account" WHERE user_id = ?', (uid(),)).fetchone()
        phone = auth.normalize('phone', account['phone'], stored=True) if account and account['phone'] else None
        if not phone:
            raise ApiError('no_phone', 'Use your password to confirm.', 409)
        result, error = auth.start_challenge(get_db(), 'phone', phone, 'mobile')
        if error:
            return error
        return jsonify(challenge_id=result['challenge_id'])

    @api.post('/account/deletion')
    def account_deletion_request():
        body = json_object(optional={'password', 'challenge_id', 'code'})
        _confirmed(get_db(), uid(), body)
        try:
            request_deletion(get_db(), uid())
        except LookupError:
            raise ApiError('not_found', 'No sign-in account.', 404) from None
        return jsonify(view(get_db(), uid()))

    @api.post('/account/deletion/cancel')
    def account_deletion_cancel():
        json_object()
        cancel_deletion(get_db(), uid())
        return jsonify(view(get_db(), uid()))
