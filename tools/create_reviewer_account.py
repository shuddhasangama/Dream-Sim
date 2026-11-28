"""Create or update THE App Store / Google Play reviewer account (client answer 9).

Reviewers cannot receive an SMS code, so this account signs in with phone + password
only and skips the verification gates (see reviewer_accounts.py for every rule).

    .venv\\Scripts\\python.exe tools\\create_reviewer_account.py --apply
    .venv\\Scripts\\python.exe tools\\create_reviewer_account.py --apply --database-url <postgresql://...>

- The phone number and password are asked for at run time with hidden input. They are
  never accepted as arguments or environment variables, never printed and never logged.
- Without --apply it refuses to run and changes nothing.
- The target database is DATABASE_URL, or --database-url for this run only. Its host
  and database name (never the password) are shown before you confirm.
- It needs no test switch, so it runs under prod_guard and security_config exactly like
  the web service (SECRET_KEY set, no test-only setting in production).
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def describe(url):
    from urllib.parse import urlsplit
    parts = urlsplit(url or '')
    return f'{parts.hostname or "?"}:{parts.port or 5432}/{parts.path.lstrip("/") or "?"}'


def main(argv=None, ask=getpass.getpass, confirm=input, connect=None):
    parser = argparse.ArgumentParser(description='Create or update the one store reviewer account.')
    parser.add_argument('--apply', action='store_true', help='required: actually write the account')
    parser.add_argument('--database-url', help='target database for this run (default: DATABASE_URL)')
    args = parser.parse_args(argv)
    if not args.apply:
        print('Refused: nothing was changed. Re-run with --apply to create or update the reviewer account.')
        return 2
    if args.database_url:
        os.environ['DATABASE_URL'] = args.database_url
    import prod_guard
    import security_config
    try:
        prod_guard.assert_safe_startup()
        security_config.require_secret_key()
    except RuntimeError as exc:
        print(f'Refused: {exc}')
        return 2
    import db
    import reviewer_accounts
    target = os.environ.get('DATABASE_URL', '')
    if connect is None and not target.startswith(('postgres://', 'postgresql://')):
        print('Refused: set DATABASE_URL (or --database-url) to the PostgreSQL database to change.')
        return 2
    print('Target database:', describe(target) if target else '(test connection)')
    if confirm('Type YES to continue: ').strip() != 'YES':
        print('Cancelled: nothing was changed.')
        return 1
    phone = ask('Reviewer phone number (+91..., hidden): ')
    password = ask('Reviewer password (hidden): ')
    if ask('Repeat the password (hidden): ') != password:
        print('Refused: the passwords did not match. Nothing was changed.')
        return 2
    conn = connect() if connect else db.get_connection()
    try:
        columns = {c.lower() for c in db._existing_columns(conn, 'Account')}
        if 'reviewer' not in columns:
            print('Refused: this database has no Account.reviewer column yet. Run the migrations (0009_account_reviewer) first.')
            return 2
        try:
            uid, outcome = reviewer_accounts.upsert(conn, phone, password)
        except reviewer_accounts.ReviewerError as exc:
            print(f'Refused: {exc}')
            return 2
    finally:
        conn.close()
        phone = password = None
    print(f'Reviewer account {outcome}: {uid}. It signs in with phone + password (no SMS code).')
    return 0


if __name__ == '__main__':
    sys.exit(main())
