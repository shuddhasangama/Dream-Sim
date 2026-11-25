"""c-security-suite: verifies every Group 4 safeguard across the whole route surface.

- the route inventory is current and every route has an access class;
- every member API route refuses a request without sign-in (401), every web page
  redirects to sign-in, simulation routes are 404 with sign-in on;
- a member can never read or change another member's lock-in, date plan or couple
  (positive control: the owner can);
- admin routes need an admin session; owner routes need the owner role;
- JSON responses never carry secret-bearing keys (runtime trim + snapshot of
  personal-looking fields: a NEW personal field fails this test).
"""
import json
import re
import unittest
from pathlib import Path

import db
import response_trim
import test_admin_dashboard
import test_auth
from test_segment_efg_routes import RouteTestCase
from tools import route_inventory as inv

PARAM = re.compile(r'<(?:[a-z]+:)?([a-z_]+)>')
WRITE = ('POST', 'PUT', 'PATCH', 'DELETE')


def rule_methods(rule):
    return sorted(m for m in rule.methods if m not in ('HEAD', 'OPTIONS'))


class InventoryTests(unittest.TestCase):
    def test_inventory_is_current(self):
        self.assertEqual(inv.main(['--check']), 0, 'run: python tools/route_inventory.py')

    def test_public_member_routes_are_exactly_the_reviewed_list(self):
        public = {r.endpoint for r in inv.member_rules() if inv.member_class(r)[0] == 'public'}
        self.assertEqual(public, set(inv.PUBLIC))


class RetiredRouteTests(RouteTestCase):
    def test_every_retired_route_answers_404_even_when_signed_in(self):
        self.make_user('owner'); self.login('owner')
        self.assertTrue(inv.RETIRED)
        for (method, path) in inv.RETIRED:
            self.assertEqual(self.client.open(path, method=method, json={}).status_code, 404, (method, path))
            self.assertFalse(any(r.rule == path and method in r.methods for r in inv.member_rules()), path)
        self.assertIn('## Removed routes (answer 404)', Path('docs/ROUTE_INVENTORY.md').read_text(encoding='utf-8'))


class SignedOutTests(unittest.TestCase):
    """Secure sign-in ON (production shape)."""

    def setUp(self):
        self.f = test_auth.AuthenticationTests('test_optional_tester_login_and_revocation')
        self.f.setUp(); self.addCleanup(self.f.doCleanups)

    def each(self, access):
        for rule in inv.member_rules():
            if inv.member_class(rule)[0] == access:
                path = PARAM.sub('probe-x', rule.rule)
                for method in rule_methods(rule):
                    yield rule, method, path

    def test_every_member_api_route_answers_401_without_sign_in(self):
        checked = 0
        for rule, method, path in self.each('member'):
            kwargs = {'json': {}, 'headers': {'Origin': test_auth.ORIGIN}} if method in WRITE else {}
            if rule.rule == '/api/v1/auth/password/set':
                kwargs['json'] = {'password': 'a-long-enough-password-123'}
            response = self.f.client.open(path, method=method, **kwargs)
            self.assertEqual(response.status_code, 401, f'{method} {rule.rule}')
            checked += 1
        self.assertGreater(checked, 140)

    def test_cross_site_writes_are_refused_before_anything_else(self):
        for rule, method, path in self.each('member'):
            if method in WRITE and not rule.rule.startswith('/api/v1/auth/'):
                self.assertIn(self.f.client.open(path, method=method, json={}).status_code, (401, 403), f'{method} {rule.rule}')

    def test_every_web_page_redirects_to_sign_in(self):
        for rule, method, path in self.each('member-web'):
            kwargs = {'headers': {'Origin': test_auth.ORIGIN}} if method in WRITE else {}
            response = self.f.client.open(path, method=method, **kwargs)
            if rule.rule == '/signin':
                continue
            self.assertIn(response.status_code, (302, 303, 403, 404), f'{method} {rule.rule}')
            if response.status_code in (302, 303):
                self.assertTrue(response.headers['Location'].endswith(('/signin', '/signup')), f'{method} {rule.rule}')

    def test_simulation_routes_are_404_with_sign_in_on(self):
        for rule, method, path in self.each('disabled-with-sign-in'):
            kwargs = {'headers': {'Origin': test_auth.ORIGIN}} if method in WRITE else {}
            self.assertEqual(self.f.client.open(path, method=method, **kwargs).status_code, 404, f'{method} {rule.rule}')


