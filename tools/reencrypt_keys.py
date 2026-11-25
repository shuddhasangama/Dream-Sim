"""Re-encrypt stored values onto the current key (sec-keys). DRY RUN by default.

    python tools/reencrypt_keys.py                 report: values per key id, per column
    python tools/reencrypt_keys.py --apply         re-encrypt values on older keys
    python tools/reencrypt_keys.py --key WAITLIST_ENCRYPTION_KEY   one key only

Connects with DATABASE_URL (or the local SQLite file) and prints the host first.
Keys whose variable is not set are skipped. Each row is updated only if its
value is unchanged since it was read (safe while the app is running), in
batches of --batch rows per commit. Values no key can open are counted as
'unreadable' and never touched. Run the dry run again afterwards: when every
column shows only the current key id, remove <KEY>_PREVIOUS.
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import crypto_keys  # noqa: E402
import db  # noqa: E402

# key variable -> [(table, id column, value column)]
REGISTRY = {
    'SIGNZY_RECEIPT_ENCRYPTION_KEY': [
        ('BgvEvidence', 'id', 'protected_details'),
        ('BgvRequest', 'id', 'protected_input'), ('BgvRequest', 'id', 'protected_result'),
        ('DigiLockerSession', 'id', 'protected_photo'), ('DigiLockerSession', 'id', 'protected_session'),
        ('DigiLockerSession', 'id', 'protected_result'),
        ('BgvAttempt', 'id', 'protected_evidence'), ('BgvReview', 'id', 'protected_note'),
        ('AvatarJob', 'id', 'protected_selfie'), ('AvatarJob', 'id', 'protected_options'),
        ('AvatarJob', 'id', 'protected_selected'),
        ('FaceImageLease', 'id', 'protected_images'),
        ('FaceMatchJob', 'id', 'protected_input'), ('FaceMatchJob', 'id', 'protected_result'),
        ('LivenessSession', 'id', 'protected_input'), ('LivenessSession', 'id', 'protected_session'),
        ('LivenessSession', 'id', 'protected_result'),
    ],
    'WAITLIST_ENCRYPTION_KEY': [('WaitlistEntry', 'id', 'protected_data')],
    'DHASHU_GURU_ENCRYPTION_KEY': [('GuruPrivate', 'id', 'payload'), ('GuruDiscussion', 'id', 'payload')],
    'DHASHU_IDENTITY_ENCRYPTION_KEY': [('IdentityCapture', 'id', 'image_ciphertext')],
    'ADMIN_TOTP_ENCRYPTION_KEY': [('AdminIdentity', 'id', 'protected_totp')],
    'DHASHU_DATA_ENCRYPTION_KEY': [],   # filled by sec-enc (member_crypto.FIELDS)
}


def registry():
    try:
        import member_crypto
        extra = [(t, i, c) for (t, i, c) in member_crypto.ENCRYPTED_COLUMNS]
    except ImportError:
        extra = []
    return {**REGISTRY, 'DHASHU_DATA_ENCRYPTION_KEY': extra}


def _table_exists(conn, table):
    try:
        conn.execute(f'SELECT 1 FROM "{table}" WHERE 1 = 0').fetchall()
        return True
    except Exception:   # noqa: BLE001
        conn.rollback()
        return False


def run(conn, apply=False, only=None, batch=200, out=print):
    p = db._placeholder(conn)
    summary = {}
    for name, columns in registry().items():
        if only and name != only:
            continue
        try:
            entries = crypto_keys.entries(name)
        except (KeyError, ValueError):
            out(f'{name}: not set, skipped')
            continue
        current = entries[0][0]
        multi = crypto_keys.cipher(name)
        for table, id_col, col in columns:
            if not _table_exists(conn, table):
                continue
            counts, changed = {}, 0
            rows = conn.execute(f'SELECT "{id_col}" AS id, "{col}" AS v FROM "{table}" WHERE "{col}" IS NOT NULL').fetchall()
            pending = 0
            for row in rows:
                key_id = crypto_keys.which(name, row['v'])
                label = key_id or 'unreadable'
                counts[label] = counts.get(label, 0) + 1
                if apply and key_id and key_id != current:
                    fresh = multi.rotate(row['v'].encode('ascii')).decode('ascii')
                    cur = conn.execute(f'UPDATE "{table}" SET "{col}" = {p} WHERE "{id_col}" = {p} AND "{col}" = {p}',
                                       (fresh, row['id'], row['v']))
                    changed += cur.rowcount or 0
                    pending += 1
                    if pending >= batch:
                        conn.commit(); pending = 0
            conn.commit()
            summary[(name, table, col)] = {'counts': counts, 'reencrypted': changed}
            listing = ', '.join(f'{k}={v}' for k, v in sorted(counts.items())) or 'empty'
            out(f'{name} {table}.{col}: {listing}' + (f' -> re-encrypted {changed} onto {current}' if apply else ''))
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--apply', action='store_true', help='write changes (default: dry run)')
    parser.add_argument('--key', help='only this key variable')
    parser.add_argument('--batch', type=int, default=200)
    args = parser.parse_args(argv)
    url = os.environ.get('DATABASE_URL', '')
    host = url.split('@', 1)[1].split('/', 1)[0] if '@' in url else ('sqlite:' + str(db.DEFAULT_DB_PATH))
    print(f'Database host: {host}   mode: {"APPLY" if args.apply else "dry run"}')
    conn = db.get_connection()
    try:
        run(conn, apply=args.apply, only=args.key, batch=max(1, args.batch))
    finally:
        conn.close()


if __name__ == '__main__':
    main()
