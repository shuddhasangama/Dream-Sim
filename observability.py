"""Request IDs, structured JSON request logs and optional Sentry (mon-sentry).

- Every request gets a request id: a well-formed incoming X-Request-ID
  (8-64 of [A-Za-z0-9-]) is kept, anything else is replaced. It is returned
  in the X-Request-ID header and as `reference` in API error bodies, and
  appears in every request log line, so a member's support screenshot can be
  traced to one log line.
- One JSON log line per request: level, ts, request_id, method, route (the URL
  RULE such as /api/v1/matches/<match_id>/actions, never the concrete path,
  query string, body or any personal data), status, duration_ms.
  DHASHU_LOG_FORMAT=text turns it into a plain line.
- Sentry starts only when SENTRY_DSN is set (off locally). send_default_pii is
  off (sentry-sdk 3 data_collection) and scrub() strips request bodies, cookies, headers, query strings, user
  data, emails and phone numbers from every event before it leaves the process.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid

from flask import g, request

REQUEST_ID = re.compile(r'[A-Za-z0-9-]{8,64}')
EMAIL = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')
# International (+country code) or Indian mobile (10 digits starting 6-9, optionally 5+5).
# Deliberately does not match ISO dates (2026-11-25) or Unix timestamps (17...).
PHONE = re.compile(r'(?<![\w+])(?:\+\d{1,3}[\s-]?\d[\d\s-]{6,12}\d|[6-9]\d{4}[\s-]?\d{5})(?![\w-])')
log = logging.getLogger('dhashu.request')


def mask(text):
    """Mask emails and phone numbers in free text (logs, error messages)."""
    if not isinstance(text, str):
        return text
    return PHONE.sub('[phone]', EMAIL.sub('[email]', text))


def current_request_id():
    try:
        return g.get('request_id')
    except RuntimeError:
        return None


def register(app):
    @app.before_request
    def assign_request_id():
        incoming = request.headers.get('X-Request-ID', '')
        g.request_id = incoming if REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex
        g.request_started = time.perf_counter()

    @app.after_request
    def log_request(response):
        rid = current_request_id()
        if rid:
            response.headers['X-Request-ID'] = rid
        started = g.get('request_started')
        entry = {
            'level': 'warning' if response.status_code >= 500 else 'info',
            'ts': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'request_id': rid, 'method': request.method,
            'route': request.url_rule.rule if request.url_rule else 'unmatched',
            'status': response.status_code,
            'duration_ms': round((time.perf_counter() - started) * 1000, 1) if started else None,
        }
        if response.status_code >= 500:
            try:
                import alerts
                alerts.record_server_error()
            except Exception:   # noqa: BLE001
                pass
        if os.environ.get('DHASHU_LOG_REQUESTS', '1') == '1':
            line = json.dumps(entry, separators=(',', ':')) if os.environ.get('DHASHU_LOG_FORMAT', 'json') == 'json' \
                else '{method} {route} {status} {duration_ms}ms rid={request_id}'.format(**entry)
            (log.warning if response.status_code >= 500 else log.info)(line)
        return response

    install_log_masking()
    init_sentry()


_MASKING_INSTALLED = False


def install_log_masking():
    """sec-logs: mask emails and phone numbers in EVERY log record of the process
    (any logger, any handler) by wrapping the log record factory once."""
    global _MASKING_INSTALLED
    if _MASKING_INSTALLED:
        return
    previous = logging.getLogRecordFactory()

    def factory(*args, **kwargs):
        record = previous(*args, **kwargs)
        try:
            message = record.getMessage()
            masked = mask(message)
            if masked != message:
                record.msg, record.args = masked, ()
        except Exception:   # noqa: BLE001 — logging must never fail
            pass
        return record
    logging.setLogRecordFactory(factory)
    _MASKING_INSTALLED = True


# ── Sentry ──────────────────────────────────────────────────────────────
_SENSITIVE_HEADERS = {'authorization', 'cookie', 'set-cookie', 'x-forwarded-for', 'x-real-ip', 'cf-connecting-ip'}


def _scrub_value(value):
    if isinstance(value, str):
        return mask(value)
    if isinstance(value, dict):
        return {k: ('[filtered]' if str(k).lower() in _SENSITIVE_HEADERS or 'token' in str(k).lower()
                    or 'password' in str(k).lower() or 'secret' in str(k).lower() else _scrub_value(v))
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_scrub_value(v) for v in value]
    return value


def scrub(event, hint=None):
    """before_send: remove personal data from a Sentry event (also used for breadcrumbs)."""
    event = dict(event)
    event.pop('user', None)
    req = dict(event.get('request') or {})
    for key in ('data', 'cookies', 'query_string', 'env'):
        req.pop(key, None)
    if 'headers' in req:
        req['headers'] = {k: v for k, v in (req['headers'] or {}).items() if k.lower() not in _SENSITIVE_HEADERS}
    if 'url' in req:
        req['url'] = str(req['url']).split('?', 1)[0]
    if req:
        event['request'] = req
    for key in ('message', 'logentry', 'extra', 'contexts', 'breadcrumbs', 'exception'):
        if key in event:
            event[key] = _scrub_value(event[key])
    event.setdefault('tags', {})
    if current_request_id():
        event['tags'] = {**event['tags'], 'request_id': current_request_id()}
    return event


def init_sentry(transport=None):
    """Initialise Sentry only when SENTRY_DSN is set. Returns True when active."""
    dsn = os.environ.get('SENTRY_DSN', '').strip()
    if not dsn:
        return False
    import sentry_sdk
    from sentry_sdk.integrations.flask import FlaskIntegration
    # sentry-sdk 3: data_collection replaces send_default_pii. Collect no user info, bodies,
    # query data or frame variables; scrub() is a second layer for everything else.
    options = dict(dsn=dsn, integrations=[FlaskIntegration()],
                   data_collection={'user_info': False, 'http_bodies': [], 'database_query_data': False,
                                    'stack_frame_variables': False},
                   before_send=scrub, before_breadcrumb=lambda crumb, hint: _scrub_value(crumb),
                   traces_sample_rate=float(os.environ.get('SENTRY_TRACES_SAMPLE_RATE', '0') or 0),
                   environment=os.environ.get('SENTRY_ENVIRONMENT', 'production'),
                   release=os.environ.get('RAILWAY_GIT_COMMIT_SHA', '')[:12] or None, max_request_body_size='never')
    if transport is not None:
        options['transport'] = transport
    sentry_sdk.init(**options)
    return True
