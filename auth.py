"""Email/SMS OTP identity, session integration and secure beta route guards."""
import hashlib
import hmac
import os
import re
import secrets
from urllib.parse import urlsplit

from flask import abort, current_app, g, jsonify, redirect, render_template, request, session

import auth_delivery
import auth_sessions as sessions
import db

CHALLENGE_SECONDS = 600
GENERIC_SENT = 'If this contact belongs to an approved beta account, a code will arrive shortly.'


def enabled():
    return current_app.config.get('AUTH_ENABLED', False)


def normalize(channel, value, stored=False):
    if not isinstance(value, str) or len(value) > 254:
        return None
    if channel == 'email':
        value = value.strip().lower()
        return value if re.fullmatch(r'[^@\s]+@[^@\s]+\.[^@\s]+', value) else None
    if channel == 'phone':
        value = value.strip()
        if stored and re.fullmatch(r'[1-9][0-9]{7,14}', value):
            value = '+' + value
        return value if re.fullmatch(r'\+[1-9][0-9]{7,14}', value) else None
    return None


def key(value):
    return hmac.new(current_app.secret_key.encode(), value.encode(), hashlib.sha256).hexdigest()


def same_origin():
    supplied = request.headers.get('Origin') or request.headers.get('Referer', '')
    try:
        parsed = urlsplit(supplied)
    except ValueError:
        return False
    origin = parsed.scheme + '://' + parsed.netloc
    return origin == current_app.config['AUTH_PUBLIC_ORIGIN']


def resolve(get_db):
    if not enabled():
        return None
    if 'auth_resolved' in g:
        return g.auth_session
    g.auth_resolved = True
    g.auth_session = None
    authorization = request.headers.get('Authorization')
    if authorization is not None:
        parts = authorization.split()
        if not request.path.startswith('/api/v1/') or len(parts) != 2 or parts[0].lower() != 'bearer':
            return None
        token, kind = parts[1], 'mobile'
    else:
        token, kind = session.get('auth_token'), 'web'
    if token:
        g.auth_session = sessions.authenticate(get_db(), token, kind)
    return g.auth_session


def failure(message, status=400, code='validation_error'):
    return jsonify(error=message, code=code), status


def start_challenge(conn, channel, destination, kind):
    if not auth_delivery.configured():
        return None, failure('Sign-in delivery is not configured yet.', 503, 'auth_unavailable')
    if not sessions.throttle(conn, [key('send-ip:' + (request.remote_addr or 'unknown'))], 20, 600):
        return None, failure('Please wait before requesting another code.', 429, 'rate_limited')
    if not sessions.throttle(conn, [key('send-contact:' + channel + ':' + destination)], 1, 60):
        return None, failure('Please wait before requesting another code.', 429, 'rate_limited')
    matches = [dict(row) for row in db.fetch_all(conn, 'Account')
               if normalize(channel, row.get(channel), stored=True) == destination]
    # Canonical duplicates fail closed instead of guessing the account owner.
    account = matches[0] if len(matches) == 1 and matches[0].get('auth_enabled') else None
    raw = secrets.token_urlsafe(32)
    provider_sid = None
    if account:
        try:
            provider_sid = auth_delivery.start(channel, destination)
        except auth_delivery.DeliveryUnavailable:
            # Same status/body shape as unknown contact, without provider
            # details. Operators get only a generic warning.
            current_app.logger.warning('OTP delivery unavailable')
    with sessions.transaction(conn):
        sessions.sql(conn, 'DELETE FROM "AuthChallenge" WHERE expires_at < ?', (sessions.now() - 86400,))
        if account:
            sessions.sql(conn, 'UPDATE "AuthChallenge" SET consumed_at = ? WHERE account_id = ? AND channel = ? AND consumed_at IS NULL',
                         (sessions.now(), account['id'], channel))
        sessions.sql(conn, '''INSERT INTO "AuthChallenge"
            (id, account_id, channel, destination, provider_sid, kind, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)''',
            (sessions.digest(raw), account['id'] if account else None, channel,
             destination, provider_sid, kind, sessions.now() + CHALLENGE_SECONDS))
    return {'challenge_id': raw, 'expires_in': CHALLENGE_SECONDS, 'message': GENERIC_SENT}, None


