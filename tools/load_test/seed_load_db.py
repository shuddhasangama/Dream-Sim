r"""Create and seed a LOCAL load-test database (c-scale-budget). Dry run by default.

    .venv\Scripts\python.exe tools\load_test\seed_load_db.py                 # dry run: prints the plan
    .venv\Scripts\python.exe tools\load_test\seed_load_db.py --apply --members 1600

Refuses anything but localhost:5433 and a database whose name ends in '_load', so
it can never touch dhashu_local, dhashu_test or a deployed database. Members are
synthetic (generate_users, seeded) and in 'dating', ids u_0001.. so the local
harness (/api/v1/dev/login-as) can sign the load users in.
"""
import argparse
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def target_url(base_url: str, name: str) -> str:
    parts = urlsplit(base_url)
    if parts.hostname not in ('localhost', '127.0.0.1') or parts.port != 5433:
        raise SystemExit('Refusing: the load database must be on localhost:5433.')
    if not name.endswith('_load'):
        raise SystemExit("Refusing: the load database name must end in '_load'.")
    return urlunsplit(parts._replace(path='/' + name))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--members', type=int, default=1600)
    parser.add_argument('--name', default='dhashu_load')
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    base = os.environ.get('DATABASE_URL', '')
    url = target_url(base, args.name)
    print(f'Plan: create database {args.name} on localhost:5433 if missing, apply the schema, '
          f'seed {args.members} synthetic dating members (seed 1500).')
    if not args.apply:
        print('DRY RUN. Re-run with --apply.')
        return 0
    import psycopg
    admin = urlunsplit(urlsplit(base)._replace(path='/postgres'))
    with psycopg.connect(admin, autocommit=True) as conn:
        if not conn.execute('SELECT 1 FROM pg_database WHERE datname = %s', (args.name,)).fetchone():
            conn.execute(f'CREATE DATABASE "{args.name}"')
    os.environ['DATABASE_URL'] = url
    os.environ['DHASHU_DB_POOL'] = '0'
    import db
    import generate_users
    from psycopg.rows import dict_row
    with psycopg.connect(url, row_factory=dict_row) as conn:
        db.init_db(conn)
        existing = conn.execute('SELECT count(*) AS n FROM "User"').fetchone()['n']
        if existing >= args.members:
            print(f'{existing} members already present; nothing to add.')
            return 0
        users = generate_users.generate_users(args.members, seed=1500)
        have = {r['id'] for r in conn.execute('SELECT id FROM "User"').fetchall()}
        generate_users.seed_db(conn, [u for u in users if u['user_id'] not in have])
        conn.commit()
        print('members now:', conn.execute('SELECT count(*) AS n FROM "User"').fetchone()['n'])
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
