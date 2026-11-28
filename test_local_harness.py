"""Local harness (local_harness.py): dev-only emulator login that must be
impossible to enable in production. Every enable/disable combination, the
404 behaviour, startup refusal per production marker, loopback-only access,
harness tokens rejected when inactive, the real login unchanged."""
import json
import logging
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from flask import Flask

import auth
import auth_sessions as sessions
import db
import generate_users
import local_harness as harness
from test_segment_efg_routes import RouteTestCase, app_module

REPO = Path(__file__).resolve().parent
MARKER_ENV = {  # one production marker each -> (env update, expected marker name)
    'RAILWAY_ENVIRONMENT': ({'RAILWAY_ENVIRONMENT': 'production'}, 'RAILWAY_ENVIRONMENT'),
    'RAILWAY_PROJECT_ID': ({'RAILWAY_PROJECT_ID': 'c0ffee'}, 'RAILWAY_PROJECT_ID'),
    'RAILWAY_SERVICE_ID': ({'RAILWAY_SERVICE_ID': 'svc'}, 'RAILWAY_SERVICE_ID'),
    'RAILWAY_GIT_COMMIT_SHA': ({'RAILWAY_GIT_COMMIT_SHA': 'abc1234'}, 'RAILWAY_GIT_COMMIT_SHA'),
    'any other RAILWAY_*': ({'RAILWAY_SOMETHING_NEW': '1'}, 'RAILWAY_SOMETHING_NEW'),
    'DHASHU_PROCESS_ROLE': ({'DHASHU_PROCESS_ROLE': 'web'}, 'DHASHU_PROCESS_ROLE'),
    'remote DATABASE_URL': ({'DATABASE_URL': 'postgresql://u:pw-secret@db.internal.example:5432/app'}, 'DATABASE_URL (non-local host)'),
    'remote ADMIN_REPORT_DATABASE_URL': ({'ADMIN_REPORT_DATABASE_URL': 'postgresql://u:pw@10.1.2.3/app'}, 'ADMIN_REPORT_DATABASE_URL (non-local host)'),
    'public AUTH_PUBLIC_ORIGIN': ({'AUTH_PUBLIC_ORIGIN': 'https://app.example.com'}, 'AUTH_PUBLIC_ORIGIN (non-local host)'),
    'public ADMIN_PUBLIC_ORIGIN': ({'ADMIN_PUBLIC_ORIGIN': 'https://admin.example.com'}, 'ADMIN_PUBLIC_ORIGIN (non-local host)'),
    'AUTH_ENABLED': ({'AUTH_ENABLED': 'true'}, 'AUTH_ENABLED'),
    'SIGNZY production env': ({'SIGNZY_ENV': 'production'}, 'SIGNZY production'),
    'SIGNZY production enabled': ({'SIGNZY_PRODUCTION_ENABLED': '1'}, 'SIGNZY production'),
    'live billing ack': ({'DHASHU_BILLING_LIVE_ACK': 'yes'}, 'DHASHU_BILLING live'),
    'live billing mode': ({'DHASHU_BILLING_MODE': 'live'}, 'DHASHU_BILLING live'),
}
# Every non-generic value used in MARKER_ENV: none may appear in a refusal message.
SENSITIVE_VALUES = ('c0ffee', 'svc', 'abc1234', 'pw-secret', 'db.internal.example', 'u:pw', '10.1.2.3',
                    'app.example.com', 'admin.example.com', 'yes')
SCRUB = ('DATABASE_URL', 'ADMIN_REPORT_DATABASE_URL', 'AUTH_PUBLIC_ORIGIN', 'ADMIN_PUBLIC_ORIGIN', 'AUTH_ENABLED',
         'DHASHU_PROCESS_ROLE', 'SIGNZY_ENV', 'SIGNZY_PRODUCTION_ENABLED', 'DHASHU_BILLING_LIVE_ACK',
         'DHASHU_BILLING_MODE', harness.FLAG)


def clean_env(**updates):
    """os.environ without any production marker (or the flag), plus updates."""
    env = {k: v for k, v in os.environ.items() if not k.startswith('RAILWAY_') and k not in SCRUB}
    env.setdefault('AUTH_ENABLED', '0')
    env.update(updates)
    return env