def verify_challenge(conn, challenge, code, kind):
    if not sessions.valid_token(challenge) or not isinstance(code, str) or not re.fullmatch(r'[0-9]{4,10}', code):
        return None
    if not sessions.throttle(conn, [key('check-ip:' + (request.remote_addr or 'unknown'))], 30, 600):
        return None
    with sessions.transaction(conn):
        row = sessions.sql(conn, '''UPDATE "AuthChallenge" SET attempts = attempts + 1
            WHERE id = ? AND kind = ? AND consumed_at IS NULL AND attempts < 5 AND expires_at > ?
            RETURNING *''', (sessions.digest(challenge), kind, sessions.now())).fetchone()
    if not row or not row['provider_sid']:
        return None
    row = dict(row)
    try:
        approved = auth_delivery.check(row['provider_sid'], code)
    except auth_delivery.DeliveryUnavailable:
        current_app.logger.warning('OTP verification unavailable')
        return None
    if not approved:
        return None
    with sessions.transaction(conn):
        # Recheck expiry/consumption after the external call. Exactly one
        # request can redeem a challenge even if the provider repeats approval.
        suffix = ' FOR UPDATE' if db._is_postgres_connection(conn) else ''
        account = sessions.sql(conn, 'SELECT * FROM "Account" WHERE id = ?' + suffix, (row['account_id'],)).fetchone()
        if not account or not account['auth_enabled'] or normalize(row['channel'], account[row['channel']], stored=True) != row['destination']:
            return None
        redeemed = sessions.sql(conn, '''UPDATE "AuthChallenge" SET consumed_at = ?
            WHERE id = ? AND consumed_at IS NULL AND expires_at > ? RETURNING account_id''',
            (sessions.now(), row['id'], sessions.now())).fetchone()
        if not redeemed:
            return None
        verified_column = 'verified_email' if row['channel'] == 'email' else 'verified_phone'
        sessions.sql(conn, 'UPDATE "Account" SET ' + verified_column + ' = 1 WHERE id = ?', (account['id'],))
        return sessions.issue_in_transaction(conn, account['user_id'], kind)


