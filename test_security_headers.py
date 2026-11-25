"""sec-headers: every response carries the security headers; HTML gets a nonce CSP."""
import os
import re
from unittest import mock

import generate_users
from test_segment_efg_routes import RouteTestCase

BASE = {'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY',
        'Referrer-Policy': 'strict-origin-when-cross-origin'}


class SecurityHeaderTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        users = generate_users.generate_users(3, seed=4)
        generate_users.seed_db(self.conn, users); self.conn.commit()
        self.client.post('/login/' + users[0]['user_id'])

    def test_api_responses(self):
        for path in ('/api/v1/health', '/api/v1/me', '/api/v1/missing'):
            headers = self.client.get(path).headers
            for name, value in BASE.items():
                self.assertEqual(headers[name], value, (path, name))
            self.assertIn('camera=()', headers['Permissions-Policy'])
            self.assertEqual(headers['Content-Security-Policy'], "default-src 'none'; frame-ancestors 'none'")

    def test_html_policy_is_report_only_by_default_and_enforced_on_request(self):
        page = self.client.get('/stats')
        self.assertEqual(page.status_code, 200)
        self.assertIn('Content-Security-Policy-Report-Only', page.headers)
        self.assertNotIn('Content-Security-Policy', page.headers)
        with mock.patch.dict(os.environ, {'DHASHU_CSP_MODE': 'enforce'}):
            page = self.client.get('/stats')
        policy = page.headers['Content-Security-Policy']
        for directive in ("frame-ancestors 'none'", "object-src 'none'", "base-uri 'self'", "default-src 'self'"):
            self.assertIn(directive, policy)
        self.assertNotIn("script-src 'self' 'unsafe-inline'", policy)
        header_nonce = re.search(r"'nonce-([^']+)'", policy).group(1)
        html = page.get_data(as_text=True)
        page_nonces = set(re.findall(r'<script nonce="([^"]+)"', html))
        self.assertEqual(page_nonces, {header_nonce})                    # every inline script is allowed, nothing else
        self.assertNotIn('<script>', html)
        again = self.client.get('/stats').headers.get('Content-Security-Policy-Report-Only', '')
        self.assertNotIn(header_nonce, again)                            # fresh nonce per request

    def test_hsts_only_over_https(self):
        self.assertNotIn('Strict-Transport-Security', self.client.get('/api/v1/health').headers)
        secure = self.client.get('/api/v1/health', headers={'X-Forwarded-Proto': 'https'})
        self.assertEqual(secure.headers['Strict-Transport-Security'], 'max-age=31536000; includeSubDomains')
        with mock.patch.dict(os.environ, {'DHASHU_HSTS_SECONDS': '0'}):
            self.assertNotIn('Strict-Transport-Security',
                             self.client.get('/api/v1/health', headers={'X-Forwarded-Proto': 'https'}).headers)
