"""API abuse protection (c-api-abuse). Registered for every request in app.py.

Always on (safe defaults, cannot block normal use):
- HTTP method allow-list: GET HEAD POST PUT PATCH DELETE OPTIONS; anything else 405.
- Body size: request.max_content_length per route. Upload routes (selfie, photo,
  identity capture) DHASHU_MAX_UPLOAD_BYTES (default 3 MB: a 2 MB image as base64
  JSON); every other route DHASHU_MAX_BODY_BYTES (default 1 MB, the same limit
  secure sign-in already set). Over the limit: 413 in the API error envelope.
- JSON only on /api/v1 writes: a body with any other content type gets 415
  (webhooks keep their own verification and are exempt).
- CORS locked: only origins listed in DHASHU_CORS_ORIGINS (comma separated, default
  none = the current behaviour, no cross-origin browser access) get
  Access-Control-Allow-Origin; a preflight from any other origin gets 403.
- Enumeration / scraping detection: many 404/403 answers to one client in a short
  window emits a structured 'abuse_spike' event (log + alert); never personal data,
  the client is a salted hash.

Off by default (DHASHU_ABUSE_LIMITS=1 to enable, AFTER DHASHU_TRUSTED_PROXY is set,
otherwise every member shares the proxy's address and one limit):
- Global per-client limit DHASHU_RATE_GLOBAL (default 600 requests/minute, in memory
  per process) and stricter per-category limits shared by all workers (AuthThrottle):
  search 60/min, upload 20/hour, ai 30/hour. Auth and OTP keep their own limits
  (auth.py, otp_policy.py). Over a limit: 429 with Retry-After.
- Clients over the enumeration threshold are refused (429) for the window.

Per-member write limits (sec-peruser), always on (register_member_limits below):
- Every signed-in member's state-changing request (POST PUT PATCH DELETE), web page
  or /api/v1, counts in one bucket per member per route group (the first segment of
  the matched route rule, so ids in the path cannot mint new buckets):
  DHASHU_RATE_USER_WRITES per minute (default 60, 1-1000; anything else refuses
  startup and, if changed at runtime, fails closed with 503). Keyed on the member id
  (an HMAC, never the raw id), not the address, so members behind one proxy or
  carrier NAT never share a limit and a member cannot dodge it by changing networks.
  Shared by all workers (AuthThrottle). Over the limit: 429 with Retry-After, and an
  event carrying the salted client_ip.client_ip() key, never the member id.
- Signed-out writes are not member-limited (auth/OTP keep their own limits); with
  DHASHU_ABUSE_LIMITS=1 they get the same per-route-group limit keyed on the client
  address from client_ip.client_ip().
- Provider callbacks (Razorpay webhook, Signzy callback), the public waitlist, sign-in
  and the local harness routes are never member-limited.
Backoff on repeated failures (sec-backoff) is not implemented here yet.
"""
import hashlib
import json
import logging
import os
import threading
import time

from flask import jsonify, request

import client_ip

log = logging.getLogger('dhashu.abuse')