def register_auth(app, get_db):
    app.config['AUTH_ENABLED'] = os.environ.get('AUTH_ENABLED', '').lower() in ('1', 'true', 'on')
    app.config['AUTH_PUBLIC_ORIGIN'] = os.environ.get('AUTH_PUBLIC_ORIGIN', '').rstrip('/')
    if app.config['AUTH_ENABLED']:
        origin = urlsplit(app.config['AUTH_PUBLIC_ORIGIN'])
        if origin.scheme != 'https' or not origin.netloc or origin.path or origin.query or origin.fragment:
            raise RuntimeError('AUTH_PUBLIC_ORIGIN must be an HTTPS origin without a path.')
        if not os.environ.get('SECRET_KEY') or len(app.secret_key) < 32:
            raise RuntimeError('Secure sign-in requires a strong SECRET_KEY of at least 32 characters.')
        if not auth_delivery.configured():
            raise RuntimeError('Secure sign-in requires Twilio Verify configuration.')
        app.config.update(SESSION_COOKIE_SECURE=True, SESSION_COOKIE_HTTPONLY=True,
                          SESSION_COOKIE_SAMESITE='Lax', SESSION_COOKIE_NAME='dhashu_auth',
                          MAX_CONTENT_LENGTH=1024 * 1024)

    @app.before_request
    def secure_boundary():
        if not enabled():
            if request.path == '/signin':
                return redirect('/signup')
            if request.path.startswith('/api/v1/auth/'):
                return failure('Secure sign-in is not enabled.', 503, 'auth_unavailable')
            return None
        # No alternate route may mint a trusted identity or reveal simulation data.
        if (request.path == '/pool' or request.path.startswith(('/login/', '/admin', '/demo'))
                or request.path == '/verify/simulate' or request.path.startswith('/verify-contact')):
            abort(404)
        if request.path == '/signup' or request.path.startswith('/onboarding/'):
            return redirect('/signin')
        if request.path.startswith('/api/v1/auth/'):
            if request.content_length and request.content_length > 4096:
                return failure('Request body is too large.', 413, 'validation_error')
        is_mobile_auth = request.path.startswith('/api/v1/auth/')
        if request.method not in ('GET', 'HEAD', 'OPTIONS') and not is_mobile_auth:
            bearer = request.path.startswith('/api/v1/') and request.headers.get('Authorization') is not None
            if bearer:
                if resolve(get_db) is None:
                    return failure('Sign in to continue.', 401, 'authentication_required')
            elif not same_origin():
                return failure('This request must come from this site.', 403, 'forbidden')

    @app.after_request
    def auth_headers(response):
        if enabled() and (request.path == '/signin' or request.path.startswith('/api/v1/') or session.get('auth_token')):
            response.headers['Cache-Control'] = 'no-store'
            response.headers['Referrer-Policy'] = 'same-origin'
        if enabled() and request.path.startswith('/api/v1/'):
            if response.status_code == 401:
                response.headers['WWW-Authenticate'] = 'Bearer realm="DhaShu API"'
            elif response.status_code == 429:
                response.headers['Retry-After'] = '600'
        return response

    @app.context_processor
    def auth_context():
        return {'secure_auth_enabled': enabled()}

    def payload(fields):
        if not request.is_json:
            return None, failure('Use application/json.', 415, 'unsupported_media_type')
        body = request.get_json(silent=True)
        if not isinstance(body, dict) or set(body) != set(fields):
            return None, failure('Expected fields: ' + ', '.join(fields))
        return body, None

    @app.post('/api/v1/auth/request')
    def auth_request():
        body, error = payload(('channel', 'destination'))
        if error:
            return error
        destination = normalize(body['channel'], body['destination'])
        if destination is None:
            return failure('Enter a valid email or phone with country code, for example +91 followed by the number.')
        result, error = start_challenge(get_db(), body['channel'], destination, 'mobile')
        return error if error else (jsonify(result), 202)

    @app.post('/api/v1/auth/verify')
    def auth_verify():
        body, error = payload(('challenge_id', 'code'))
        if error:
            return error
        result = verify_challenge(get_db(), body['challenge_id'], body['code'], 'mobile')
        return jsonify(result) if result else failure('Code is invalid or expired. Request a new code.', 401, 'invalid_code')

    @app.post('/api/v1/auth/refresh')
    def auth_refresh():
        body, error = payload(('refresh_token',))
        if error:
            return error
        if not sessions.throttle(get_db(), [key('refresh-ip:' + (request.remote_addr or 'unknown'))], 60, 60):
            return failure('Please wait and try again.', 429, 'rate_limited')
        result = sessions.refresh(get_db(), body['refresh_token'])
        return jsonify(result) if result else failure('Sign in again.', 401, 'authentication_required')

    @app.post('/api/v1/auth/logout')
    def auth_logout():
        return logout_api(False)

    @app.post('/api/v1/auth/logout-all')
    def auth_logout_all():
        return logout_api(True)

    def logout_api(all_sessions):
        # These endpoints are bearer-only: a cookie cannot bypass CSRF checks.
        if request.headers.get('Authorization') is None:
            return failure('A bearer token is required.', 401, 'authentication_required')
        active = resolve(get_db)
        if not active:
            return failure('Sign in to continue.', 401, 'authentication_required')
        sessions.revoke(get_db(), active['id'], active['user_id'], all_sessions)
        return jsonify(logged_out=True)

    @app.route('/signin', methods=['GET', 'POST'])
    def signin():
        message = error = None
        challenge = session.get('login_challenge')
        if request.method == 'POST':
            if request.form.get('action') == 'request':
                channel = request.form.get('channel')
                destination = normalize(channel, request.form.get('destination'))
                if destination is None:
                    error = 'Enter a valid email or phone number including its country code.'
                else:
                    result, failure_response = start_challenge(get_db(), channel, destination, 'web')
                    if failure_response:
                        error = 'Sign-in is unavailable or too many codes were requested. Please try later.'
                    else:
                        active = resolve(get_db)
                        if active:
                            sessions.revoke(get_db(), active['id'], active['user_id'])
                        session.clear()
                        challenge = result['challenge_id']
                        session['login_challenge'] = challenge
                        message = GENERIC_SENT
            elif request.form.get('action') == 'verify':
                result = verify_challenge(get_db(), challenge, request.form.get('code'), 'web')
                if result:
                    session.clear()
                    session['auth_token'] = result['access_token']
                    session['user_id'] = result['user_id']
                    return redirect('/dashboard')
                error = 'Code is invalid or expired. Request a new code.'
        return render_template('signin.html', challenge=challenge, message=message, error=error)
