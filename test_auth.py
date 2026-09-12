"""Phase 3 integration tests. Provider calls are mocked; no codes are sent."""
import json
from unittest import mock

import auth
import auth_delivery
import auth_sessions as sessions
import db
import generate_users
from test_segment_efg_routes import RouteTestCase, app_module

ORIGIN = 'https://beta.example.test'
SID = 'VE' + 'a' * 32


class AuthenticationTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.config_patch = mock.patch.dict(app_module.app.config, {
            'AUTH_ENABLED': True, 'AUTH_PUBLIC_ORIGIN': ORIGIN,
            'SESSION_COOKIE_SECURE': True, 'SESSION_COOKIE_HTTPONLY': True,
            'SESSION_COOKIE_SAMESITE': 'Lax', 'MAX_CONTENT_LENGTH': 1024 * 1024})
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)
        self.start = mock.patch.object(auth_delivery, 'start', return_value=SID).start()
        self.check = mock.patch.object(auth_delivery, 'check', return_value=True).start()
        self.configured = mock.patch.object(auth_delivery, 'configured', return_value=True).start()
        self.addCleanup(mock.patch.stopall)
        for name, user in zip(('owner', 'other'), generate_users.generate_users(2, seed=11)):
            row = app_module.onboarding.build_user_row(
                user_id=name, city=user['city'], gender=user['gender'],
                stats=user['stats'], visions=user['visions'], activities={})
            row['bgv_status'] = 'verified'
            row['journey_state'] = 'dating'
            row['preferences_json'] = json.dumps(user['preferences'])
            db.insert_row(self.conn, 'User', row)
            db.insert_row(self.conn, 'Account', {'id': 'account-' + name, 'user_id': name,
                'email': name + '@example.test', 'phone': '919876543210' if name == 'owner' else '919876543211',
                'auth_enabled': 1, 'created_at': 'test'})

    def post(self, path, body, **kwargs):
        return self.client.post('/api/v1/auth/' + path, json=body, **kwargs)

    def challenge(self, channel='email', destination='owner@example.test'):
        response = self.post('request', {'channel': channel, 'destination': destination})
        self.assertEqual(response.status_code, 202, response.json)
        return response.json['data']['challenge_id']

    def login_mobile(self, destination='owner@example.test'):
        challenge = self.challenge(destination=destination)
        response = self.post('verify', {'challenge_id': challenge, 'code': '123456'})
        self.assertEqual(response.status_code, 200, response.json)
        return response.json['data']

    def bearer(self, tokens):
        return {'Authorization': 'Bearer ' + tokens['access_token']}

    def test_email_login_issues_hashed_credentials_and_current_identity(self):
        tokens = self.login_mobile()
        self.start.assert_called_once_with('email', 'owner@example.test')
        self.check.assert_called_once_with(SID, '123456')
        self.assertEqual(tokens['expires_in'], 900)
        with self.client.session_transaction() as cookie:
            self.assertNotIn('auth_token', cookie)
        response = self.client.get('/api/v1/me', headers=self.bearer(tokens))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['data']['user_id'], 'owner')
        stored = json.dumps(db.fetch_all(self.conn, 'AuthSession') + db.fetch_all(self.conn, 'AuthRefresh') + db.fetch_all(self.conn, 'AuthChallenge'))
        for secret in (tokens['access_token'], tokens['refresh_token'], '123456'):
            self.assertNotIn(secret, stored)
        self.assertEqual(db.fetch_one(self.conn, 'Account', user_id='owner')['verified_email'], 1)

    def test_sms_uses_country_code_and_same_account(self):
        challenge = self.challenge('phone', '+919876543210')
        response = self.post('verify', {'challenge_id': challenge, 'code': '123456'})
        self.assertEqual(response.json['data']['user_id'], 'owner')
        self.start.assert_called_once_with('phone', '+919876543210')
        self.assertEqual(db.fetch_one(self.conn, 'Account', user_id='owner')['verified_phone'], 1)
        self.assertEqual(db.fetch_one(self.conn, 'Account', user_id='owner')['verified_email'], 0)

    def test_unknown_and_unapproved_accounts_never_issue_tokens(self):
        self.conn.execute('UPDATE Account SET auth_enabled = 0 WHERE user_id = ?', ('other',))
        self.conn.commit()
        for destination in ('absent@example.test', 'other@example.test'):
            challenge = self.challenge(destination=destination)
            result = self.post('verify', {'challenge_id': challenge, 'code': '123456'})
            self.assertEqual(result.status_code, 401)
        self.start.assert_not_called()
        self.check.assert_not_called()
        self.assertEqual(db.fetch_all(self.conn, 'AuthSession'), [])

    def test_canonical_duplicate_account_fails_closed(self):
        self.conn.execute('UPDATE Account SET email = ? WHERE user_id = ?', ('OWNER@EXAMPLE.TEST', 'other'))
        self.conn.commit()
        challenge = self.challenge()
        self.assertEqual(self.post('verify', {'challenge_id': challenge, 'code': '123456'}).status_code, 401)
        self.start.assert_not_called()

    def test_wrong_codes_attempt_limit_and_no_session(self):
        self.check.return_value = False
        challenge = self.challenge()
        for _ in range(6):
            self.assertEqual(self.post('verify', {'challenge_id': challenge, 'code': '111111'}).status_code, 401)
        self.assertEqual(self.check.call_count, 5)
        self.assertEqual(db.fetch_all(self.conn, 'AuthSession'), [])

    def test_expired_and_consumed_challenges_cannot_be_reused(self):
        challenge = self.challenge()
        response = self.post('verify', {'challenge_id': challenge, 'code': '123456'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.post('verify', {'challenge_id': challenge, 'code': '123456'}).status_code, 401)
        self.assertEqual(self.check.call_count, 1)
        with mock.patch.object(sessions, 'now', return_value=sessions.now() + 61):
            challenge = self.challenge()
        with mock.patch.object(sessions, 'now', return_value=sessions.now() + 1000):
            self.assertEqual(self.post('verify', {'challenge_id': challenge, 'code': '123456'}).status_code, 401)
        self.assertEqual(self.check.call_count, 1)

    def test_contact_change_during_challenge_cannot_authenticate(self):
        challenge = self.challenge()
        self.conn.execute('UPDATE Account SET email = ? WHERE user_id = ?', ('changed@example.test', 'owner'))
        self.conn.commit()
        self.assertEqual(self.post('verify', {'challenge_id': challenge, 'code': '123456'}).status_code, 401)
        self.assertEqual(db.fetch_all(self.conn, 'AuthSession'), [])

    def test_provider_outage_fails_closed_without_details_or_codes(self):
        self.configured.return_value = False
        result = self.post('request', {'channel': 'email', 'destination': 'owner@example.test'})
        self.assertEqual(result.status_code, 503)
        self.configured.return_value = True
        self.start.side_effect = auth_delivery.DeliveryUnavailable('private-provider-detail')
        challenge = self.challenge()
        result = self.post('verify', {'challenge_id': challenge, 'code': '123456'})
        self.assertEqual(result.status_code, 401)
        self.assertNotIn('private-provider-detail', result.get_data(as_text=True))
        self.check.assert_not_called()

    def test_send_cooldown_and_shared_ip_limit(self):
        self.challenge()
        self.assertEqual(self.post('request', {'channel': 'email', 'destination': 'owner@example.test'}).status_code, 429)
        for i in range(18):
            self.assertEqual(self.post('request', {'channel': 'email', 'destination': f'unknown{i}@example.test'}).status_code, 202)
        self.assertEqual(self.post('request', {'channel': 'email', 'destination': 'last@example.test'}).status_code, 429)
        with mock.patch.object(sessions, 'now', return_value=sessions.now() + 601):
            self.challenge()

    def test_access_expiry_and_rotating_refresh(self):
        tokens = self.login_mobile()
        with mock.patch.object(sessions, 'now', return_value=sessions.now() + 901):
            self.assertEqual(self.client.get('/api/v1/me', headers=self.bearer(tokens)).status_code, 401)
            result = self.post('refresh', {'refresh_token': tokens['refresh_token']})
            self.assertEqual(result.status_code, 200, result.json)
            new = result.json['data']
            self.assertNotEqual(new['refresh_token'], tokens['refresh_token'])
            self.assertEqual(self.client.get('/api/v1/me', headers=self.bearer(new)).status_code, 200)
            self.assertEqual(self.client.get('/api/v1/me', headers=self.bearer(tokens)).status_code, 401)
        # Replay of the old refresh credential revokes the entire session family.
        self.assertEqual(self.post('refresh', {'refresh_token': tokens['refresh_token']}).status_code, 401)
        self.assertEqual(self.client.get('/api/v1/me', headers=self.bearer(new)).status_code, 401)
        self.assertEqual(self.post('refresh', {'refresh_token': new['refresh_token']}).status_code, 401)

    def test_refresh_and_absolute_session_expiry(self):
        tokens = self.login_mobile()
        with mock.patch.object(sessions, 'now', return_value=sessions.now() + sessions.REFRESH_SECONDS):
            self.assertEqual(self.post('refresh', {'refresh_token': tokens['refresh_token']}).status_code, 401)
        self.conn.execute('UPDATE AuthSession SET expires_at = ? WHERE id = ?', (sessions.now(), tokens['session_id']))
        self.conn.commit()
        self.assertEqual(self.post('refresh', {'refresh_token': tokens['refresh_token']}).status_code, 401)

    def test_revocation_and_account_disablement(self):
        tokens = self.login_mobile()
        second = sessions.issue(self.conn, 'owner')
        other = sessions.issue(self.conn, 'other')
        self.assertEqual(self.post('logout', {}, headers=self.bearer(tokens)).status_code, 200)
        self.assertEqual(self.client.get('/api/v1/me', headers=self.bearer(tokens)).status_code, 401)
        self.assertEqual(self.post('refresh', {'refresh_token': tokens['refresh_token']}).status_code, 401)
        self.assertEqual(self.client.get('/api/v1/me', headers=self.bearer(second)).status_code, 200)
        self.assertEqual(self.post('logout-all', {}, headers=self.bearer(second)).status_code, 200)
        self.assertEqual(self.client.get('/api/v1/me', headers=self.bearer(second)).status_code, 401)
        self.assertEqual(self.client.get('/api/v1/me', headers=self.bearer(other)).status_code, 200)
        self.conn.execute('UPDATE Account SET auth_enabled = 0 WHERE user_id = ?', ('other',))
        self.conn.commit()
        self.assertEqual(self.client.get('/api/v1/me', headers=self.bearer(other)).status_code, 401)
        self.assertEqual(self.post('refresh', {'refresh_token': other['refresh_token']}).status_code, 401)

    def test_bearer_identity_ownership_and_no_cookie_fallback(self):
        tokens = self.login_mobile()
        self.login('other')  # Legacy simulation cookie must not count as identity.
        self.assertEqual(self.client.get('/api/v1/me').status_code, 401)
        result = self.client.get('/api/v1/profile?user_id=other', headers=self.bearer(tokens))
        self.assertEqual(result.json['data']['user_id'], 'owner')
        for header in ('Bearer junk', 'Basic xxx', 'Bearer', 'Bearer a b'):
            self.assertEqual(self.client.get('/api/v1/me', headers={'Authorization': header}).status_code, 401)
        # Shared legacy action handlers use bearer ownership, never session user_id.
        response = self.client.post('/api/v1/reach/ignore', json={'filter': 'age', 'ignore': True}, headers=self.bearer(tokens))
        self.assertEqual(response.status_code, 200)
        owner = json.loads(db.fetch_one(self.conn, 'User', id='owner')['preferences_json'])
        other = json.loads(db.fetch_one(self.conn, 'User', id='other')['preferences_json'])
        self.assertIn('age', owner['ignored'])
        self.assertNotIn('age', other.get('ignored', []))

    def test_simulation_routes_and_onboarding_cannot_mint_identity(self):
        for path in ('/pool', '/login/owner', '/admin/pairs', '/admin/reset-week', '/demo/partner', '/verify/simulate', '/verify-contact/send'):
            for method in (self.client.get, self.client.post):
                self.assertEqual(method(path).status_code, 404)
        for path in ('/signup', '/onboarding/finish'):
            self.assertEqual(self.client.post(path).headers.get('Location'), '/signin')
        self.assertEqual(self.client.get('/api/v1/me').status_code, 401)

    def test_web_signin_csrf_cookie_attributes_and_logout(self):
        self.assertEqual(self.client.post('/signin', data={'action': 'request'}).status_code, 403)
        result = self.client.post('/signin', headers={'Origin': ORIGIN}, data={
            'action': 'request', 'channel': 'email', 'destination': 'owner@example.test'})
        self.assertEqual(result.status_code, 200)
        with self.client.session_transaction() as cookie:
            challenge = cookie['login_challenge']
        # A web challenge is not exchangeable for mobile credentials.
        self.assertEqual(self.post('verify', {'challenge_id': challenge, 'code': '123456'}).status_code, 401)
        result = self.client.post('/signin', headers={'Origin': ORIGIN}, data={'action': 'verify', 'code': '123456'})
        self.assertEqual(result.status_code, 302)
        self.assertEqual(result.headers['Location'], '/dashboard')
        for flag in ('Secure', 'HttpOnly', 'SameSite=Lax'):
            self.assertIn(flag, result.headers['Set-Cookie'])
        self.assertEqual(self.client.get('/api/v1/me').status_code, 200)
        self.assertEqual(self.client.get('/api/v1/me', headers={'Authorization': 'Bearer invalid'}).status_code, 401)
        self.assertEqual(self.client.post('/api/v1/reach/show-all', json={'ignore': True}).status_code, 403)
        self.assertEqual(self.post('logout', {}).status_code, 401)
        with self.client.session_transaction() as cookie:
            token = cookie['auth_token']
        self.assertEqual(self.client.post('/logout', headers={'Origin': 'https://attacker.example'}).status_code, 403)
        self.assertEqual(self.client.post('/logout', headers={'Origin': ORIGIN}).status_code, 302)
        self.assertIsNone(sessions.authenticate(self.conn, token, 'web'))
        self.assertEqual(self.client.get('/api/v1/me').status_code, 401)

    def test_invalid_input_and_body_size(self):
        for body in ([], {}, {'channel': 'phone', 'destination': '9876543210'},
                     {'channel': [], 'destination': 'x'}, {'channel': 'email', 'destination': []}):
            self.assertEqual(self.post('request', body).status_code, 400)
        for path in ('request', 'verify', 'refresh'):
            self.assertEqual(self.client.post('/api/v1/auth/' + path, data='not-json').status_code, 415)
        self.assertEqual(self.post('request', {'channel': 'email', 'destination': 'x' * 5000}).status_code, 413)
        self.start.assert_not_called()

    def test_feature_disabled_preserves_existing_web_behavior(self):
        with mock.patch.dict(app_module.app.config, {'AUTH_ENABLED': False}):
            self.assertEqual(self.post('request', {}).status_code, 503)
            self.assertEqual(self.client.post('/login/owner').status_code, 302)
            self.assertEqual(self.client.get('/api/v1/me').status_code, 200)

    def test_resend_invalidates_old_challenge(self):
        old = self.challenge()
        with mock.patch.object(sessions, 'now', return_value=sessions.now() + 61):
            new = self.challenge()
        self.assertEqual(self.post('verify', {'challenge_id': old, 'code': '123456'}).status_code, 401)
        self.assertEqual(self.post('verify', {'challenge_id': new, 'code': '123456'}).status_code, 200)
        self.assertEqual(self.check.call_count, 1)

    def test_web_credentials_expire_and_cannot_be_bearer_tokens(self):
        tokens = sessions.issue(self.conn, 'owner', 'web')
        with self.client.session_transaction() as cookie:
            cookie['auth_token'] = tokens['access_token']
            cookie['user_id'] = 'owner'
        self.assertEqual(self.client.get('/api/v1/me').status_code, 200)
        self.assertEqual(self.client.get('/api/v1/me', headers=self.bearer(tokens)).status_code, 401)
        with mock.patch.object(sessions, 'now', return_value=sessions.now() + sessions.WEB_SECONDS):
            self.assertEqual(self.client.get('/api/v1/me').status_code, 401)

    def test_failed_token_issue_rolls_back_code_redemption_and_verification(self):
        challenge = self.challenge()
        self.conn.execute("CREATE TRIGGER fail_refresh BEFORE INSERT ON AuthRefresh BEGIN SELECT RAISE(ABORT, 'test rollback'); END")
        self.conn.commit()
        result = self.post('verify', {'challenge_id': challenge, 'code': '123456'})
        self.assertEqual(result.status_code, 500)
        self.assertEqual(db.fetch_all(self.conn, 'AuthSession'), [])
        row = db.fetch_one(self.conn, 'AuthChallenge', id=sessions.digest(challenge))
        self.assertIsNone(row['consumed_at'])
        self.assertEqual(db.fetch_one(self.conn, 'Account', user_id='owner')['verified_email'], 0)
