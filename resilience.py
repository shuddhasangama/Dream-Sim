"""Circuit breakers for outbound provider calls (c-resilience).

A provider that is timing out or failing must not take the app down with it:
every request would otherwise wait the full timeout. After FAILURES
consecutive outage failures (timeouts, network errors, HTTP 5xx) a breaker
OPENS: calls fail immediately with CircuitOpen for RESET seconds. Then one
trial call is let through (HALF-OPEN): success closes the breaker, failure
re-opens it. HTTP 4xx answers are the provider working (our request was bad)
and never count as outages.

CircuitOpen is a ConnectionError, so every caller's existing "provider
unavailable" path (OTP delivery error, Guru guided fallback, Signzy receipt,
Razorpay 503) handles it with no new code. Per process; thread-safe.

    DHASHU_BREAKER_FAILURES       consecutive failures before opening (default 5)
    DHASHU_BREAKER_RESET_SECONDS  seconds open before a trial call (default 30)
"""
from __future__ import annotations

import logging
import os
import threading
import time
import urllib.error

log = logging.getLogger('dhashu.resilience')


class CircuitOpen(ConnectionError):
    def __init__(self, name):
        super().__init__(f'{name} temporarily unavailable (circuit open)')
        self.name = name


def _setting(name, default, low, high):
    try:
        return max(low, min(high, float(os.environ.get(name, default))))
    except ValueError:
        return default


class CircuitBreaker:
    def __init__(self, name, failures=None, reset=None, clock=time.monotonic):
        self.name = name
        self.threshold = int(failures or _setting('DHASHU_BREAKER_FAILURES', 5, 1, 100))
        self.reset = float(reset or _setting('DHASHU_BREAKER_RESET_SECONDS', 30, 1, 3600))
        self.clock = clock
        self._lock = threading.Lock()
        self.state = 'closed'
        self.failures = 0
        self.opened_at = 0.0
        self._trial = False

    def allow(self):
        with self._lock:
            if self.state == 'closed':
                return True
            if self.state == 'open' and self.clock() - self.opened_at >= self.reset:
                self.state, self._trial = 'half_open', False
            if self.state == 'half_open' and not self._trial:
                self._trial = True
                return True
            return False

    def success(self):
        with self._lock:
            if self.state != 'closed':
                log.warning('Circuit closed: %s', self.name)
            self.state, self.failures, self._trial = 'closed', 0, False

    def failure(self):
        with self._lock:
            self.failures += 1
            if self.state == 'half_open' or self.failures >= self.threshold:
                if self.state != 'open':
                    log.warning('Circuit OPEN: %s after %s failure(s)', self.name, self.failures)
                    _alert(self.name)
                self.state, self.opened_at, self._trial = 'open', self.clock(), False


_BREAKERS: dict = {}
_REGISTRY_LOCK = threading.Lock()


def breaker(name):
    with _REGISTRY_LOCK:
        if name not in _BREAKERS:
            _BREAKERS[name] = CircuitBreaker(name)
        return _BREAKERS[name]


def snapshot():
    return {name: b.state for name, b in sorted(_BREAKERS.items())}


def reset_all():
    with _REGISTRY_LOCK:
        _BREAKERS.clear()


def _is_outage(exc):
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code >= 500
    return isinstance(exc, (OSError, TimeoutError))   # URLError, socket errors, timeouts


def call(name, fn, *args, **kwargs):
    """Run one outbound call through the named breaker. Re-raises whatever the call
    raised (callers keep their handling); raises CircuitOpen without calling when open."""
    guard = breaker(name)
    if not guard.allow():
        raise CircuitOpen(name)
    try:
        result = fn(*args, **kwargs)
    except Exception as exc:
        guard.failure() if _is_outage(exc) else guard.success()
        raise
    guard.success()
    return result


def _alert(name):
    try:
        import alerts
        alerts.emit('circuit_open', provider=name)
    except Exception:   # noqa: BLE001 — alerting must never break the call path
        pass
