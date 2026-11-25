"""Security headers on every response (sec-headers).

Always: X-Content-Type-Options, X-Frame-Options, Referrer-Policy,
Permissions-Policy, and HSTS on HTTPS requests (direct or behind the proxy).

Content-Security-Policy:
- API/JSON responses: "default-src 'none'; frame-ancestors 'none'" (enforced).
- HTML pages: a strict policy with a per-request script nonce (templates use
  nonce="{{ csp_nonce() }}" on their inline scripts) and only the external
  hosts the pages use (Razorpay checkout, Google Fonts). DHASHU_CSP_MODE:
  report-only (default: sent as Content-Security-Policy-Report-Only, so a
  missed inline script cannot break a live page) | enforce | off.
DHASHU_HSTS_SECONDS (default 31536000; 0 disables).
"""
import os
import secrets

from flask import g, request

PERMISSIONS = ('accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), '
               'microphone=(), payment=(self "https://checkout.razorpay.com" "https://api.razorpay.com"), usb=()')


def nonce():
    if 'csp_nonce' not in g:
        g.csp_nonce = secrets.token_urlsafe(16)
    return g.csp_nonce


def html_policy(script_nonce):
    return '; '.join([
        "default-src 'self'",
        f"script-src 'self' 'nonce-{script_nonce}' https://checkout.razorpay.com",
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com",
        "font-src 'self' https://fonts.gstatic.com",
        "img-src 'self' data:",
        "connect-src 'self' https://*.razorpay.com",
        "frame-src https://api.razorpay.com https://checkout.razorpay.com",
        "frame-ancestors 'none'",
        "base-uri 'self'",
        "form-action 'self'",
        "object-src 'none'",
    ])


def _https():
    return request.is_secure or request.headers.get('X-Forwarded-Proto', '').split(',')[0].strip().lower() == 'https'


def register(app):
    app.jinja_env.globals['csp_nonce'] = nonce

    @app.after_request
    def add_security_headers(response):
        headers = response.headers
        headers.setdefault('X-Content-Type-Options', 'nosniff')
        headers.setdefault('X-Frame-Options', 'DENY')
        headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
        headers.setdefault('Permissions-Policy', PERMISSIONS)
        hsts = os.environ.get('DHASHU_HSTS_SECONDS', '31536000')
        if _https() and hsts.isdigit() and int(hsts) > 0:
            headers.setdefault('Strict-Transport-Security', f'max-age={int(hsts)}; includeSubDomains')
        mode = os.environ.get('DHASHU_CSP_MODE', 'report-only')
        if response.mimetype == 'text/html' and mode in ('enforce', 'report-only'):
            name = 'Content-Security-Policy' if mode == 'enforce' else 'Content-Security-Policy-Report-Only'
            headers.setdefault(name, html_policy(nonce()))
        elif response.mimetype != 'text/html':
            headers.setdefault('Content-Security-Policy', "default-src 'none'; frame-ancestors 'none'")
        return response
