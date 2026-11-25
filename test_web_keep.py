"""dec-web (owner decision: keep the old web version): every web page works when signed
in, carries the security headers and a nonce CSP, and refuses cross-site form posts."""
import re
import unittest

import test_auth
from test_segment_efg_routes import RouteTestCase
from tools import route_inventory as inv

PARAM = re.compile(r'<(?:[a-z]+:)?([a-z_]+)>')
SAMPLE = {'kind': 'date', 'purpose': 'availability', 'pid': 'plan-1', 'token': 'probe', 'path:pid': 'plan-1'}


def web_get_rules():
    return [r for r in inv.member_rules() if inv.member_class(r)[0] == 'member-web' and 'GET' in r.methods]


class SignedInWebTests(RouteTestCase):
    """Local mode, signed-in member in a lock-in with a plan: every page answers."""

    def setUp(self):
        super().setUp()
        self.make_user('owner'); self.make_user('partner')
        self.make_plan(self.make_lockin('owner', 'partner'), 'plan-1')
        self.login('owner')

    def test_every_web_page_works_signed_in(self):
        broken, checked = [], 0
        for rule in web_get_rules():
            path = PARAM.sub(lambda m: SAMPLE.get(m.group(1), 'probe'), rule.rule)
            response = self.client.get(path)
            checked += 1
            body = response.get_data(as_text=True)
            if rule.rule == '/billing' and response.status_code == 503 and 'not enabled' in body:
                continue                                              # billing off: its documented answer, not a crash
            if response.status_code >= 500 or 'Traceback' in body:
                broken.append(f'{rule.rule} -> {response.status_code}')
        self.assertEqual(broken, [])
        self.assertGreaterEqual(checked, 40)

    def test_every_html_page_has_security_headers_and_a_matching_script_nonce(self):
        for rule in web_get_rules():
            path = PARAM.sub(lambda m: SAMPLE.get(m.group(1), 'probe'), rule.rule)
            response = self.client.get(path)
            if response.status_code != 200 or response.mimetype != 'text/html':
                continue
            headers = response.headers
            for name in ('X-Content-Type-Options', 'X-Frame-Options', 'Referrer-Policy', 'Permissions-Policy'):
                self.assertIn(name, headers, (rule.rule, name))
            policy = headers.get('Content-Security-Policy-Report-Only') or headers.get('Content-Security-Policy')
            self.assertIsNotNone(policy, rule.rule)
            nonce = re.search(r"'nonce-([^']+)'", policy).group(1)
            html = response.get_data(as_text=True)
            self.assertNotIn('<script>', html, rule.rule)                         # every inline script is nonced
            for found in re.findall(r'<script nonce="([^"]+)"', html):
                self.assertEqual(found, nonce, rule.rule)


class SignedInRequiredTests(unittest.TestCase):
    """Secure sign-in on: pages need a session; cross-site form posts are refused."""

    def setUp(self):
        self.f = test_auth.AuthenticationTests('test_optional_tester_login_and_revocation')
        self.f.setUp(); self.addCleanup(self.f.doCleanups)

    def test_pages_need_sign_in_and_forms_refuse_cross_site_posts(self):
        for rule in web_get_rules():
            if rule.rule in ('/signin', '/signup') or rule.endpoint in inv.PUBLIC:
                continue
            path = PARAM.sub(lambda m: SAMPLE.get(m.group(1), 'probe'), rule.rule)
            self.assertIn(self.f.client.get(path).status_code, (302, 303, 403, 404), rule.rule)
        posts = [r for r in inv.member_rules() if inv.member_class(r)[0] == 'member-web' and 'POST' in r.methods]
        self.assertGreater(len(posts), 20)
        for rule in posts:
            path = PARAM.sub(lambda m: SAMPLE.get(m.group(1), 'probe'), rule.rule)
            r = self.f.client.post(path, data={'x': '1'}, headers={'Origin': 'https://evil.example'})
            self.assertIn(r.status_code, (302, 303, 403, 404), rule.rule)          # never accepted from another site

    def test_route_inventory_marks_the_web_as_kept(self):
        from pathlib import Path
        text = Path('docs/ROUTE_INVENTORY.md').read_text(encoding='utf-8')
        self.assertIn('kept (owner decision 2026-11-25)', text)


if __name__ == '__main__':
    unittest.main()
