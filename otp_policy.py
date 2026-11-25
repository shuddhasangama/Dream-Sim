"""SMS one-time-code limits (sec-otp). Each SMS costs money and can be abused
(SMS pumping), so sending is limited three ways:

  DHASHU_OTP_COUNTRIES          dial codes allowed to receive codes (default "91")
  DHASHU_OTP_PER_NUMBER_DAY     codes per number per 24 h (default 5); checked for
                                EVERY request, known number or not, so the limit
                                itself cannot reveal which numbers have accounts
  DHASHU_OTP_GLOBAL_PER_HOUR    real SMS sends per hour across all numbers (default
                                300). When reached, every OTP request is refused
                                (503 otp_paused) until the hour ends and the
                                alert 'otp_global_breaker' fires once.
Counters live in AuthThrottle (shared by all workers and replicas).
"""
import os

import auth_sessions as sessions


def _int(name, default, low, high):
    try:
        return max(low, min(high, int(os.environ.get(name, default))))
    except ValueError:
        return default


def countries():
    return [c.strip().lstrip('+') for c in os.environ.get('DHASHU_OTP_COUNTRIES', '91').split(',') if c.strip()]


def country_allowed(destination):
    return isinstance(destination, str) and any(destination.startswith('+' + code) for code in countries())


def per_number_day():
    return _int('DHASHU_OTP_PER_NUMBER_DAY', 5, 1, 50)


def global_per_hour():
    return _int('DHASHU_OTP_GLOBAL_PER_HOUR', 300, 1, 100000)


def _global_key():
    import auth
    return auth.key('otp-global-sends')


def globally_paused(conn):
    row = sessions.sql(conn, 'SELECT attempts, expires_at FROM "AuthThrottle" WHERE id = ?', (_global_key(),)).fetchone()
    return bool(row and row['expires_at'] > sessions.now() and row['attempts'] >= global_per_hour())


def record_send(conn):
    """Count one real SMS send; emit the breaker alert when this send hits the limit."""
    allowed = sessions.throttle(conn, [_global_key()], global_per_hour() - 1, 3600)
    if not allowed:
        try:
            import alerts
            alerts.emit('otp_global_breaker', limit_per_hour=global_per_hour())
        except Exception:   # noqa: BLE001
            pass
    return allowed
