"""Code-side alert events (mon-alerts).

emit(event, **fields) writes one structured WARNING line {"alert": event, ...}
on the 'dhashu.alert' logger and, when Sentry is active, a Sentry message with
the same name, so alert rules can match on either. Fields must be counts,
names and ids, never personal data. Each event is rate-limited per process
(DHASHU_ALERT_COOLDOWN_SECONDS, default 300) so a storm is one alert.

Events:
  server_error_spike      >= DHASHU_ALERT_5XX_PER_MINUTE (default 20) 5xx in 60 s
  circuit_open            a provider breaker opened (provider=...); OTP providers
                          (twilio, msg91) also emit otp_provider_down
  stuck_verification_jobs BGV requests / provider jobs running longer than
                          DHASHU_ALERT_STUCK_MINUTES (default 15)
  payment_webhook_failure the Razorpay webhook refused or failed a delivery
                          (billing_api.webhook_failure; reason=code, status=...);
                          duplicate deliveries are a silent success, never an alert
  abuse_spike             emitted by request-abuse protection (c-api-abuse)
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections import deque

log = logging.getLogger('dhashu.alert')
_lock = threading.Lock()
_last_sent: dict = {}
_errors = deque()
OTP_PROVIDERS = {'twilio', 'msg91'}


def _cooldown():
    try:
        return max(0, int(os.environ.get('DHASHU_ALERT_COOLDOWN_SECONDS', '300')))
    except ValueError:
        return 300


def emit(event, clock=time.monotonic, **fields):
    """Emit an alert unless the same event fired within the cooldown. Returns True if emitted."""
    now = clock()
    key = event + ':' + str(fields.get('provider', ''))   # one cooldown per event and provider
    with _lock:
        last = _last_sent.get(key)
        if last is not None and now - last < _cooldown():
            return False
        _last_sent[key] = now
    payload = {'alert': event, **{k: v for k, v in fields.items() if isinstance(v, (str, int, float, bool)) or v is None}}
    log.warning(json.dumps(payload, separators=(',', ':')))
    try:
        import sentry_sdk
        if sentry_sdk.get_client().is_active():
            sentry_sdk.capture_message('alert:' + event, level='warning', tags={k: str(v) for k, v in payload.items()})
    except Exception:   # noqa: BLE001 — alerting never breaks the caller
        pass
    if event == 'circuit_open' and fields.get('provider') in OTP_PROVIDERS:
        emit('otp_provider_down', clock=clock, provider=fields['provider'])
    return True


def record_server_error(clock=time.monotonic):
    """Called for every 5xx; emits server_error_spike past the per-minute threshold."""
    now = clock()
    try:
        threshold = max(1, int(os.environ.get('DHASHU_ALERT_5XX_PER_MINUTE', '20')))
    except ValueError:
        threshold = 20
    with _lock:
        _errors.append(now)
        while _errors and now - _errors[0] > 60:
            _errors.popleft()
        count = len(_errors)
    if count >= threshold:
        return emit('server_error_spike', clock=clock, count_last_minute=count)
    return False


def check_stuck_jobs(conn, clock=time.time):
    """Worker check: verification work running far longer than it should. Returns the count."""
    import db
    try:
        minutes = max(1, int(os.environ.get('DHASHU_ALERT_STUCK_MINUTES', '15')))
    except ValueError:
        minutes = 15
    cutoff = clock() - minutes * 60
    from datetime import datetime, timezone
    iso_cutoff = datetime.fromtimestamp(cutoff, timezone.utc).isoformat()
    stuck = sum(1 for r in db.fetch_all(conn, 'BgvRequest', state='processing') if (r.get('updated_at') or '') < iso_cutoff)
    stuck += sum(1 for r in db.fetch_all(conn, 'ProviderJob', state='running') if (r.get('updated_at') or 0) < cutoff)
    if stuck:
        emit('stuck_verification_jobs', count=stuck, minutes=minutes)
    return stuck


def reset():
    with _lock:
        _last_sent.clear()
        _errors.clear()