class CrossMemberTests(RouteTestCase):
    """Mallory is signed in and knows Bob and Carol's ids."""

    def setUp(self):
        super().setUp()
        for uid in ('mallory', 'bob', 'carol'):
            self.make_user(uid)
        self.lid = self.make_lockin('bob', 'carol', 'lock-bc')
        self.pid = self.make_plan(self.lid, 'plan-bc')
        db.insert_row(self.conn, 'Couple', {'id': 'pair-bc', 'partner_a_id': 'bob', 'partner_b_id': 'carol',
                                            'stage': 'relationship', 'entered_via': 'progression', 'start_date': '2026-01-01'})
        self.conn.commit()
        self.ids = {'lid': 'lock-bc', 'pid': 'plan-bc', 'cid': 'pair-bc', 'match_id': 'lock-bc'}

    def snapshot(self):
        return [json.dumps(db.fetch_all(self.conn, t), sort_keys=True, default=str)
                for t in ('LockIn', 'DatePlan', 'Couple', 'Exit', 'GateResponse', 'NextLevelThread', 'ContactRequest')]

    def routes(self):
        for rule in inv.member_rules():
            if inv.member_class(rule)[0] == 'member' and set(rule.arguments) & set(self.ids):
                path = PARAM.sub(lambda m: self.ids.get(m.group(1), 'probe-x'), rule.rule)
                for method in rule_methods(rule):
                    yield rule, method, path

    def test_another_members_objects_are_never_served_or_changed(self):
        before = self.snapshot()
        self.login('mallory')
        leaks, checked = [], 0
        for rule, method, path in self.routes():
            response = self.client.open(path, method=method, **({'json': {}} if method in WRITE else {}))
            checked += 1
            if response.status_code < 300 or response.status_code >= 500:
                leaks.append(f'{method} {rule.rule} -> {response.status_code}')
            body = response.get_data(as_text=True)
            self.assertNotIn('Traceback', body)
        self.assertEqual(leaks, [])
        self.assertGreater(checked, 50)
        self.assertEqual(self.snapshot(), before)

    def test_positive_control_the_owner_can_read_their_own(self):
        self.login('bob')
        served = [rule.rule for rule, method, path in self.routes()
                  if method == 'GET' and self.client.get(path).status_code == 200]
        self.assertGreaterEqual(len(served), 5, served)     # the ids really resolve, so the 403/404s above mean something


class AdminRouteTests(unittest.TestCase):
    def setUp(self):
        self.f = test_admin_dashboard.AdminDashboardTests('test_rfc_totp')
        self.f.setUp(); self.addCleanup(self.f.tearDown)

    def each(self):
        for rule in inv.admin_rules():
            if inv.admin_class(rule) != 'public':
                yield rule, PARAM.sub('overview', rule.rule)

    def call(self, rule, path, headers=None):
        method = rule_methods(rule)[0]
        return self.f.client.open(path, method=method, json={} if method in WRITE else None, headers=headers or {})

    def test_admin_routes_need_an_admin_session(self):
        for rule, path in self.each():
            self.assertIn(self.call(rule, path).status_code, (401, 403), rule.rule)

    def test_owner_routes_refuse_other_roles(self):
        self.assertEqual(self.f.login().status_code, 200)
        headers = {'Origin': 'http://localhost', 'X-CSRF-Token': self.f.csrf()}
        for role in ('support', 'marketing'):
            self.f.conn.execute('UPDATE "AdminIdentity" SET role = ?', (role,)); self.f.conn.commit()
            for rule, path in self.each():
                if inv.admin_class(rule) == 'admin: owner':
                    self.assertEqual(self.call(rule, path, headers).status_code, 403, (role, rule.rule))


class ResponseFieldTests(RouteTestCase):
    SNAPSHOT = Path('docs/RESPONSE_PERSONAL_FIELDS.json')
    PERSONAL = re.compile(r'(phone|email|mail|dob|birth|address|aadhaar|pan_|passport|password|token|secret|hash|'
                          r'cipher|protected|totp|selfie|face|photo|image|health|ethnic|contact|name|age|lat|lng|ip_)', re.I)

    def collect(self, value, keys):
        if isinstance(value, dict):
            for key, item in value.items():
                keys.add(key); self.collect(item, keys)
        elif isinstance(value, list):
            for item in value:
                self.collect(item, keys)

    def test_trim_removes_secret_keys_anywhere(self):
        removed = []
        cleaned = response_trim.trim({'data': {'a': 1, 'password_hash': 'x', 'rows': [{'protected_input': 'y', 'ok': 2}]},
                                      'phone_index': 'z'}, removed)
        self.assertEqual(cleaned, {'data': {'a': 1, 'rows': [{'ok': 2}]}})
        self.assertEqual(sorted(removed), ['data.password_hash', 'data.rows[].protected_input', 'phone_index'])

    def test_no_new_personal_field_appears_in_member_responses(self):
        for uid in ('bob', 'carol'):
            self.make_user(uid)
        lid = self.make_lockin('bob', 'carol', 'lock-bc'); self.make_plan(lid, 'plan-bc')
        self.login('bob')
        ids = {'lid': 'lock-bc', 'pid': 'plan-bc', 'cid': 'probe-x', 'match_id': 'lock-bc'}
        keys = set()
        for rule in inv.member_rules():
            if inv.member_class(rule)[0] != 'member' or 'GET' not in rule.methods:
                continue
            response = self.client.get(PARAM.sub(lambda m: ids.get(m.group(1), 'probe-x'), rule.rule))
            if response.is_json:
                self.collect(response.get_json(), keys)
                self.assertFalse([k for k in keys if response_trim.sensitive(k)], rule.rule)
        personal = sorted(k for k in keys if self.PERSONAL.search(k))
        allowed = json.loads(self.SNAPSHOT.read_text(encoding='utf-8'))
        new = sorted(set(personal) - set(allowed))
        self.assertEqual(new, [], f'New personal-looking response fields {new}: check they are needed, '
                                  f'then add them to {self.SNAPSHOT}')


if __name__ == '__main__':
    unittest.main()
