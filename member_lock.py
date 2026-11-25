"""Owner-only member lock (feat-lock).

lock(): requires a reason; sets Account.locked_at/lock_reason, revokes EVERY
session of the member, records MemberLockEvent + SecurityEvent. A locked member
cannot get a new session by any route (OTP, password, tester) because
auth_sessions.issue_in_transaction refuses; authenticate/refresh also refuse.
unlock(): requires a reason; the member signs in again normally.
"""
import uuid

import auth_sessions as sessions
import db

MESSAGE = 'This account is locked. Please contact DhaShu support.'


class AccountLocked(Exception):
    """Raised when a locked member tries to start a session."""


def _reason(reason):
    reason = reason.strip() if isinstance(reason, str) else ''
    if not 10 <= len(reason) <= 500:
        raise ValueError('Give a reason of 10 to 500 characters.')
    return reason


def is_locked(conn, user_id):
    row = sessions.sql(conn, 'SELECT locked_at FROM "Account" WHERE user_id = ?', (user_id,)).fetchone()
    return bool(row and row['locked_at'] is not None)


def _change(conn, user_id, admin_id, action, reason):
    reason = _reason(reason)
    with sessions.transaction(conn):
        db.lock_user_rows(conn, user_id)
        suffix = ' FOR UPDATE' if db._is_postgres_connection(conn) else ''
        account = sessions.sql(conn, 'SELECT id, locked_at FROM "Account" WHERE user_id = ?' + suffix, (user_id,)).fetchone()
        if not account:
            raise LookupError('This member has no sign-in account.')
        timestamp = sessions.now()
        if action == 'lock':
            if account['locked_at'] is not None:
                raise ValueError('This member is already locked.')
            sessions.sql(conn, 'UPDATE "Account" SET locked_at = ?, lock_reason = ? WHERE id = ?',
                         (timestamp, reason, account['id']))
            sessions.sql(conn, 'UPDATE "AuthSession" SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL',
                         (timestamp, user_id))
        else:
            if account['locked_at'] is None:
                raise ValueError('This member is not locked.')
            sessions.sql(conn, 'UPDATE "Account" SET locked_at = NULL, lock_reason = NULL WHERE id = ?', (account['id'],))
        sessions.sql(conn, '''INSERT INTO "MemberLockEvent" (id, user_id, action, reason, admin_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?)''', (uuid.uuid4().hex, user_id, action, reason, admin_id, timestamp))
        sessions.record_security_event(conn, user_id, 'member_' + action, 'by admin')


def lock(conn, user_id, admin_id, reason):
    _change(conn, user_id, admin_id, 'lock', reason)


def unlock(conn, user_id, admin_id, reason):
    _change(conn, user_id, admin_id, 'unlock', reason)


def history(conn, user_id):
    return [dict(r) for r in sessions.sql(conn, '''SELECT action, reason, admin_id, created_at FROM "MemberLockEvent"
        WHERE user_id = ? ORDER BY created_at DESC LIMIT 20''', (user_id,)).fetchall()]