def patched_env(**updates):
    return mock.patch.dict(os.environ, clean_env(**updates), clear=True)


# ── A. pure conditions ────────────────────────────────────────────────────
class ConditionTests(unittest.TestCase):
    def test_active_only_with_the_exact_flag_and_nothing_else(self):
        for value, expected in (('1', True), ('', False), ('0', False), ('true', False), ('yes', False), (' 1', False)):
            env = clean_env(**({harness.FLAG: value} if value != '' else {}))
            self.assertEqual(harness.active(env), expected, repr(value))
        self.assertFalse(harness.active(clean_env()))

    def test_auth_enabled_in_any_spelling_disables_and_refuses(self):
        for value in ('1', 'true', 'TRUE', 'on'):
            env = clean_env(**{harness.FLAG: '1', 'AUTH_ENABLED': value})
            self.assertFalse(harness.active(env), value)
            with self.assertRaisesRegex(RuntimeError, 'AUTH_ENABLED'):
                harness.assert_safe_startup(env)
        for value in ('0', 'false', 'off', 'no'):
            self.assertTrue(harness.active(clean_env(**{harness.FLAG: '1', 'AUTH_ENABLED': value})), value)
        self.assertFalse(harness.active(clean_env(**{harness.FLAG: '1', 'AUTH_ENABLED': ''})))

    def test_every_production_marker_disables_and_refuses_startup_by_name_only(self):
        for label, (updates, name) in MARKER_ENV.items():
            with self.subTest(label):
                env = clean_env(**{harness.FLAG: '1'}, **updates)
                self.assertIn(name, harness.production_markers(env))
                self.assertFalse(harness.active(env))
                with self.assertRaises(RuntimeError) as caught:
                    harness.assert_safe_startup(env)
                message = str(caught.exception)
                self.assertIn(name.split(' ')[0], message)
                for secret in SENSITIVE_VALUES:  # hosts, passwords and ids are never echoed
                    self.assertNotIn(secret, message)

    def test_flag_off_never_refuses_startup_even_with_markers(self):
        for updates, _name in MARKER_ENV.values():
            harness.assert_safe_startup(clean_env(**updates))  # production boots normally

    def test_local_settings_are_not_markers(self):
        env = clean_env(**{harness.FLAG: '1', 'DATABASE_URL': 'postgresql://postgres:x@localhost:5433/dhashu_local',
                           'ADMIN_PUBLIC_ORIGIN': 'http://127.0.0.1:5001', 'SIGNZY_ENV': 'preproduction',
                           'SIGNZY_PRODUCTION_ENABLED': '0', 'DHASHU_BILLING_MODE': 'disabled'})
        self.assertEqual(harness.production_markers(env), [])
        self.assertTrue(harness.active(env))
        harness.assert_safe_startup(env)
        self.assertTrue(harness.active(clean_env(**{harness.FLAG: '1', 'DATABASE_URL': 'postgresql://p@127.0.0.1/x'})))


# ── B/C. registration and requests on an isolated Flask app ──────────────
class HarnessAppCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.conn = db.get_connection(Path(tmp.name) / 'harness.db')
        self.addCleanup(self.conn.close)
        db.init_db(self.conn)
        for name, user in zip(('u_0001', 'u_0002'), generate_users.generate_users(2, seed=7)):
            row = app_module.onboarding.build_user_row(user_id=name, city=user['city'], gender=user['gender'],
                                                       stats=user['stats'], visions=user['visions'], activities={})
            row['journey_state'] = 'dating'
            db.insert_row(self.conn, 'User', row)

    def make_app(self, **env):
        self.env = patched_env(**env)
        self.env.start()
        self.addCleanup(self.env.stop)
        app = Flask('harness_test')
        app.config['TESTING'] = True
        registered = harness.register(app, lambda: self.conn)
        return app, registered

    def active_app(self):
        app, registered = self.make_app(**{harness.FLAG: '1'})
        self.assertTrue(registered)
        return app, app.test_client()

    def login(self, client, user_id='u_0001', **kwargs):
        return client.post('/api/v1/dev/login-as', json={'user_id': user_id}, **kwargs)


