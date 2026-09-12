"""Explicit operator approval of existing beta profiles; never a public endpoint.

Dry run is the default. --apply is required to change accounts. DATABASE_URL
selects Railway/PostgreSQL; otherwise the normal local database is used.
"""
import argparse
import uuid

import auth
import auth_sessions as sessions
import db


def manage(conn, user_id, action, email=None, phone=None, apply=False):
    with sessions.transaction(conn):
        if db._is_postgres_connection(conn):
            sessions.sql(conn, 'LOCK TABLE "Account" IN SHARE ROW EXCLUSIVE MODE')
        if not db.fetch_one(conn, 'User', id=user_id):
            raise ValueError('No profile exists with this user ID.')
        existing = db.fetch_one(conn, 'Account', user_id=user_id)
        if action == 'disable':
            if not existing:
                raise ValueError('This profile has no account to disable.')
            if apply:
                sessions.sql(conn, 'UPDATE "Account" SET auth_enabled = 0 WHERE user_id = ?', (user_id,))
                sessions.sql(conn, 'UPDATE "AuthSession" SET revoked_at = ? WHERE user_id = ?', (sessions.now(), user_id))
            return 'Account access disabled and sessions revoked.' if apply else 'Would disable access and revoke all sessions.'
        if action != 'enable':
            raise ValueError('Unsupported action.')
        email = email if email is not None else (existing or {}).get('email')
        phone = phone if phone is not None else (existing or {}).get('phone')
        contacts = {}
        for channel, value in (('email', email), ('phone', phone)):
            if value:
                normalized = auth.normalize(channel, value, stored=True)
                if not normalized:
                    raise ValueError('Invalid ' + channel + '; phone must include country code.')
                contacts[channel] = normalized
            else:
                contacts[channel] = None
        if not any(contacts.values()):
            raise ValueError('Provide at least one real contact controlled by this tester.')
        for row in db.fetch_all(conn, 'Account'):
            if row['user_id'] == user_id:
                continue
            for channel, value in contacts.items():
                if value and auth.normalize(channel, row[channel], stored=True) == value:
                    raise ValueError('That ' + channel + ' is already associated with another account.')
        if apply:
            account_id = existing['id'] if existing else uuid.uuid4().hex
            if not existing:
                sessions.sql(conn, '''INSERT INTO "Account" (id, user_id, email, phone, auth_enabled, verification_required, created_at)
                    VALUES (?, ?, ?, ?, 1, 1, ?)''',
                    (account_id, user_id, contacts['email'], contacts['phone'], str(sessions.now())))
            else:
                # Re-approval or contact correction invalidates all old challenges
                # and sessions. Only a fresh real OTP can establish access.
                sessions.sql(conn, '''UPDATE "Account" SET email = ?, phone = ?, auth_enabled = 1,
                    verified_email = 0, verified_phone = 0, verification_required = 1 WHERE id = ?''',
                    (contacts['email'], contacts['phone'], account_id))
            sessions.sql(conn, 'UPDATE "AuthChallenge" SET consumed_at = ? WHERE account_id = ?', (sessions.now(), account_id))
            sessions.sql(conn, 'UPDATE "AuthSession" SET revoked_at = ? WHERE user_id = ?', (sessions.now(), user_id))
        return 'Account approved; fresh OTP sign-in is required.' if apply else 'Would approve this profile for OTP sign-in and revoke its existing sessions.'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('enable', 'disable'))
    parser.add_argument('--user-id', required=True)
    parser.add_argument('--email')
    parser.add_argument('--phone', help='Country code included, e.g. +91 followed by the number')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    conn = db.get_connection()
    try:
        db.init_db(conn)
        print(manage(conn, args.user_id, args.action, args.email, args.phone, args.apply))
    except ValueError as exc:
        parser.error(str(exc))
    finally:
        conn.close()


if __name__ == '__main__':
    main()
