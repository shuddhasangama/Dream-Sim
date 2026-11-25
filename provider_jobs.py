"""Background provider jobs (perf-worker).

Slow third-party calls run in bgv_worker.py instead of inside a member's
request. A request records the job (and its own state, e.g. a DigiLocker
session in 'creating') and returns at once; the app keeps showing progress by
polling the existing screen or GET /api/v1/jobs/<id>.

- enqueue(): idempotent on idempotency_key. A retried request never creates a
  second job, so a provider call is never made (or charged) twice by retries.
- claim(): FOR UPDATE SKIP LOCKED with a lease. Two workers never take the same
  job; a job whose worker died is requeued (or dead-lettered) when its lease ends.
- finish(): success, or retry with exponential backoff until max_attempts, then
  'dead' (the kind's on_dead hook leaves the member a clear state).
Only references (ids) are stored, never personal data: handlers read the
already-encrypted source rows.
"""
from __future__ import annotations

import logging
import time
import uuid

import auth_sessions
import db

sql = auth_sessions.sql
log = logging.getLogger('dhashu.provider_jobs')

# kind -> {'run': fn(conn, job) -> None, 'on_dead': fn(conn, job) -> None, 'max_attempts': int, 'lease': seconds}
HANDLERS: dict = {}


def register_kind(kind, run, on_dead=None, max_attempts=3, lease=60):
    HANDLERS[kind] = {'run': run, 'on_dead': on_dead, 'max_attempts': max_attempts, 'lease': lease}


def backoff(attempts: int) -> int:
    return min(300, 5 * 2 ** max(0, attempts - 1))


def now() -> int:
    return int(time.time())


def enqueue(conn, kind, user_id, ref, key):
    """Inside the caller's transaction. Returns the (new or existing) job id."""
    spec = HANDLERS.get(kind)
    if spec is None:
        raise ValueError('Unknown job kind')
    existing = sql(conn, 'SELECT id FROM "ProviderJob" WHERE idempotency_key = ?', (key,)).fetchone()
    if existing:
        return existing['id']
    job_id, t = uuid.uuid4().hex, now()
    sql(conn, '''INSERT INTO "ProviderJob" (id,kind,user_id,ref,idempotency_key,state,attempts,max_attempts,run_after,created_at,updated_at)
                 VALUES (?,?,?,?,?,'queued',0,?,?,?,?) ON CONFLICT (idempotency_key) DO NOTHING''',
        (job_id, kind, user_id, ref, key, spec['max_attempts'], t, t, t))
    return sql(conn, 'SELECT id FROM "ProviderJob" WHERE idempotency_key = ?', (key,)).fetchone()['id']


def _expire_leases(conn, t):
    for row in sql(conn, 'SELECT * FROM "ProviderJob" WHERE state = ? AND lease_until < ?', ('running', t)).fetchall():
        row = dict(row)
        if row['attempts'] >= row['max_attempts']:
            sql(conn, 'UPDATE "ProviderJob" SET state=?, last_error=?, updated_at=? WHERE id=?', ('dead', 'lease_expired', t, row['id']))
            _dead(conn, row)
        else:
            sql(conn, 'UPDATE "ProviderJob" SET state=?, run_after=?, last_error=?, updated_at=? WHERE id=?',
                ('queued', t + backoff(row['attempts']), 'lease_expired', t, row['id']))


def _dead(conn, row):
    hook = HANDLERS.get(row['kind'], {}).get('on_dead')
    if hook:
        hook(conn, row)
    log.warning('Provider job dead-lettered: kind=%s job=%s attempts=%s', row['kind'], row['id'], row['attempts'])


def claim(conn, kinds=None):
    """Claim one due job (own transaction). Returns the job dict or None."""
    kinds = sorted(kinds or HANDLERS)
    if not kinds:
        return None
    with auth_sessions.transaction(conn):
        t = now()
        _expire_leases(conn, t)
        marks = ','.join('?' * len(kinds))
        query = (f'SELECT * FROM "ProviderJob" WHERE state = ? AND run_after <= ? AND kind IN ({marks}) '
                 'ORDER BY run_after, id LIMIT 1' + (' FOR UPDATE SKIP LOCKED' if db._is_postgres_connection(conn) else ''))
        row = sql(conn, query, ('queued', t, *kinds)).fetchone()
        if not row:
            return None
        row = dict(row)
        lease = HANDLERS[row['kind']]['lease']
        sql(conn, 'UPDATE "ProviderJob" SET state=?, attempts=attempts+1, lease_until=?, updated_at=? WHERE id=?',
            ('running', t + lease, t, row['id']))
        row.update(state='running', attempts=row['attempts'] + 1, lease_until=t + lease)
    return row


def finish(conn, job, ok, error=None):
    with auth_sessions.transaction(conn):
        t = now()
        if ok:
            sql(conn, 'UPDATE "ProviderJob" SET state=?, lease_until=NULL, last_error=NULL, updated_at=? WHERE id=? AND state=?',
                ('succeeded', t, job['id'], 'running'))
        elif job['attempts'] >= job['max_attempts']:
            sql(conn, 'UPDATE "ProviderJob" SET state=?, lease_until=NULL, last_error=?, updated_at=? WHERE id=? AND state=?',
                ('dead', error, t, job['id'], 'running'))
            _dead(conn, job)
        else:
            sql(conn, 'UPDATE "ProviderJob" SET state=?, run_after=?, lease_until=NULL, last_error=?, updated_at=? WHERE id=? AND state=?',
                ('queued', t + backoff(job['attempts']), error, t, job['id'], 'running'))


def work_one(conn, kinds=None):
    """Worker step: claim one job, run its handler outside any transaction, record the outcome."""
    job = claim(conn, kinds)
    if not job:
        return False
    try:
        HANDLERS[job['kind']]['run'](conn, job)
    except Exception as error:   # noqa: BLE001 — recorded (type only, never provider text) and retried
        finish(conn, job, False, type(error).__name__)
        return True
    finish(conn, job, True)
    return True


def status(conn, job_id, user_id):
    """Owner-only view (no references or errors exposed)."""
    row = db.fetch_one(conn, 'ProviderJob', id=job_id) if isinstance(job_id, str) and len(job_id) <= 64 else None
    if not row or row['user_id'] != user_id:
        return None
    return {'id': row['id'], 'kind': row['kind'], 'state': row['state'],
            'done': row['state'] in ('succeeded', 'failed', 'dead'), 'attempts': row['attempts']}


def register(api, get_db):
    from flask import g, jsonify
    from api_contract import ApiError

    @api.get('/jobs/<job_id>')
    def read_job(job_id):
        value = status(get_db(), job_id, g.api_user['user_id'])
        if value is None:
            raise ApiError('not_found', 'Job not found.', 404)
        return jsonify(value)
