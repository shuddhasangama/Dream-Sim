"""Local development harness: sign in as a seeded user from the Android emulator.

LOCAL ONLY. Lets an emulator dev build (mobile `npm run build:emulator`) obtain
the SAME kind of access/refresh tokens the real login issues, for an existing
seeded user, against a backend running on this laptop with secure sign-in off.

It is active only when ALL of these hold (checked at startup AND on every request):
  1. DHASHU_LOCAL_HARNESS=1 is set explicitly;
  2. AUTH_ENABLED is explicitly off (0/false/no/off; unset means real sign-in is ON);
  3. no production marker is present (production_markers() below);
  4. the request reaches this process directly from loopback (127.0.0.1 / ::1;
     the emulator's 10.0.2.2 arrives as 127.0.0.1), with a local Host header and
     no proxy forwarding header.

When the flag is off the routes are not registered at all. Any failed condition
returns 404 (never 403), indistinguishable from a route that does not exist.
Startup refuses to boot when the flag is set together with any production marker.
Sessions it issues are prefixed "harness_" and are rejected everywhere whenever
the harness is not active (auth_sessions.session_allowed), so a harness token can
never authenticate in production even if one ended up in a production database.
Tokens are never logged.
"""
from __future__ import annotations

import client_ip
import logging
import os
import re
from datetime import datetime, timezone
from urllib.parse import urlsplit

from flask import abort, current_app, g, jsonify, request

FLAG = 'DHASHU_LOCAL_HARNESS'
SESSION_PREFIX = 'harness_'
LOOPBACK_PEERS = frozenset({'127.0.0.1', '::1'})
LOCAL_HOSTNAMES = frozenset({'localhost', '127.0.0.1', '::1'})
# Host header values the local server can legitimately receive: the laptop
# itself, or the Android emulator's alias for it.
ALLOWED_REQUEST_HOSTS = frozenset({'localhost', '127.0.0.1', '::1', '10.0.2.2'})
# Explicit names (any other RAILWAY_* variable is also a marker).
RAILWAY_MARKERS = ('RAILWAY_ENVIRONMENT', 'RAILWAY_ENVIRONMENT_NAME', 'RAILWAY_ENVIRONMENT_ID',
                   'RAILWAY_PROJECT_ID', 'RAILWAY_PROJECT_NAME', 'RAILWAY_SERVICE_ID',
                   'RAILWAY_SERVICE_NAME', 'RAILWAY_DEPLOYMENT_ID', 'RAILWAY_GIT_COMMIT_SHA',
                   'RAILWAY_PUBLIC_DOMAIN', 'RAILWAY_PRIVATE_DOMAIN', 'RAILWAY_STATIC_URL')
FORWARDING_HEADERS = ('X-Forwarded-For', 'X-Forwarded-Host', 'X-Real-IP', 'Forwarded')
USER_ID = re.compile(r'[A-Za-z0-9_:.-]{1,64}')
SEEDED_USER_ID = re.compile(r'(u|test)_[A-Za-z0-9_:.-]{1,60}')
CONFIG_KEY = 'LOCAL_HARNESS_ACTIVE'

log = logging.getLogger('dhashu.local_harness')


def flag_set(env=None) -> bool:
    return (os.environ if env is None else env).get(FLAG, '') == '1'


def auth_enabled(env=None) -> bool:
    # Same parsing as auth.register_auth.
    value = (os.environ if env is None else env).get('AUTH_ENABLED', '')
    return value.strip().lower() not in ('0', 'false', 'no', 'off')


def _non_local_host(url: str) -> bool:
    try:
        host = urlsplit(url).hostname
    except ValueError:
        return True
    return host is None or host.lower() not in LOCAL_HOSTNAMES


def production_markers(env=None) -> list[str]:
    """Names (never values) of every setting that indicates a deployed/production process."""
    env = os.environ if env is None else env
    found = {name for name in RAILWAY_MARKERS if env.get(name)}
    found |= {name for name, value in env.items() if name.startswith('RAILWAY_') and value}
    if env.get('DHASHU_PROCESS_ROLE'):
        found.add('DHASHU_PROCESS_ROLE')
    for name in ('DATABASE_URL', 'ADMIN_REPORT_DATABASE_URL', 'AUTH_PUBLIC_ORIGIN', 'ADMIN_PUBLIC_ORIGIN'):
        value = env.get(name, '')
        if value and _non_local_host(value):
            found.add(name + ' (non-local host)')
    auth_value = env.get('AUTH_ENABLED', '').strip().lower()
    if auth_value in ('1', 'true', 'on', 'yes'):
        found.add('AUTH_ENABLED')
    if env.get('SIGNZY_PRODUCTION_ENABLED', '0') not in ('', '0') or env.get('SIGNZY_ENV', 'preproduction') == 'production':
        found.add('SIGNZY production')
    if env.get('DHASHU_BILLING_LIVE_ACK') or env.get('DHASHU_BILLING_MODE', 'disabled') == 'live':
        found.add('DHASHU_BILLING live')
    return sorted(found)


def active(env=None) -> bool:
    return flag_set(env) and not auth_enabled(env) and not production_markers(env)


def assert_safe_startup(env=None) -> None:
    """Refuse to boot when the harness flag is combined with any production marker."""
    if flag_set(env):
        markers = production_markers(env)
        if markers:
            raise RuntimeError(f'{FLAG}=1 is local-only and refused because production markers are present: '
                               + ', '.join(markers) + '. Unset ' + FLAG + '.')


