"""Opaque, revocable credentials shared by web and mobile authentication.

Uses real UTC epoch time, never the simulation clock. Authentication writes
use one transaction rather than db.insert_row's per-row commits.
"""
from contextlib import contextmanager
import hashlib
import secrets
import time
import uuid

import db

ACCESS_SECONDS = 15 * 60
WEB_SECONDS = 12 * 60 * 60
REFRESH_SECONDS = 7 * 24 * 60 * 60
SESSION_SECONDS = 30 * 24 * 60 * 60


def now():
    return int(time.time())


def digest(token):
    return hashlib.sha256(token.encode('utf-8')).hexdigest()


def valid_token(token):
    return isinstance(token, str) and 32 <= len(token) <= 128 and token.isascii()


def sql(conn, statement, values=()):
    return conn.execute(statement.replace('?', db._placeholder(conn)), values)


@contextmanager
def transaction(conn):
    if db._is_postgres_connection(conn):
        # Existing DB helpers may have opened a read transaction. All callers
        # enter here with no pending writes; own the following commit boundary.
        conn.commit()
        with conn.transaction():
            yield
    else:
        conn.execute('BEGIN IMMEDIATE')
        try:
            yield
            conn.commit()
        except BaseException:
            conn.rollback()
            raise


def issue(conn, user_id, kind='mobile'):
    if kind not in ('mobile', 'web'):
        raise ValueError('Invalid session kind')
    with transaction(conn):
        return issue_in_transaction(conn, user_id, kind)


def issue_in_transaction(conn, user_id, kind='mobile'):
    timestamp = now()
    sid, access = uuid.uuid4().hex, secrets.token_urlsafe(32)
    access_seconds = ACCESS_SECONDS if kind == 'mobile' else WEB_SECONDS
    expires = timestamp + (SESSION_SECONDS if kind == 'mobile' else WEB_SECONDS)
    sql(conn, '''INSERT INTO "AuthSession"
        (id, user_id, access_hash, kind, created_at, access_expires_at, expires_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)''',
        (sid, user_id, digest(access), kind, timestamp, timestamp + access_seconds, expires))
    result = {'access_token': access, 'token_type': 'Bearer', 'expires_in': access_seconds,
              'session_id': sid, 'user_id': user_id}
    if kind == 'mobile':
        refresh = secrets.token_urlsafe(32)
        sql(conn, 'INSERT INTO "AuthRefresh" (id, session_id, expires_at) VALUES (?, ?, ?)',
            (digest(refresh), sid, timestamp + REFRESH_SECONDS))
        result['refresh_token'] = refresh
        result['refresh_expires_in'] = REFRESH_SECONDS
    return result


def authenticate(conn, token, kind='mobile'):
    if not valid_token(token):
        return None
    row = sql(conn, '''SELECT s.* FROM "AuthSession" s JOIN "User" u ON u.id = s.user_id
        JOIN "Account" a ON a.user_id = s.user_id AND a.auth_enabled = 1
        WHERE s.access_hash = ? AND s.kind = ? AND s.revoked_at IS NULL
        AND s.access_expires_at > ? AND s.expires_at > ?''',
        (digest(token), kind, now(), now())).fetchone()
    return dict(row) if row else None


def refresh(conn, token):
    if not valid_token(token):
        return None
    token_hash = digest(token)
    with transaction(conn):
        # Lock the stable session before reading consumed state. Concurrent
        # refresh/revoke operations therefore serialize on both databases.
        old = sql(conn, 'SELECT session_id FROM "AuthRefresh" WHERE id = ?', (token_hash,)).fetchone()
        if not old:
            return None
        suffix = ' FOR UPDATE' if db._is_postgres_connection(conn) else ''
        session = sql(conn, 'SELECT * FROM "AuthSession" WHERE id = ?' + suffix,
                      (old['session_id'],)).fetchone()
        old = sql(conn, 'SELECT * FROM "AuthRefresh" WHERE id = ?', (token_hash,)).fetchone()
        timestamp = now()
        if not session or session['revoked_at'] is not None or session['expires_at'] <= timestamp:
            return None
        account = sql(conn, 'SELECT id FROM "Account" WHERE user_id = ? AND auth_enabled = 1', (session['user_id'],)).fetchone()
        if not account:
            return None
        if old['consumed_at'] is not None:
            sql(conn, 'UPDATE "AuthSession" SET revoked_at = ? WHERE id = ?',
                (timestamp, session['id']))
            return None
        if old['expires_at'] <= timestamp or session['kind'] != 'mobile':
            return None
        access, next_refresh = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        access_expiry = min(timestamp + ACCESS_SECONDS, session['expires_at'])
        refresh_expiry = min(timestamp + REFRESH_SECONDS, session['expires_at'])
        sql(conn, 'UPDATE "AuthRefresh" SET consumed_at = ? WHERE id = ?', (timestamp, token_hash))
        sql(conn, 'UPDATE "AuthSession" SET access_hash = ?, access_expires_at = ? WHERE id = ?',
            (digest(access), access_expiry, session['id']))
        sql(conn, 'INSERT INTO "AuthRefresh" (id, session_id, expires_at) VALUES (?, ?, ?)',
            (digest(next_refresh), session['id'], refresh_expiry))
        return {'access_token': access, 'refresh_token': next_refresh,
                'token_type': 'Bearer', 'expires_in': access_expiry - timestamp,
                'refresh_expires_in': refresh_expiry - timestamp,
                'session_id': session['id'], 'user_id': session['user_id']}


def revoke(conn, session_id, user_id, all_sessions=False):
    with transaction(conn):
        if all_sessions:
            sql(conn, 'UPDATE "AuthSession" SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL',
                (now(), user_id))
        else:
            sql(conn, 'UPDATE "AuthSession" SET revoked_at = ? WHERE id = ? AND user_id = ?',
                (now(), session_id, user_id))


def throttle(conn, keys, limit=5, seconds=60):
    """Atomic per-key fixed-window limits shared across all workers.

    Callers pass hashes, not raw emails, phone numbers or IP addresses.
    Attempts count even when the account is unknown or delivery fails.
    """
    timestamp = now()
    allowed = True
    with transaction(conn):
        sql(conn, 'DELETE FROM "AuthThrottle" WHERE expires_at < ?', (timestamp - 86400,))
        for key in keys:
            row = sql(conn, '''INSERT INTO "AuthThrottle" (id, attempts, expires_at) VALUES (?, 1, ?)
                ON CONFLICT (id) DO UPDATE SET
                attempts = CASE WHEN "AuthThrottle".expires_at <= ? THEN 1 ELSE "AuthThrottle".attempts + 1 END,
                expires_at = CASE WHEN "AuthThrottle".expires_at <= ? THEN excluded.expires_at ELSE "AuthThrottle".expires_at END
                RETURNING attempts''', (key, timestamp + seconds, timestamp, timestamp)).fetchone()
            allowed = allowed and row['attempts'] <= limit
    return allowed
