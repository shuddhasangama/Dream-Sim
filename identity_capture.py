"""Private identity evidence. An image is never itself an identity check.

No provider calls live here. Operators export a consented capture and record
the provider's result against its immutable capture ID, not a phone number.
"""
import base64
import hashlib
import io
import json
import os
import uuid
from datetime import datetime, timedelta, timezone

from PIL import Image, ImageOps, UnidentifiedImageError
import db
import ceremony
from api_contract import ApiError
from evolution_service import transaction

CONSENT_VERSION = 'identity-image-v1'
CONSENT_TEXT = ('I agree that DhaShu may securely store this identity image and share it '
                'with its background-verification provider solely to check my identity. '
                'It is separate from my public profile photo. Uploading it does not verify '
                'me. I can delete it here; deletion cannot recall an export already sent '
                'to the provider. The image is scheduled for deletion after 30 days; provider '
                'retention is governed separately. Existing agreement records are retained.')


def utcnow():
    return datetime.now(timezone.utc)


def stamp():
    return utcnow().isoformat()


def enabled():
    return os.environ.get('DHASHU_IDENTITY_CAPTURE_ENABLED', '0') == '1'


def cipher():
    # Lazy import: disabled deployments do not require a configured key.
    from cryptography.fernet import Fernet
    try:
        return Fernet(os.environ.get('DHASHU_IDENTITY_ENCRYPTION_KEY', '').encode('ascii'))
    except (ValueError, UnicodeError):
        raise ApiError('identity_unavailable', 'Secure identity storage is not configured.', 503) from None


def normalize(value):
    if not isinstance(value, str) or len(value) > 2_800_000 or ',' not in value:
        raise ApiError('invalid_image', 'Use a JPEG, PNG or WebP image under 2 MB.')
    prefix, encoded = value.split(',', 1)
    if prefix not in ('data:image/jpeg;base64', 'data:image/png;base64', 'data:image/webp;base64'):
        raise ApiError('invalid_image', 'Use a JPEG, PNG or WebP image.')
    try:
        raw = base64.b64decode(encoded, validate=True)
        if len(raw) > 2_000_000:
            raise ValueError()
        with Image.open(io.BytesIO(raw)) as source:
            if source.format not in ('JPEG', 'PNG', 'WEBP') or source.width * source.height > 20_000_000 or min(source.size) < 160:
                raise ValueError()
            # Preserve the whole image for the reviewer; no forced face crop.
            image = ImageOps.exif_transpose(source).convert('RGB')
            image.thumbnail((1200, 1200))
            out = io.BytesIO()
            image.save(out, 'JPEG', quality=88)
            return out.getvalue()
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError):
        raise ApiError('invalid_image', 'Use a readable image of at least 160 pixels, under 2 MB.') from None


def account_binding(conn, uid):
    account = db.fetch_one(conn, 'Account', user_id=uid) or {}
    value = json.dumps({k: account.get(k) for k in ('id', 'phone', 'email')}, sort_keys=True)
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def verified(conn, uid):
    row = db.fetch_one(conn, 'IdentityCapture', id=uid)
    return bool(row and row['status'] == 'verified' and row.get('valid_until') and row['valid_until'] > stamp()
                and row['account_binding_sha256'] == account_binding(conn, uid))


def view(conn, uid):
    row = db.fetch_one(conn, 'IdentityCapture', id=uid)
    status = row['status'] if row else 'not_captured'
    if row and status != 'deleted' and row['account_binding_sha256'] != account_binding(conn, uid):
        status = 'expired'
    elif status == 'verified' and not verified(conn, uid):
        status = 'expired'
    elif row and status in ('captured', 'submitted') and row['image_expires_at'] <= stamp():
        status = 'expired'
    return {'enabled': enabled(), 'status': status, 'verified': verified(conn, uid),
            'capture_id': row['capture_id'] if row else None,
            'captured_at': row['captured_at'] if row else None,
            'image_expires_at': row['image_expires_at'] if row else None,
            'valid_until': row.get('valid_until') if row else None,
            'consent_version': CONSENT_VERSION, 'consent_text': CONSENT_TEXT,
            'provider_connected': False, 'liveness_checked': False}


def event(conn, uid, capture_id, action, details=''):
    db.insert_row(conn, 'IdentityEvent', {'id': uuid.uuid4().hex, 'user_id': uid,
        'capture_id': capture_id, 'action': action, 'created_at': stamp(), 'details': details})


