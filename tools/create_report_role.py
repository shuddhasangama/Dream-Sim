"""Create the read-only reporting database user for the admin dashboard (sec-admin).

    python tools/create_report_role.py              print the SQL (dry run)
    python tools/create_report_role.py --apply      run it (needs an owner/superuser DATABASE_URL)

The password comes from ADMIN_REPORT_DB_PASSWORD (never a command-line argument).
Afterwards set ADMIN_REPORT_DATABASE_URL=postgresql://dhashu_report:<password>@host/db
on the ADMIN service only. admin_dashboard/reports.py then reads through this user:
- read-only at the role level (default_transaction_read_only) AND per transaction;
- SELECT only on the tables/columns the reports use. Password hashes, session and
  refresh token hashes, OTP challenges and authenticator secrets are NOT readable.
Re-running is safe (grants are idempotent; the password is reset).
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROLE = 'dhashu_report'

# Whole tables with no secrets that reports read.
TABLES = ['User', 'UserActivity', 'BgvRequest', 'BillingPurchase', 'DigiLockerSession', 'ErrorReport',
          'MemberLockEvent', 'SignzyGuard', 'LivenessSession', 'FaceMatchJob', 'AvatarJob', 'AdminAudit']
# Tables that hold secrets: only these columns.
COLUMNS = {
    'Account': ['id', 'user_id', 'email', 'phone', 'phone_index', 'auth_enabled', 'verified_email', 'verified_phone',
                'verification_required', 'created_at', 'locked_at', 'lock_reason'],
    'AuthSession': ['id', 'user_id', 'kind', 'created_at', 'access_expires_at', 'expires_at', 'revoked_at'],
    'AuthRefresh': ['session_id', 'consumed_at', 'expires_at'],
    'AdminIdentity': ['id', 'email', 'role'],
}


def statements(database, password, role=ROLE, schema='public'):
    quoted = password.replace("'", "''")
    yield f"""DO $$ BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN
    CREATE ROLE {role} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
  END IF;
END $$"""
    yield f"ALTER ROLE {role} WITH LOGIN PASSWORD '{quoted}'"
    yield f"ALTER ROLE {role} SET default_transaction_read_only = on"
    yield f"ALTER ROLE {role} SET statement_timeout = '5s'"
    yield f'GRANT CONNECT ON DATABASE "{database}" TO {role}'
    yield f'GRANT USAGE ON SCHEMA "{schema}" TO {role}'
    yield f'REVOKE ALL ON ALL TABLES IN SCHEMA "{schema}" FROM {role}'
    for table in TABLES:
        yield f'GRANT SELECT ON "{schema}"."{table}" TO {role}'
    for table, columns in COLUMNS.items():
        yield f'GRANT SELECT ({", ".join(columns)}) ON "{schema}"."{table}" TO {role}'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    password = os.environ.get('ADMIN_REPORT_DB_PASSWORD', '')
    url = os.environ.get('DATABASE_URL', '')
    if not url.startswith('postgres'):
        parser.error('DATABASE_URL must point at PostgreSQL')
    if args.apply and len(password) < 16:
        parser.error('Set ADMIN_REPORT_DB_PASSWORD (16+ characters) first')
    import psycopg
    host = url.split('@', 1)[1].split('/', 1)[0] if '@' in url else '?'
    with psycopg.connect(url, autocommit=True) as conn:
        database = conn.execute('SELECT current_database()').fetchone()[0]
        print(f'Database host: {host}  database: {database}  mode: {"APPLY" if args.apply else "dry run"}')
        for sql in statements(database, password or '<ADMIN_REPORT_DB_PASSWORD>'):
            print((sql.split('PASSWORD')[0] + "PASSWORD '***'") if 'PASSWORD' in sql else sql)
            if args.apply:
                conn.execute(sql)


if __name__ == '__main__':
    main()