class RegistrationTests(HarnessAppCase):
    def dev_rules(self, app):
        return sorted(r.rule for r in app.url_map.iter_rules() if r.rule.startswith('/api/v1/dev'))

    def test_flag_off_registers_nothing_and_everything_is_404(self):
        for env in ({}, {harness.FLAG: '0'}, {harness.FLAG: 'true'}, {harness.FLAG: 'yes'}):
            with self.subTest(env=env), patched_env(**env), self.assertNoLogs('dhashu.local_harness', level='WARNING'):
                app = Flask('off')
                self.assertFalse(harness.register(app, lambda: self.conn))
                self.assertFalse(app.config[harness.CONFIG_KEY])
                self.assertEqual(self.dev_rules(app), [])
                client = app.test_client()
                for method, path in (('post', '/api/v1/dev/login-as'), ('get', '/api/v1/dev/users'),
                                     ('post', '/api/v1/dev/refresh'), ('post', '/api/v1/dev/logout')):
                    self.assertEqual(getattr(client, method)(path, json={'user_id': 'u_0001'}).status_code, 404, path)

    def test_flag_with_auth_enabled_or_marker_refuses_to_register(self):
        for updates, _ in MARKER_ENV.values():
            with self.subTest(updates=list(updates)), patched_env(**{harness.FLAG: '1'}, **updates):
                app = Flask('refuse')
                with self.assertRaises(RuntimeError):
                    harness.register(app, lambda: self.conn)
                self.assertEqual(self.dev_rules(app), [])

    def test_active_registers_the_four_routes_and_logs_one_loud_warning(self):
        with self.assertLogs('dhashu.local_harness', level='WARNING') as logs:
            app, _client = self.active_app()
        self.assertEqual(self.dev_rules(app), ['/api/v1/dev/login-as', '/api/v1/dev/logout', '/api/v1/dev/refresh', '/api/v1/dev/users'])
        self.assertEqual(len(logs.records), 1)
        self.assertIn('LOCAL HARNESS ACTIVE', logs.output[0])