def capture(conn, uid, body):
    if not enabled():
        raise ApiError('identity_disabled', 'Identity capture is not enabled.', 403)
    if body.get('consent') is not True or body.get('consent_version') != CONSENT_VERSION:
        raise ApiError('consent_required', 'Review and explicitly accept the identity-image consent.')
    raw = normalize(body.get('image'))
    encrypted = cipher().encrypt(raw).decode('ascii')
    digest = hashlib.sha256(raw).hexdigest()
    with transaction(conn):
        old = db.fetch_one(conn, 'IdentityCapture', id=uid)
        if old and old['account_binding_sha256'] == account_binding(conn, uid) and old['image_sha256'] == digest and old['status'] in ('captured', 'submitted') and old['image_expires_at'] > stamp():
            return view(conn, uid)  # Network retry; no duplicate or extended retention.
        if old and old['status'] not in ('deleted', 'rejected') and view(conn, uid)['status'] != 'expired':
            raise ApiError('capture_exists', 'Delete your existing capture before replacing it.', 409)
        now = utcnow()
        row = {'id': uid, 'capture_id': uuid.uuid4().hex, 'status': 'captured',
            'image_ciphertext': encrypted, 'image_sha256': digest,
            'captured_at': now.isoformat(), 'image_expires_at': (now + timedelta(days=30)).isoformat(),
            'consent_version': CONSENT_VERSION, 'consent_text': CONSENT_TEXT,
            'provider': None, 'provider_reference': None, 'reviewed_at': None, 'valid_until': None,
            'authentication': ceremony.authentication_evidence()['authentication'],
            'account_binding_sha256': account_binding(conn, uid)}
        db.insert_row(conn, 'IdentityCapture', row)
        event(conn, uid, row['capture_id'], 'captured')
    return view(conn, uid)


def remove(conn, uid):
    with transaction(conn):
        row = db.fetch_one(conn, 'IdentityCapture', id=uid)
        if row and row['status'] != 'deleted':
            db.insert_row(conn, 'IdentityCapture', {**row, 'image_ciphertext': None,
                'status': 'deleted', 'valid_until': None})
            event(conn, uid, row['capture_id'], 'deleted')
    return view(conn, uid)


def provider_result(conn, uid, capture_id, provider, reference, result):
    if result not in ('verified', 'rejected') or not provider.strip() or not reference.strip():
        raise ValueError('A provider name, result reference and verified/rejected result are required.')
    with transaction(conn):
        row = db.fetch_one(conn, 'IdentityCapture', id=uid)
        if not row or row['capture_id'] != capture_id or row['status'] != 'submitted' or row['image_expires_at'] <= stamp():
            raise ValueError('Only the current, unexpired submitted capture can receive a result.')
        if row['provider'] != provider.strip():
            raise ValueError('The result provider must match the recorded submission provider.')
        if row['account_binding_sha256'] != account_binding(conn, uid):
            raise ValueError('Account contacts changed; a new consented capture is required.')
        now = utcnow()
        db.insert_row(conn, 'IdentityCapture', {**row, 'status': result, 'provider': provider.strip(),
            'provider_reference': reference.strip(), 'reviewed_at': now.isoformat(),
            'valid_until': (now + timedelta(days=365)).isoformat() if result == 'verified' else None})
        event(conn, uid, capture_id, result, json.dumps({'provider': provider, 'reference': reference}))
    # Deliberately does not change User.bgv_status or field-level BGV checks.


def purge(conn):
    with transaction(conn):
        count = 0
        for row in db.fetch_all(conn, 'IdentityCapture'):
            if row['image_ciphertext'] and row['image_expires_at'] <= stamp():
                db.insert_row(conn, 'IdentityCapture', {**row, 'image_ciphertext': None})
                event(conn, row['id'], row['capture_id'], 'image_expired')
                count += 1
        return count


def register(api, get_db):
    from flask import g, jsonify, request
    from api_contract import json_object

    def uid():
        if not getattr(g, 'auth_session', None):
            raise ApiError('authentication_required', 'An authenticated account is required for private identity evidence.', 401)
        return g.api_user['user_id']

    @api.get('/identity-capture')
    def identity_read():
        response = jsonify(view(get_db(), uid()))
        response.headers['Cache-Control'] = 'no-store'
        return response

    @api.post('/identity-capture')
    def identity_create():
        request.max_content_length = 2_900_000
        body = json_object(required={'image', 'consent', 'consent_version'})
        import auth_sessions
        actor = uid()
        if not auth_sessions.throttle(get_db(), ['identity-upload:' + actor], 10, 3600):
            raise ApiError('rate_limited', 'Too many capture attempts. Please try again later.', 429)
        response = jsonify(capture(get_db(), actor, body))
        response.headers['Cache-Control'] = 'no-store'
        return response

    @api.delete('/identity-capture')
    def identity_delete():
        response = jsonify(remove(get_db(), uid()))
        response.headers['Cache-Control'] = 'no-store'
        return response
