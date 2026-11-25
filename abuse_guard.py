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
Per-member limits, real-IP extraction and backoff are Adithya's (sec-peruser,
sec-ip, sec-backoff); this module keys on client_ip.client_ip() so it uses theirs.
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
UPLOAD_PATHS = ('/api/v1/profile/photo', '/api/v1/profile/avatar/selfie', '/api/v1/identity-capture')
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
