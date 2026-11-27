"""External return targets must never become web redirect destinations."""

import unittest
from unittest import mock

import auth
from test_segment_efg_routes import RouteTestCase, app_module


class SafeNextTests(unittest.TestCase):
    def test_accepts_only_local_paths(self):
        for path in ('/', '/valid/path', '/valid/path?step=1#details', '/valid%20path'):
            self.assertEqual(auth.safe_next(path), path)

    def test_external_ambiguous_and_malformed_paths_fall_back(self):
        for target in (None, '', 7, 'https://evil.example', 'javascript:alert(1)',
                       '//evil.example', '///evil.example', '/\\evil.example',
                       '/%2fevil.example', '/%252fevil.example', '/%5cevil.example',
                       '/%2525252fevil.example',
                       '/%0d%0aLocation:%20https://evil.example',
                       '/ok\r\nLocation: https://evil.example', '/ok\\evil.example',
                       '/' + 'x' * 5000):
            with self.subTest(target=target):
                self.assertEqual(auth.safe_next(target), '/dashboard')


class SafeReturnRouteTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.login(self.make_user('owner'))

    def test_payment_page_never_renders_an_external_next_link(self):
        with mock.patch.dict('os.environ', {'PAYMENTS_ENABLED': '1'}):
            for target in ('https://evil.example', '//evil.example', '/%2fevil.example'):
                response = self.client.get('/pay/guru', query_string={'next': target})
                self.assertEqual(response.status_code, 200)
                body = response.get_data(as_text=True)
                self.assertIn('name="next" value="/dashboard"', body)
                self.assertNotIn('evil.example', body)
            response = self.client.get('/pay/guru', query_string={'next': '/valid/path'})
            self.assertIn('name="next" value="/valid/path"', response.get_data(as_text=True))

    def test_payment_confirmation_redirects_only_to_a_local_path(self):
        for target, expected in (('https://evil.example', '/dashboard'),
                                 ('//evil.example', '/dashboard'),
                                 ('/valid/path', '/valid/path')):
            response = self.client.post('/pay/guru/confirm', data={'next': target})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers['Location'], expected)

    def test_demo_back_and_referer_use_safe_local_paths(self):
        for target, expected in (('https://evil.example', '/dashboard'),
                                 ('//evil.example', '/dashboard'),
                                 ('/valid/path', '/valid/path')):
            response = self.client.post('/demo/advance', data={'step': 'day', 'back': target})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.headers['Location'], expected)
        response = self.client.post('/demo/advance', data={'step': 'day'},
                                    headers={'Referer': 'https://evil.example/phishing'})
        self.assertEqual(response.headers['Location'], '/dashboard')
        response = self.client.post('/demo/advance', data={'step': 'day'},
                                    headers={'Referer': '/valid/path'})
        self.assertEqual(response.headers['Location'], '/valid/path')

    def test_verification_ignores_untrusted_return_values(self):
        response = self.client.post('/verify/start', data={'next': 'https://evil.example',
                                                            'back': '//evil.example'})
        self.assertEqual(response.headers['Location'], '/verify')

    def test_disabled_demo_and_signed_out_payment_do_not_redirect_to_target(self):
        with mock.patch.dict('os.environ', {'DEMO_MODE': '0'}):
            response = self.client.post('/demo/advance', data={'back': 'https://evil.example'})
            self.assertEqual(response.status_code, 404)
        with self.client.session_transaction() as session:
            session.clear()
        with mock.patch.dict(app_module.app.config, {'AUTH_ENABLED': True}):
            response = self.client.get('/pay/guru?next=https://evil.example')
            self.assertNotEqual(response.headers.get('Location'), 'https://evil.example')
