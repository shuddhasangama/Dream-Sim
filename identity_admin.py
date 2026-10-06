"""Explicit operator handoff; never sends an image to a third party itself."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import zipfile

import db
import identity_capture as identity
from evolution_service import transaction


def current(conn, uid, capture_id):
    row = db.fetch_one(conn, 'IdentityCapture', id=uid)
    if not row or row['capture_id'] != capture_id or row['status'] in ('deleted', 'rejected') or row['image_expires_at'] <= identity.stamp():
        raise ValueError('Use the current unexpired capture ID; deleted/rejected captures cannot be exported.')
    if row['account_binding_sha256'] != identity.account_binding(conn, uid):
        raise ValueError('Account contacts changed; a new consented capture is required.')
    return row


def export(conn, uid, capture_id, output):
    output = Path(output).resolve()
    created = False
    try:
        with transaction(conn):
            row = current(conn, uid, capture_id)
            if not row['image_ciphertext']:
                raise ValueError('The image has been deleted.')
            raw = identity.cipher().decrypt(row['image_ciphertext'].encode('ascii'))
            if hashlib.sha256(raw).hexdigest() != row['image_sha256']:
                raise ValueError('Stored image integrity check failed.')
            manifest = {key: row[key] for key in ('capture_id', 'image_sha256', 'captured_at',
                'image_expires_at', 'consent_version', 'consent_text', 'authentication')}
            manifest.update(user_id=uid, source='user_supplied_image', liveness_checked=False,
                            identity_authenticated=False)
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as bundle:
                bundle.writestr('identity.jpg', raw)
                bundle.writestr('manifest.json', json.dumps(manifest, indent=2))
            # Exclusive creation: never overwrite another person's export.
            fd = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created = True
            with os.fdopen(fd, 'wb') as target:
                target.write(buffer.getvalue())
            identity.event(conn, uid, capture_id, 'exported')
        return output
    except BaseException:
        if created:
            output.unlink(missing_ok=True)
        raise


def submitted(conn, uid, capture_id, provider, reference):
    if not provider.strip() or not reference.strip():
        raise ValueError('Provider and submission reference are required.')
    with transaction(conn):
        row = current(conn, uid, capture_id)
        if row['status'] != 'captured':
            raise ValueError('Only a captured image can be marked submitted.')
        db.insert_row(conn, 'IdentityCapture', {**row, 'status': 'submitted',
            'provider': provider.strip(), 'provider_reference': reference.strip()})
        identity.event(conn, uid, capture_id, 'submitted', json.dumps({'provider': provider, 'reference': reference}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('status', 'export', 'submitted', 'result', 'purge'))
    parser.add_argument('--user-id')
    parser.add_argument('--capture-id')
    parser.add_argument('--output', help='Private ZIP path outside your repository; do not commit it.')
    parser.add_argument('--provider')
    parser.add_argument('--reference')
    parser.add_argument('--result', choices=('verified', 'rejected'))
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    if args.action != 'purge' and not args.user_id:
        parser.error('--user-id is required')
    if args.action in ('export', 'submitted', 'result') and not args.capture_id:
        parser.error('--capture-id is required (from status)')
    if args.action == 'export' and not args.output:
        parser.error('--output is required')
    if args.action in ('submitted', 'result') and not (args.provider and args.reference):
        parser.error('--provider and --reference are required')
    if args.action == 'result' and not args.result:
        parser.error('--result is required')
    conn = db.get_connection()
    try:
        if args.action == 'status':
            print(json.dumps(identity.view(conn, args.user_id), indent=2))
        elif not args.apply:
            print('DRY RUN: no image exported or database changes made. Repeat with --apply.')
        elif args.action == 'export':
            print('Private export created:', export(conn, args.user_id, args.capture_id, args.output))
        elif args.action == 'submitted':
            submitted(conn, args.user_id, args.capture_id, args.provider, args.reference)
            print('Submission recorded; awaiting provider result.')
        elif args.action == 'result':
            identity.provider_result(conn, args.user_id, args.capture_id, args.provider, args.reference, args.result)
            print('Provider result recorded. Account BGV and other checks were not changed.')
        else:
            print('Expired images purged:', identity.purge(conn))
    except (ValueError, OSError) as exc:
        parser.exit(1, str(exc) + '\n')
    finally:
        conn.close()


if __name__ == '__main__':
    main()