class RequestTests(HarnessAppCase):
    def test_login_as_issues_the_same_token_shape_as_real_login(self):
        _app, client = self.active_app()
        response = self.login(client)
        self.assertEqual(response.status_code, 200, response.get_data(as_text=True))
        tokens = response.get_json()
        with sessions.transaction(self.conn):
            real = sessions.issue_in_transaction(self.conn, 'u_0002', 'mobile')
        self.assertEqual(set(tokens), set(real))
        self.assertEqual((tokens['token_type'], tokens['expires_in'], tokens['user_id']), ('Bearer', sessions.ACCESS_SECONDS, 'u_0001'))
        self.assertTrue(tokens['session_id'].startswith('harness_'))
        self.assertTrue(sessions.valid_token(tokens['access_token']) and sessions.valid_token(tokens['refresh_token']))

    def test_cannot_log_in_as_an_existing_non_seeded_user(self):
        # These rows EXIST locally, but only u_* / test_* profiles may be used.
        names = ('member-42', 'U_0003', 'xu_1', 'tester_1', 'test-1', 'u', 'test_blr_20260921_f01')
        for name, user in zip(names, generate_users.generate_users(len(names), seed=5)):
            row = app_module.onboarding.build_user_row(user_id=name, city=user['city'], gender=user['gender'],
                                                       stats=user['stats'], visions=user['visions'], activities={})
            row['journey_state'] = 'dating'
            db.insert_row(self.conn, 'User', row)
        _app, client = self.active_app()
        with self.assertNoLogs('dhashu.local_harness', level='WARNING'):
            for name in names[:-1]:
                self.assertEqual(self.login(client, name).status_code, 404, name)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM "AuthSession"').fetchone()[0], 0)
        seeded = self.login(client, 'test_blr_20260921_f01')
        self.assertEqual(seeded.status_code, 200)
        self.assertEqual(seeded.get_json()['user_id'], 'test_blr_20260921_f01')

    def test_cannot_log_in_as_a_non_existent_or_malformed_user(self):
        _app, client = self.active_app()
        self.assertEqual(self.login(client, 'u_9999').status_code, 404)
        for bad in ('', 'x' * 65, "u_0001' OR '1'='1", '../u_0001', None, 7):
            self.assertEqual(client.post('/api/v1/dev/login-as', json={'user_id': bad}).status_code, 400, repr(bad))
        self.assertEqual(client.post('/api/v1/dev/login-as', data='nope').status_code, 400)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM "AuthSession"').fetchone()[0], 0)

    def test_only_direct_loopback_peers_are_served(self):
        _app, client = self.active_app()
        for peer in ('10.0.0.5', '192.168.1.20', '10.0.2.2', '172.17.0.1', '8.8.8.8'):
            self.assertEqual(self.login(client, environ_base={'REMOTE_ADDR': peer}).status_code, 404, peer)
            self.assertEqual(client.get('/api/v1/dev/users', environ_base={'REMOTE_ADDR': peer}).status_code, 404, peer)
        self.assertEqual(self.login(client, environ_base={'REMOTE_ADDR': '::1'}).status_code, 200)
        self.assertEqual(self.login(client, environ_base={'REMOTE_ADDR': '127.0.0.1'}).status_code, 200)

    def test_proxy_headers_and_foreign_hosts_are_404(self):
        _app, client = self.active_app()
        for header in ({'X-Forwarded-For': '127.0.0.1'}, {'X-Real-IP': '127.0.0.1'}, {'Forwarded': 'for=127.0.0.1'},
                       {'X-Forwarded-Host': 'localhost'}):
            self.assertEqual(self.login(client, headers=header).status_code, 404, header)
        for host in ('app.example.com', 'evil.test:5000', '192.168.1.20:5000'):
            self.assertEqual(self.login(client, headers={'Host': host}).status_code, 404, host)
        for host in ('10.0.2.2:5000', '127.0.0.1:5000', 'localhost:5000', '[::1]:5000'):
            self.assertEqual(self.login(client, headers={'Host': host}).status_code, 200, host)

    def test_conditions_are_rechecked_on_every_request(self):
        _app, client = self.active_app()
        tokens = self.login(client).get_json()
        for label, (updates, _name) in MARKER_ENV.items():
            with self.subTest(label), mock.patch.dict(os.environ, updates):
                self.assertEqual(self.login(client).status_code, 404)
                self.assertEqual(client.get('/api/v1/dev/users').status_code, 404)
                self.assertEqual(client.post('/api/v1/dev/refresh', json={'refresh_token': tokens['refresh_token']}).status_code, 404)
                self.assertEqual(client.post('/api/v1/dev/logout', headers={'Authorization': 'Bearer ' + tokens['access_token']}).status_code, 404)
        with mock.patch.dict(os.environ, {harness.FLAG: '0'}):
            self.assertEqual(self.login(client).status_code, 404)
        self.assertEqual(self.login(client).status_code, 200)

    def test_every_dev_login_is_logged_without_tokens(self):
        _app, client = self.active_app()
        with self.assertLogs('dhashu.local_harness', level='WARNING') as logs:
            tokens = self.login(client, 'u_0002').get_json()
        line = '\n'.join(logs.output)
        self.assertIn('user_id=u_0002', line)
        self.assertIn('peer=127.0.0.1', line)   # sec-ip: label only; the logged value is still the TCP peer
        self.assertRegex(line, r'at=\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\+00:00')
        for secret in (tokens['access_token'], tokens['refresh_token']):
            self.assertNotIn(secret, line)

    def test_users_lists_seeded_ids_only(self):
        # Non-seeded local rows (a real-style member id, look-alikes) must never be offered.
        for name, user in zip(('test_blr_20260921_f01', 'member-42', 'u', 'xu_1', 'U_0003', 'tester_1', 'test-1'),
                              generate_users.generate_users(7, seed=9)):
            row = app_module.onboarding.build_user_row(user_id=name, city=user['city'], gender=user['gender'],
                                                       stats=user['stats'], visions=user['visions'], activities={})
            row['journey_state'] = 'dating'
            db.insert_row(self.conn, 'User', row)
        _app, client = self.active_app()
        body = client.get('/api/v1/dev/users').get_json()
        self.assertEqual([u['user_id'] for u in body['users']], ['test_blr_20260921_f01', 'u_0001', 'u_0002'])
        self.assertEqual(body['users'][1], {'user_id': 'u_0001', 'journey_state': 'dating'})

    def test_refresh_rotates_harness_tokens_and_rejects_reuse_and_real_tokens(self):
        _app, client = self.active_app()
        first = self.login(client).get_json()
        rotated = client.post('/api/v1/dev/refresh', json={'refresh_token': first['refresh_token']})
        self.assertEqual(rotated.status_code, 200)
        self.assertEqual(rotated.get_json()['session_id'], first['session_id'])
        reused = client.post('/api/v1/dev/refresh', json={'refresh_token': first['refresh_token']})
        self.assertEqual(reused.status_code, 401)  # reuse revokes the family, as in real login
        with sessions.transaction(self.conn):
            real = sessions.issue_in_transaction(self.conn, 'u_0002', 'mobile')
        self.assertEqual(client.post('/api/v1/dev/refresh', json={'refresh_token': real['refresh_token']}).status_code, 401)
        self.assertEqual(client.post('/api/v1/dev/refresh', json={}).status_code, 401)

    def test_logout_revokes_the_harness_session(self):
        _app, client = self.active_app()
        tokens = self.login(client).get_json()
        bearer = {'Authorization': 'Bearer ' + tokens['access_token']}
        self.assertEqual(client.post('/api/v1/dev/logout', headers=bearer).status_code, 200)
        self.assertEqual(client.post('/api/v1/dev/logout', headers=bearer).status_code, 401)
        self.assertEqual(client.post('/api/v1/dev/refresh', json={'refresh_token': tokens['refresh_token']}).status_code, 401)


