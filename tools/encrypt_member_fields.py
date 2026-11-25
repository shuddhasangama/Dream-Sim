"""Encrypt existing member fields in place (sec-enc). DRY RUN by default.

    python tools/encrypt_member_fields.py             report plain / encrypted counts per column
    python tools/encrypt_member_fields.py --apply     encrypt plain values, fill Account.phone_index
    python tools/encrypt_member_fields.py --decrypt --apply   rollback: write plain values back

Needs DHASHU_DATA_ENCRYPTION_KEY and DHASHU_BLIND_INDEX_KEY. Order for go-live:
set both keys -> deploy -> run --apply (index first, then values) -> set
DHASHU_FIELD_ENCRYPTION=1 so new writes are encrypted too. Reads accept both
forms at every step, so the app keeps working throughout. Each row is updated
only if unchanged since it was read; prints the database host first.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import db  # noqa: E402
import member_crypto  # noqa: E402


def run(conn, apply=False, decrypt=False, out=print):
    p = db._placeholder(conn)
    summary = {}
    for table, id_col, col in member_crypto.ENCRYPTED_COLUMNS:
        try:
            rows = conn.execute(f'SELECT "{id_col}" AS id, "{col}" AS v FROM "{table}" WHERE "{col}" IS NOT NULL').fetchall()
        except Exception:   # noqa: BLE001 — table missing in this database
            conn.rollback()
            continue
        plain = sealed = changed = 0
        for row in rows:
            value = row['v']
            if member_crypto.is_sealed(value):
                sealed += 1
                new = member_crypto.open_value(value) if decrypt else None
            else:
                plain += 1
                new = None if decrypt else member_crypto.force_seal(value)
            if apply and new is not None:
                cur = conn.execute(f'UPDATE "{table}" SET "{col}" = {p} WHERE "{id_col}" = {p} AND "{col}" = {p}',
                                   (new, row['id'], value))
                changed += cur.rowcount or 0
        conn.commit()
        summary[(table, col)] = {'plain': plain, 'encrypted': sealed, 'changed': changed}
        out(f'{table}.{col}: plain={plain} encrypted={sealed}' + (f' -> changed {changed}' if apply else ''))
    # blind index for every phone (plain or encrypted)
    missing = filled = 0
    try:
        rows = conn.execute('SELECT id, phone, phone_index FROM "Account" WHERE phone IS NOT NULL').fetchall()
    except Exception:   # noqa: BLE001
        conn.rollback(); rows = []
    for row in rows:
        index = member_crypto.blind_index(row['phone'])
        if index and row['phone_index'] != index:
            missing += 1
            if apply and not decrypt:
                filled += conn.execute(f'UPDATE "Account" SET phone_index = {p} WHERE id = {p}', (index, row['id'])).rowcount or 0
    conn.commit()
    summary['phone_index'] = {'missing': missing, 'filled': filled}
    out(f'Account.phone_index: missing={missing}' + (f' -> filled {filled}' if apply else ''))
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--decrypt', action='store_true')
    args = parser.parse_args(argv)
    if len(os.environ.get('DHASHU_BLIND_INDEX_KEY', '')) < 32 and not args.decrypt:
        parser.error('DHASHU_BLIND_INDEX_KEY (32+ characters) must be set first')
    url = os.environ.get('DATABASE_URL', '')
    host = url.split('@', 1)[1].split('/', 1)[0] if '@' in url else ('sqlite:' + str(db.DEFAULT_DB_PATH))
    print(f'Database host: {host}   mode: {"APPLY" if args.apply else "dry run"}{" (decrypt)" if args.decrypt else ""}')
    conn = db.get_connection()
    try:
        run(conn, apply=args.apply, decrypt=args.decrypt)
    finally:
        conn.close()


if __name__ == '__main__':
    main()
