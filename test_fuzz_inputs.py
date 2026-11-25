"""c-security-suite: fuzz auth, profile, REACH and upload inputs.
Any body, any type, any size within limits: a safe 4xx answer, never a 500, never a
stack trace or internal detail in the response."""
import os
import unittest
from unittest import mock

from hypothesis import HealthCheck, given, settings, strategies as st

import test_auth
from test_segment_efg_routes import RouteTestCase

SCALARS = st.one_of(st.none(), st.booleans(), st.integers(min_value=-10**12, max_value=10**12),
                    st.floats(allow_nan=False, allow_infinity=False), st.text(max_size=300))
JSON = st.recursive(SCALARS, lambda children: st.one_of(st.lists(children, max_size=5),
                                                        st.dictionaries(st.text(max_size=20), children, max_size=5)),
                    max_leaves=25)
FIELDS = st.sampled_from(['channel', 'destination', 'challenge_id', 'code', 'refresh_token', 'phone', 'password',
                          'fields', 'value', 'photo', 'image', 'consent', 'consent_version', 'index', 'min', 'max',
                          'candidate_id', 'action', 'request_id', 'categories', 'note'])
BODIES = st.one_of(JSON, st.dictionaries(FIELDS, JSON, max_size=6))
FUZZ = settings(max_examples=int(os.environ.get('DHASHU_FUZZ_EXAMPLES', '30')), deadline=None,
                suppress_health_check=[HealthCheck.function_scoped_fixture, HealthCheck.too_slow])
LEAKS = ('Traceback', 'File "', 'psycopg', 'sqlite3', 'Exception:', 'line ')


class SafeAnswers:
    def check(self, response, label):
        self.assertLess(response.status_code, 500, (label, response.get_data(as_text=True)[:300]))
        body = response.get_data(as_text=True)
        for leak in LEAKS:
            self.assertNotIn(leak, body, label)


class AuthFuzzTests(SafeAnswers, unittest.TestCase):
    def setUp(self):
        self.f = test_auth.AuthenticationTests('test_optional_tester_login_and_revocation')
        self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.f.conn.execute('DELETE FROM "AuthThrottle"'); self.f.conn.commit()

    @FUZZ
    @given(path=st.sampled_from(['request', 'signup/request', 'verify', 'refresh', 'tester', 'password/login']), body=BODIES)
    def test_auth_inputs(self, path, body):
        with mock.patch('auth_sessions.throttle', return_value=True):        # fuzz the parsing, not the rate limit
            self.check(self.f.post(path, body), path)

    @FUZZ
    @given(raw=st.binary(max_size=2000))
    def test_auth_raw_bytes(self, raw):
        self.check(self.f.client.post('/api/v1/auth/verify', data=raw, content_type='application/json'), 'raw')


class MemberFuzzTests(SafeAnswers, RouteTestCase):
    ROUTES = [('PATCH', '/api/v1/profile/stats'), ('PUT', '/api/v1/profile/personal'), ('POST', '/api/v1/profile/avatar/selfie'),
              ('POST', '/api/v1/identity-capture'), ('POST', '/api/v1/reach/set-range'), ('POST', '/api/v1/reach/widen'),
              ('POST', '/api/v1/reach/ignore'), ('POST', '/api/v1/reach/show-all'), ('PUT', '/api/v1/profile/chemistry/activities'),
              ('POST', '/api/v1/discovery/decision')]

    def setUp(self):
        super().setUp()
        self.make_user('owner')            # verified, dating: reaches the most handler logic
        self.login('owner')

    @FUZZ
    @given(route=st.sampled_from(ROUTES), body=BODIES)
    def test_profile_reach_and_upload_inputs(self, route, body):
        method, path = route
        self.check(self.client.open(path, method=method, json=body), path)

    @FUZZ
    @given(route=st.sampled_from(ROUTES), data=st.sampled_from(['data:image/png;base64,', 'data:image/jpeg;base64,!!!!',
                                                                 'data:text/html;base64,PHNjcmlwdD4=', 'A' * 5000]),
           key=st.sampled_from(['photo', 'image']))
    def test_malformed_images(self, route, data, key):
        method, path = route
        self.check(self.client.open(path, method=method, json={key: data, 'consent': True, 'consent_version': 'v1'}), path)


if __name__ == '__main__':
    unittest.main()
