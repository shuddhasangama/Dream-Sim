"""fix/avatar-signout: the avatar screen's routes (/profile/avatar, /profile/liveness,
/profile/face-match) accept every session the rest of the API accepts from the app:
the secure sign-in session and, on a local backend only, the emulator's local-harness
session ("Pick a local user"). They used to read g.auth_session, which only
auth.resolve sets, so a harness session got 401 there while /profile answered 200,
and the app signed the member out.

Also: a route that refuses a session the API has accepted answers code
'app_session_required' (auth.APP_SESSION_REQUIRED), never 'authentication_required',
which the app reserves for a refused session (sign in again)."""
import json
import os
from unittest import mock

import auth
import auth_sessions as sessions
import db
import generate_users
import local_harness as harness
from test_local_harness import patched_env
from test_segment_efg_routes import RouteTestCase, app_module

AVATAR_SCREEN = ('/api/v1/profile/avatar', '/api/v1/profile/liveness', '/api/v1/profile/face-match')


class AvatarScreenSessionTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        # sec-login: RouteTestCase registers the local harness for the legacy route
        # suites; these tests start from "harness not registered" and opt in via harness_on().
        patch = mock.patch.dict(app_module.app.config, {harness.CONFIG_KEY: False})
        patch.start()
        self.addCleanup(patch.stop)
        for name, user in zip(('owner', 'other'), generate_users.generate_users(2, seed=11)):
            row = app_module.onboarding.build_user_row(user_id=name, city=user['city'], gender=user['gender'],
                                                       stats=user['stats'], visions=user['visions'], activities={})
            row['bgv_status'] = 'verified'
            row['journey_state'] = 'dating'
            row['preferences_json'] = json.dumps(user['preferences'])
            db.insert_row(self.conn, 'User', row)
            db.insert_row(self.conn, 'Account', {'id': 'account-' + name, 'user_id': name, 'email': name + '@example.test',
                                                 'verified_email': 1, 'auth_enabled': 1, 'created_at': 'test'})

    def issue(self, user_id, **kind):
        with sessions.transaction(self.conn):
            return sessions.issue_in_transaction(self.conn, user_id, 'mobile', **kind)

    def harness_on(self):
        for item in (patched_env(**{harness.FLAG: '1', 'DHASHU_PAYMENT_BYPASS': '1', 'DEMO_MODE': '1', 'DHASHU_SIMULATED_CLOCK': 'true'}),
                     mock.patch.dict(app_module.app.config, {harness.CONFIG_KEY: True})):
            item.start()
            self.addCleanup(item.stop)

    def get(self, path, token=None, **kwargs):
        headers = {'Authorization': 'Bearer ' + token} if token else {}
        return self.client.get(path, headers=headers, **kwargs)

    # ── the reported bug ───────────────────────────────────────────────────
    def test_harness_session_is_accepted_by_the_avatar_screen_like_the_rest_of_the_api(self):
        self.harness_on()
        token = self.issue('other', harness=True)['access_token']
        for path in ('/api/v1/profile', '/api/v1/journey/status', '/api/v1/profile/stats') + AVATAR_SCREEN:
            response = self.get(path, token)
            self.assertEqual(response.status_code, 200, (path, response.get_json()))
        self.assertEqual(self.get('/api/v1/profile/avatar', token).get_json()['data']['state'], 'not_started')

    def test_no_session_is_refused_with_authentication_required(self):
        self.harness_on()
        for path in AVATAR_SCREEN:
            for token in (None, 'x' * 43):
                response = self.get(path, token)
                self.assertEqual(response.status_code, 401, path)
                self.assertEqual(response.get_json()['error']['code'], 'authentication_required', path)

    def test_revoked_or_expired_harness_session_is_refused(self):
        self.harness_on()
        issued = self.issue('other', harness=True)
        sessions.revoke(self.conn, issued['session_id'], 'other')
        for path in AVATAR_SCREEN:
            response = self.get(path, issued['access_token'])
            self.assertEqual(response.status_code, 401, path)
            self.assertEqual(response.get_json()['error']['code'], 'authentication_required')
        expired = self.issue('other', harness=True)
        sessions.sql(self.conn, 'UPDATE "AuthSession" SET access_expires_at=? WHERE id=?',
                     (sessions.now() - 1, expired['session_id']))
        self.conn.commit()
        self.assertEqual(self.get('/api/v1/profile/avatar', expired['access_token']).status_code, 401)

    def test_harness_session_is_refused_whenever_the_harness_is_not_active(self):
        token = self.issue('other', harness=True)['access_token']
        for path in AVATAR_SCREEN:                       # harness never registered
            self.assertEqual(self.get(path, token).status_code, 401, path)
        self.harness_on()
        self.assertEqual(self.get('/api/v1/profile/avatar', token).status_code, 200)
        self.assertEqual(self.get('/api/v1/profile/avatar', token, environ_base={'REMOTE_ADDR': '10.0.0.9'}).status_code, 401)
        with mock.patch.dict(os.environ, {'RAILWAY_ENVIRONMENT': 'production'}):
            self.assertEqual(self.get('/api/v1/profile/avatar', token).status_code, 401)
        with mock.patch.dict(app_module.app.config, {'AUTH_ENABLED': True}):
            self.assertEqual(self.get('/api/v1/profile/avatar', token).status_code, 401)

    def test_secure_sign_in_session_still_works(self):
        with patched_env(), mock.patch.dict(app_module.app.config, {'AUTH_ENABLED': True}):
            token = self.issue('owner')['access_token']
            for path in AVATAR_SCREEN:
                response = self.get(path, token)
                self.assertEqual(response.status_code, 200, (path, response.get_json()))
            for path in AVATAR_SCREEN:
                self.assertEqual(self.get(path).status_code, 401, path)

    # ── a route refusing an accepted session is not a refused session ──────
    def test_cookie_session_on_an_app_only_route_says_app_session_required(self):
        self.harness_on()
        self.assertEqual(self.client.post('/login/owner').status_code, 302)
        self.assertEqual(self.client.get('/api/v1/profile').status_code, 200)   # the API accepts it
        for path in AVATAR_SCREEN + ('/api/v1/verification', '/api/v1/identity-capture'):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 401, path)
            self.assertEqual(response.get_json()['error']['code'], auth.APP_SESSION_REQUIRED, path)

    def test_bearer_session_helper(self):
        with app_module.app.test_request_context('/api/v1/profile/avatar'):
            self.assertIsNone(auth.bearer_session())
        with app_module.app.test_request_context('/api/v1/profile/avatar', headers={'Authorization': 'Bearer t'}):
            self.assertIsNone(auth.bearer_session())               # nothing resolved: refused
            self.assertIsNone(harness.bearer_session())
            app_module.g.local_harness_user = (True, None)        # presented but invalid
            self.assertIsNone(auth.bearer_session())
            app_module.g.local_harness_user = (True, 'other')
            app_module.g.local_harness_session_id = 'harness_1'
            self.assertEqual(auth.bearer_session(), {'id': 'harness_1', 'user_id': 'other', 'kind': 'mobile'})
            app_module.g.auth_session = {'id': 's1', 'user_id': 'owner', 'kind': 'mobile'}
            self.assertEqual(auth.bearer_session()['id'], 's1')    # secure sign-in wins
        with app_module.app.test_request_context('/api/v1/profile/avatar'):
            app_module.g.auth_session = {'id': 's1', 'user_id': 'owner', 'kind': 'web'}
            self.assertIsNone(auth.bearer_session())               # bearer-only routes need the app's header