# ── D/E. the real app: current_user(), real login unchanged ──────────────
class AppIntegrationTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self._harness_config = app_module.app.config.get(harness.CONFIG_KEY)
        app_module.app.config[harness.CONFIG_KEY] = False
        self.addCleanup(app_module.app.config.__setitem__, harness.CONFIG_KEY, self._harness_config)
        for name, user in zip(('owner', 'other'), generate_users.generate_users(2, seed=11)):
            row = app_module.onboarding.build_user_row(user_id=name, city=user['city'], gender=user['gender'],
                                                       stats=user['stats'], visions=user['visions'], activities={})
            row['bgv_status'] = 'verified'
            row['journey_state'] = 'dating'
            row['preferences_json'] = json.dumps(user['preferences'])
            db.insert_row(self.conn, 'User', row)
        # 'owner' also has a real, enabled Account (as a real member would).
        db.insert_row(self.conn, 'Account', {'id': 'account-owner', 'user_id': 'owner', 'email': 'owner@example.test',
                                             'phone': '919876543210', 'auth_enabled': 1, 'created_at': 'test'})

    def issue(self, user_id, **kind):
        with sessions.transaction(self.conn):
            return sessions.issue_in_transaction(self.conn, user_id, 'mobile', **kind)

    def harness_on(self):
        stack = [patched_env(**{harness.FLAG: '1', 'DHASHU_PAYMENT_BYPASS': '1', 'DEMO_MODE': '1', 'DHASHU_SIMULATED_CLOCK': 'true'}),
                 mock.patch.dict(app_module.app.config, {harness.CONFIG_KEY: True})]
        for item in stack:
            item.start()
            self.addCleanup(item.stop)

    def me(self, token, **kwargs):
        return self.client.get('/api/v1/me', headers={'Authorization': 'Bearer ' + token}, **kwargs)

    def test_the_real_app_does_not_register_dev_routes_by_default(self):
        key = 'synthetic-test-secret-key-that-is-at-least-32-characters'
        with patched_env(AUTH_ENABLED='1', AUTH_PUBLIC_ORIGIN='https://beta.example.test',
                         SECRET_KEY=key, TWILIO_ACCOUNT_SID='AC' + 'a' * 32,
                         TWILIO_VERIFY_SERVICE_SID='VA' + 'b' * 32,
                         TWILIO_AUTH_TOKEN='test-only', RAILWAY_ENVIRONMENT='production'):
            result = StartupTests().import_app(AUTH_ENABLED='1', AUTH_PUBLIC_ORIGIN='https://beta.example.test',
                                               SECRET_KEY=key, TWILIO_ACCOUNT_SID='AC' + 'a' * 32,
                                               TWILIO_VERIFY_SERVICE_SID='VA' + 'b' * 32,
                                               TWILIO_AUTH_TOKEN='test-only', RAILWAY_ENVIRONMENT='production')
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertIn('ACTIVE False []', result.stdout)

    def test_harness_bearer_signs_in_only_while_active(self):
        token = self.issue('other', harness=True)['access_token']
        self.assertEqual(self.me(token).status_code, 401)  # registered off: ignored
        self.harness_on()
        response = self.me(token)
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()['data']['user_id'], 'other')
        self.assertEqual(self.me(token, environ_base={'REMOTE_ADDR': '10.0.0.9'}).status_code, 401)
        with mock.patch.dict(os.environ, {'RAILWAY_ENVIRONMENT': 'production'}):
            with mock.patch('auth.resolve', return_value=None):
                self.assertEqual(self.me(token).status_code, 401)
        with mock.patch.dict(os.environ, {harness.FLAG: '0'}):
            self.assertEqual(self.me(token).status_code, 401)

    def test_emulator_host_keeps_the_picked_local_user_signed_in(self):
        # The Android emulator reaches the laptop as Host 10.0.2.2 (peer 127.0.0.1).
        # sec-login review: auth.enabled() must treat it as the local harness, or the
        # member is answered 401 authentication_required and the app signs them out.
        token = self.issue('other', harness=True)['access_token']
        self.harness_on()
        emulator = {'base_url': 'http://10.0.2.2:5000'}
        response = self.me(token, **emulator)
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()['data']['user_id'], 'other')
        write = self.client.post('/api/v1/week/prepare', json={}, headers={'Authorization': 'Bearer ' + token}, **emulator)
        self.assertNotEqual(write.status_code, 401, write.get_json())
        loopback = {'environ_base': {'REMOTE_ADDR': '127.0.0.1'}}
        with app_module.app.test_request_context('/api/v1/me', headers={'Authorization': 'Bearer ' + token},
                                                 **emulator, **loopback):
            self.assertFalse(auth.enabled())
            app_module.current_user()
            self.assertEqual(auth.bearer_session()['user_id'], 'other')
        # Any other host, a forwarded request or a non-loopback peer: real sign-in rules.
        for extra in ({'base_url': 'http://evil.example'}, {'headers': {'X-Forwarded-For': '1.2.3.4'}},
                      {'environ_base': {'REMOTE_ADDR': '10.0.2.2'}}):
            with app_module.app.test_request_context('/api/v1/me', **{**emulator, **loopback, **extra}):
                self.assertTrue(auth.enabled(), extra)

    def test_invalid_bearer_never_falls_back_to_the_cookie_session(self):
        self.harness_on()
        self.assertEqual(self.client.post('/login/owner').status_code, 302)
        self.assertEqual(self.client.get('/api/v1/me').status_code, 200)  # cookie alone still works
        self.assertEqual(self.me('x' * 43).status_code, 401)

    def test_real_tokens_are_never_accepted_on_the_harness_path(self):
        self.harness_on()
        real = self.issue('owner')
        self.assertEqual(self.me(real['access_token']).status_code, 401)
        tester = self.issue('owner', tester=True)
        self.assertEqual(self.me(tester['access_token']).status_code, 401)

    def test_harness_tokens_are_rejected_by_the_real_sign_in_path(self):
        harness_tokens = self.issue('owner', harness=True)  # owner even has an enabled Account
        for env in ({}, {harness.FLAG: '1'}, {harness.FLAG: '1', 'AUTH_ENABLED': 'true'}):
            with self.subTest(env=env), patched_env(**env):
                self.assertIsNone(sessions.authenticate(self.conn, harness_tokens['access_token'], 'mobile'))
                self.assertIsNone(sessions.refresh(self.conn, harness_tokens['refresh_token']))
        with patched_env(), mock.patch.dict(app_module.app.config, {'AUTH_ENABLED': True}):
            self.assertEqual(self.me(harness_tokens['access_token']).status_code, 401)

    def test_real_login_tokens_are_unchanged(self):
        for env in ({}, {harness.FLAG: '1'}):
            with self.subTest(env=env), patched_env(**env):
                real = self.issue('owner')
                self.assertFalse(real['session_id'].startswith(('harness_', 'tester_')))
                self.assertEqual(sessions.authenticate(self.conn, real['access_token'], 'mobile')['user_id'], 'owner')
                rotated = sessions.refresh(self.conn, real['refresh_token'])
                self.assertEqual(rotated['user_id'], 'owner')
                self.assertIsNone(sessions.refresh(self.conn, rotated['refresh_token'], harness=True))
        with self.assertRaises(ValueError):
            self.issue('owner', tester=True, harness=True)