def request_allowed() -> bool:
    """Every condition, re-checked per request (the environment can change)."""
    if not current_app.config.get(CONFIG_KEY) or not active():
        return False
    if client_ip.socket_peer(request) not in LOOPBACK_PEERS:   # the real connection, never a header
        return False
    if any(request.headers.get(name) for name in FORWARDING_HEADERS):
        return False
    hostname = urlsplit('//' + (request.host or '')).hostname
    return hostname is not None and hostname.lower() in ALLOWED_REQUEST_HOSTS


def _require():
    if not request_allowed():
        abort(404)


def bearer_user_id(get_db):
    """User id for a valid harness bearer token, else None.

    Returns (handled, user_id): handled is True when an Authorization header was
    presented on an allowed harness request, so the caller must not fall back
    to the browser cookie session.
    """
    if 'local_harness_user' in g:
        return g.local_harness_user
    g.local_harness_user = (False, None)
    authorization = request.headers.get('Authorization')
    if authorization is None or not request.path.startswith('/api/v1/') or not request_allowed():
        return g.local_harness_user
    import auth_sessions as sessions
    parts = authorization.split()
    token = parts[1] if len(parts) == 2 and parts[0].lower() == 'bearer' else None
    row = None
    if token and sessions.valid_token(token):
        row = sessions.sql(get_db(), '''SELECT s.id, s.user_id FROM "AuthSession" s JOIN "User" u ON u.id = s.user_id
            WHERE s.access_hash = ? AND s.kind = 'mobile' AND s.revoked_at IS NULL
            AND s.access_expires_at > ? AND s.expires_at > ?''',
            (sessions.digest(token), sessions.now(), sessions.now())).fetchone()
    user_id = row['user_id'] if row and row['id'].startswith(SESSION_PREFIX) else None
    g.local_harness_user = (True, user_id)
    if user_id:
        g.local_harness_session_id = row['id']
    return g.local_harness_user


def bearer_session():
    """The harness session behind this request's bearer token, already checked
    by bearer_user_id() (app.current_user) for this request; else None.

    Same shape the bearer-only routes read from auth.resolve's g.auth_session.
    Never set when the harness is inactive, so it is always None in production.
    """
    handled, user_id = g.get('local_harness_user', (False, None))
    session_id = g.get('local_harness_session_id')
    if not handled or not user_id or not session_id:
        return None
    return {'id': session_id, 'user_id': user_id, 'kind': 'mobile'}


def register(app, get_db) -> bool:
    """Register the /api/v1/dev/* routes only when the harness is active. Returns whether it is."""
    assert_safe_startup()
    app.config[CONFIG_KEY] = active()
    if not app.config[CONFIG_KEY]:
        return False
    import auth_sessions as sessions

    log.warning('!!! LOCAL HARNESS ACTIVE (%s=1): /api/v1/dev/* lets loopback clients sign in as any '
                'seeded user without a password. LOCAL DEVELOPMENT ONLY. Never set this in a deployment. !!!', FLAG)

    def failure(message, status, code):
        # Same shape as auth.failure; api.py's after_request wraps it in the v1 envelope.
        return jsonify(error=message, code=code), status

    @app.get('/api/v1/dev/users')
    def local_harness_users():
        _require()
        # Seeded/synthetic profiles only (generate_users.py u_*, fixed test pairs test_*);
        # any other local User row is never offered by the picker.
        rows = sessions.sql(get_db(), 'SELECT id, journey_state FROM "User" ORDER BY id').fetchall()
        seeded = [row for row in rows if SEEDED_USER_ID.fullmatch(row['id'])][:200]
        return jsonify(users=[{'user_id': row['id'], 'journey_state': row['journey_state']} for row in seeded])

    @app.post('/api/v1/dev/login-as')
    def local_harness_login_as():
        _require()
        body = request.get_json(silent=True)
        user_id = body.get('user_id') if isinstance(body, dict) else None
        if not isinstance(user_id, str) or not USER_ID.fullmatch(user_id):
            return failure('Choose a local user.', 400, 'validation_error')
        if not SEEDED_USER_ID.fullmatch(user_id):
            abort(404)  # only seeded/synthetic profiles (u_*, test_*), same 404 as a missing user
        conn = get_db()
        with sessions.transaction(conn):
            if not sessions.sql(conn, 'SELECT id FROM "User" WHERE id = ?', (user_id,)).fetchone():
                abort(404)
            result = sessions.issue_in_transaction(conn, user_id, 'mobile', harness=True)
        log.warning('Local harness dev login: user_id=%s at=%s peer=%s', user_id,
                    datetime.now(timezone.utc).isoformat(timespec='seconds'), client_ip.socket_peer(request))
        return jsonify(result)

    @app.post('/api/v1/dev/refresh')
    def local_harness_refresh():
        _require()
        body = request.get_json(silent=True)
        token = body.get('refresh_token') if isinstance(body, dict) else None
        result = sessions.refresh(get_db(), token, harness=True) if isinstance(token, str) else None
        return jsonify(result) if result else failure('Sign in again.', 401, 'authentication_required')

    @app.post('/api/v1/dev/logout')
    def local_harness_logout():
        _require()
        handled, user_id = bearer_user_id(get_db)
        if not user_id:
            return failure('Sign in to continue.', 401, 'authentication_required')
        sessions.revoke(get_db(), g.local_harness_session_id, user_id)
        return jsonify(signed_out=True)

    return True