ALLOWED_METHODS = {'GET', 'HEAD', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'}
UPLOAD_PATHS = ('/api/v1/profile/avatar/selfie', '/api/v1/identity-capture')   # /profile/photo retired 2026-11-25
CATEGORIES = {
    # category: (path prefixes, limit, window seconds)
    'search': (('/api/v1/discovery',), 60, 60),
    'upload': (UPLOAD_PATHS, 20, 3600),
    'ai': (('/api/v1/guru/', '/api/v1/profile/avatar/generate'), 30, 3600),
}
JSON_EXEMPT = ('/api/v1/webhooks/',)   # the Razorpay webhook lives at /billing/webhooks/razorpay (not /api/v1)
ENUMERATION_LIMIT, ENUMERATION_WINDOW = 50, 600


def _int(name, default):
    try:
        return max(1, int(os.environ.get(name, default)))
    except ValueError:
        return default


def limits_enabled():
    return os.environ.get('DHASHU_ABUSE_LIMITS', '0') == '1'


def cors_origins():
    return {o.strip().rstrip('/') for o in os.environ.get('DHASHU_CORS_ORIGINS', '').split(',') if o.strip()}


def client_key():
    """Salted hash of the client address: usable as a key, useless as personal data."""
    salt = os.environ.get('SECRET_KEY', 'dhashu-local')
    return hashlib.sha256((salt + '|' + client_ip.client_ip(request)).encode()).hexdigest()[:16]


class _Window:
    """Fixed-window counters in memory (per process), thread safe."""

    def __init__(self):
        self.lock, self.counts = threading.Lock(), {}

    def hit(self, key, window, now=None):
        now = time.time() if now is None else now
        with self.lock:
            start, count = self.counts.get(key, (now, 0))
            if now - start >= window:
                start, count = now, 0
            count += 1
            self.counts[key] = (start, count)
            if len(self.counts) > 50_000:              # bound memory: drop expired windows
                self.counts = {k: v for k, v in self.counts.items() if now - v[0] < 3600}
            return count, max(1, int(window - (now - start)))

    def peek(self, key, window, now=None):
        now = time.time() if now is None else now
        with self.lock:
            start, count = self.counts.get(key, (now, 0))
            return 0 if now - start >= window else count

    def reset(self):
        with self.lock:
            self.counts.clear()


GLOBAL = _Window()
MISSES = _Window()
_ALERTED = _Window()


def reset():
    for window in (GLOBAL, MISSES, _ALERTED):
        window.reset()


def event(kind, **fields):
    record = {'event': kind, 'route': request.url_rule.rule if request.url_rule else 'unmatched',
              'method': request.method, 'client': client_key(), **fields}
    log.warning(json.dumps(record, sort_keys=True))
    return record


def _error(status, code, message, retry_after=None):
    # Same flat shape as auth.failure(); the API envelope step turns it into
    # {data: null, error: {code, message, detail, reference}} like every other error.
    response = jsonify(error=message, code=code)
    response.status_code = status
    if retry_after:
        response.headers['Retry-After'] = str(retry_after)
    return response


def _category(path):
    for name, (prefixes, limit, window) in CATEGORIES.items():
        if path.startswith(prefixes):
            return name, limit, window
    return None


def register(app):
    @app.before_request
    def abuse_before():
        if request.method not in ALLOWED_METHODS:
            return _error(405, 'method_not_allowed', 'This method is not allowed.')
        path = request.path
        upload = path.startswith(UPLOAD_PATHS)
        request.max_content_length = (_int('DHASHU_MAX_UPLOAD_BYTES', 3 * 1024 * 1024) if upload
                                      else _int('DHASHU_MAX_BODY_BYTES', 1024 * 1024))
        if request.content_length and request.content_length > request.max_content_length:
            event('body_too_large', size=request.content_length)
            return _error(413, 'payload_too_large', 'This request is too large.')
        origin = request.headers.get('Origin')
        if request.method == 'OPTIONS' and origin and request.headers.get('Access-Control-Request-Method'):
            if origin.rstrip('/') not in cors_origins():
                return _error(403, 'origin_not_allowed', 'This origin is not allowed.')
            return app.response_class(status=204)
        if (path.startswith('/api/v1/') and request.method in ('POST', 'PUT', 'PATCH')
                and (request.content_length or 0) > 0 and not request.is_json and not path.startswith(JSON_EXEMPT)):
            return _error(415, 'unsupported_media_type', 'Use application/json.')
        if not limits_enabled() or not path.startswith('/api/'):
            return None
        key = client_key()
        if MISSES.peek(key, ENUMERATION_WINDOW) >= ENUMERATION_LIMIT:
            return _error(429, 'rate_limited', 'Too many requests. Please wait and try again.', ENUMERATION_WINDOW)
        count, retry = GLOBAL.hit(key, 60)
        if count > _int('DHASHU_RATE_GLOBAL', 600):
            if count == _int('DHASHU_RATE_GLOBAL', 600) + 1:
                event('rate_limited', scope='global')
            return _error(429, 'rate_limited', 'Too many requests. Please wait and try again.', retry)
        category = _category(path) if request.method != 'GET' or path.startswith('/api/v1/discovery') else None
        if category:
            import auth_sessions
            from app import get_db
            name, limit, window = category
            if not auth_sessions.throttle(get_db(), ['abuse:' + name + ':' + key], limit, window):
                event('rate_limited', scope=name)
                return _error(429, 'rate_limited', 'Too many requests. Please wait and try again.', window)
        return None

    @app.after_request
    def abuse_after(response):
        origin = request.headers.get('Origin')
        if origin and origin.rstrip('/') in cors_origins():
            response.headers['Access-Control-Allow-Origin'] = origin.rstrip('/')
            response.headers['Vary'] = 'Origin'
            if request.method == 'OPTIONS':
                response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, PATCH, DELETE'
                response.headers['Access-Control-Allow-Headers'] = 'Authorization, Content-Type, X-Request-ID'
                response.headers['Access-Control-Max-Age'] = '600'
        if request.path.startswith('/api/') and response.status_code in (403, 404):
            key = client_key()
            count, _ = MISSES.hit(key, ENUMERATION_WINDOW)
            if count >= ENUMERATION_LIMIT and _ALERTED.hit(key, ENUMERATION_WINDOW)[0] == 1:
                event('abuse_spike', misses=count, window_seconds=ENUMERATION_WINDOW)
                try:
                    import alerts
                    alerts.emit('abuse_spike', kind='enumeration')
                except Exception:   # noqa: BLE001
                    pass
        return response

    @app.errorhandler(413)
    def too_large(_exc):
        if request.path.startswith('/api/'):
            event('body_too_large', size=request.content_length or 0)
            return _error(413, 'payload_too_large', 'This request is too large.')
        return 'This request is too large.', 413


# -- sec-peruser: per-member write limits -------------------------------------
WRITE_METHODS = frozenset({'POST', 'PUT', 'PATCH', 'DELETE'})
MEMBER_WINDOW_SECONDS = 60
MEMBER_EXEMPT_PREFIXES = ('/api/v1/auth/', '/api/v1/dev/', '/billing/webhooks/', '/public/', '/static/')
MEMBER_EXEMPT_PATHS = {'/signin'}


class LimitUnavailable(Exception):
    """The member limit cannot be evaluated: refuse the write (fail closed)."""


def member_write_limit(environ=None):
    """DHASHU_RATE_USER_WRITES, strictly 1-1000. A bad value never silently disables
    member protection: it raises (startup refusal / 503 at request time)."""
    raw = (os.environ if environ is None else environ).get('DHASHU_RATE_USER_WRITES', '60')
    if not isinstance(raw, str) or not 1 <= len(raw) <= 4 or not raw.isascii() or not raw.isdecimal():
        raise LimitUnavailable('DHASHU_RATE_USER_WRITES must be a whole number from 1 to 1000.')
    limit = int(raw)
    if not 1 <= limit <= 1000:
        raise LimitUnavailable('DHASHU_RATE_USER_WRITES must be a whole number from 1 to 1000.')
    return limit


def route_group():
    """Canonical bucket name from the matched rule (never the raw path)."""
    rule = request.url_rule.rule if request.url_rule is not None else request.path
    if rule.startswith('/api/v1/'):
        return 'api:' + (rule[len('/api/v1/'):].partition('/')[0] or 'root')
    return 'web:' + (rule.lstrip('/').partition('/')[0] or 'root')


def _member_exempt(path):
    return (path in MEMBER_EXEMPT_PATHS or path.startswith(MEMBER_EXEMPT_PREFIXES)
            or request.endpoint == 'signzy_digilocker_callback')


def check_member_write(user_id, get_db):
    """None when this write may proceed, else the 429/503 response. user_id is the
    already-authenticated member, or None when signed out."""
    import auth
    import auth_sessions
    group = route_group()
    if user_id:
        bucket = auth.key('member-write:' + user_id + ':' + group)   # HMAC: no member id at rest
    elif limits_enabled():
        bucket = auth.key('client-write:' + client_ip.client_ip(request) + ':' + group)
    else:
        return None
    try:
        allowed = auth_sessions.throttle(get_db(), [bucket], limit=member_write_limit(),
                                         seconds=MEMBER_WINDOW_SECONDS)
    except LimitUnavailable:
        return _limit_response(503, 'rate_limit_unavailable', 'Please try again later.')
    except Exception as error:   # noqa: BLE001 - DB failure: fail closed, never leak the error text
        log.error('Member write limit unavailable: %s', type(error).__name__)
        return _limit_response(503, 'rate_limit_unavailable', 'Please try again later.')
    if allowed:
        return None
    event('rate_limited', scope='member' if user_id else 'client_write', group=group)
    return _limit_response(429, 'rate_limited', 'Too many requests. Please wait and try again.',
                           MEMBER_WINDOW_SECONDS)


def _limit_response(status, code, message, retry_after=None):
    if request.path.startswith('/api/'):
        return _error(status, code, message, retry_after)
    from flask import make_response
    response = make_response(message, status)
    response.mimetype = 'text/plain'
    if retry_after:
        response.headers['Retry-After'] = str(retry_after)
    return response


def register_member_limits(app, *, current_user, get_db):
    """Register AFTER sign-in (auth.register_auth / local_harness.register) so the
    member is resolved exactly as every route resolves it. Validates the setting now:
    a bad DHASHU_RATE_USER_WRITES refuses startup."""
    member_write_limit()

    @app.before_request
    def member_write_limit_check():
        if request.method not in WRITE_METHODS or _member_exempt(request.path):
            return None
        user = current_user()
        return check_member_write(user['user_id'] if user else None, get_db)