# ── F. the real process: startup refusal ──────────────────────────────────
class StartupTests(unittest.TestCase):
    def import_app(self, **updates):
        env = clean_env(**updates)
        env['PYTHONIOENCODING'] = 'utf-8'
        code = ("import json, app; print('ACTIVE', app.app.config['LOCAL_HARNESS_ACTIVE'], "
                "sorted(r.rule for r in app.app.url_map.iter_rules() if r.rule.startswith('/api/v1/dev')))\n"
                "if app.app.config['LOCAL_HARNESS_ACTIVE']:\n"
                "    r = app.app.test_client().post('/api/v1/dev/login-as', json={'user_id': ''})\n"
                "    print('ENVELOPE', r.status_code, json.dumps(r.get_json(), sort_keys=True))")
        return subprocess.run([sys.executable, '-c', code], cwd=REPO, env=env, capture_output=True, text=True, timeout=120)

    def test_app_refuses_to_boot_with_flag_and_a_production_marker(self):
        for updates in ({'RAILWAY_ENVIRONMENT': 'production'}, {'RAILWAY_PROJECT_ID': 'p'},
                        {'DATABASE_URL': 'postgresql://u:pw@db.example.com/app'}, {'DHASHU_PROCESS_ROLE': 'web'}):
            with self.subTest(updates=list(updates)):
                result = self.import_app(**{harness.FLAG: '1'}, **updates)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('DHASHU_LOCAL_HARNESS=1 is local-only and refused', result.stderr)

    def test_app_boots_with_flag_locally_and_refuses_auth_off_without_flag(self):
        local = self.import_app(**{harness.FLAG: '1'})
        self.assertEqual(local.returncode, 0, local.stderr[-2000:])
        self.assertIn("ACTIVE True ['/api/v1/dev/login-as', '/api/v1/dev/logout', '/api/v1/dev/refresh', '/api/v1/dev/users']", local.stdout)
        self.assertIn('LOCAL HARNESS ACTIVE', local.stderr)
        # Through the real app's /api/v1 envelope: same error shape the mobile client parses.
        import json as _json, re as _re
        line = next(l for l in local.stdout.splitlines() if l.startswith('ENVELOPE '))
        status, body = line.split(' ', 2)[1:]
        envelope = _json.loads(body)
        self.assertEqual(status, '400')
        self.assertIsNone(envelope['data'])
        # mon-sentry: 'reference' carries the request id so support can trace the log line.
        reference = envelope['error'].pop('reference')
        self.assertRegex(reference, r'^[0-9a-f]{32}$')
        self.assertEqual(envelope['error'], {'code': 'validation_error', 'detail': None, 'message': 'Choose a local user.'})
        production_shape = self.import_app(RAILWAY_ENVIRONMENT='production')
        self.assertNotEqual(production_shape.returncode, 0)
        self.assertIn('AUTH_ENABLED may be disabled only with DHASHU_LOCAL_HARNESS=1', production_shape.stderr)


class DeploymentConfigTests(unittest.TestCase):
    def test_no_deployment_config_sets_the_harness_flag(self):
        for name in ('Procfile', 'codemagic.yaml', '.railwayignore', 'service_entrypoint.py'):
            self.assertNotIn(harness.FLAG, (REPO / name).read_text(encoding='utf-8'), name)
        for pattern in ('railway*.json', 'railway*.toml', 'nixpacks*', 'Dockerfile*'):
            for path in REPO.glob(pattern):
                self.assertNotIn(harness.FLAG, path.read_text(encoding='utf-8'), path.name)


if __name__ == '__main__':
    unittest.main()
