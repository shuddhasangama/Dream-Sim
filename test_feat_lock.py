"""sec-admin + feat-lock: owner-only lock/unlock with a reason; locked members cannot sign in."""
import unittest
from unittest import mock

import auth_sessions as sessions
import member_lock
import test_admin_dashboard
import test_auth

ORIGIN = {'Origin': 'http://localhost'}
REASON = 'Reported for harassment, ticket 4411'


class AdminLockTests(unittest.TestCase):
    def setUp(self):
        self.f = test_admin_dashboard.AdminDashboardTests('test_rfc_totp')
        self.f.setUp()
        self.addCleanup(self.f.tearDown)
        self.conn, self.client = self.f.conn, self.f.client

    def headers(self):
        return {**ORIGIN, 'X-CSRF-Token': self.f.csrf()}

    def lock(self, body, headers=None, path='/api/members/lock'):
        return self.client.post(path, json=body, headers=headers if headers is not None else self.headers())

    def test_owner_locks_with_reason_sessions_revoked_everything_recorded(self):
        member_session = sessions.issue(self.conn, 'u1')
        self.assertEqual(self.f.login().status_code, 200)
        self.assertEqual(self.lock({'user_id': 'u1', 'reason': REASON}, headers=ORIGIN).status_code, 403)   # no CSRF
        for bad in ({'user_id': 'u1'}, {'user_id': 'u1', 'reason': 'short'}, {'user_id': 'u1', 'reason': REASON, 'x': 1}):
            self.assertEqual(self.lock(bad).status_code, 400, bad)
        self.assertEqual(self.lock({'user_id': 'nobody', 'reason': REASON}).status_code, 404)
        self.assertEqual(self.lock({'user_id': 'seed_without_account', 'reason': REASON}).status_code, 404)
        response = self.lock({'user_id': 'u1', 'reason': REASON})
        self.assertEqual(response.status_code, 200, response.text)
        account = self.conn.execute('SELECT locked_at, lock_reason FROM "Account" WHERE user_id = ?', ('u1',)).fetchone()
        self.assertIsNotNone(account['locked_at'])
        self.assertEqual(account['lock_reason'], REASON)
        revoked = self.conn.execute('SELECT revoked_at FROM "AuthSession" WHERE id = ?', (member_session['session_id'],)).fetchone()
        self.assertIsNotNone(revoked['revoked_at'])
        self.assertEqual(self.lock({'user_id': 'u1', 'reason': REASON}).status_code, 400)                 # already locked
        events = [tuple(r) for r in self.conn.execute('SELECT user_id, action, reason FROM "MemberLockEvent"')]
        self.assertEqual(events, [('u1', 'lock', REASON)])
        audit = [r['action'] for r in self.conn.execute('SELECT action FROM "AdminAudit"')]
        self.assertIn('member_lock', audit)
        self.assertIn(('u1', 'member_lock'), [tuple(r) for r in self.conn.execute('SELECT user_id, kind FROM "SecurityEvent"')])
        summary = self.client.post('/api/user-summary', json={'user_id': 'u1'}, headers=self.headers()).get_json()
        self.assertTrue(summary['account'][0]['locked'])
        self.assertTrue(summary['can_lock'])
        self.assertEqual(summary['lock_history'][0]['reason'], REASON)
        unlocked = self.lock({'user_id': 'u1', 'reason': 'Investigation closed, ticket 4411'}, path='/api/members/unlock')
        self.assertEqual(unlocked.status_code, 200)
        self.assertIsNone(self.conn.execute('SELECT locked_at FROM "Account" WHERE user_id = ?', ('u1',)).fetchone()[0])
        self.assertIn('member_unlock', [r['action'] for r in self.conn.execute('SELECT action FROM "AdminAudit"')])
        self.assertEqual(self.lock({'user_id': 'u1', 'reason': REASON}, path='/api/members/unlock').status_code, 400)

    def test_only_owners_can_lock_or_unlock(self):
        self.assertEqual(self.f.login().status_code, 200)
        for role in ('support', 'marketing'):
            # roles are read on every request; a second login would reuse the TOTP code
            self.conn.execute('UPDATE "AdminIdentity" SET role = ?', (role,)); self.conn.commit()
            for path in ('/api/members/lock', '/api/members/unlock'):
                self.assertEqual(self.lock({'user_id': 'u1', 'reason': REASON}, path=path).status_code, 403, (role, path))
        self.assertIsNone(self.conn.execute('SELECT locked_at FROM "Account" WHERE user_id = ?', ('u1',)).fetchone()[0])

    def test_every_owner_report_view_is_audited(self):
        self.f.login()
        before = self.conn.execute('SELECT COUNT(*) FROM "AdminAudit"').fetchone()[0]
        for path in ('/api/reports/markets', '/api/reports/activities'):
            self.assertEqual(self.client.get(path).status_code, 200)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM "AdminAudit"').fetchone()[0], before + 2)


class LockedMemberSignInTests(unittest.TestCase):
    def setUp(self):
        self.f = test_auth.AuthenticationTests('test_optional_tester_login_and_revocation')
        self.f.setUp()
        self.addCleanup(self.f.doCleanups)

    def clear_pacing(self):
        # the 60 s per-number code pacing (sec-otp) is not what this test is about
        self.f.conn.execute('DELETE FROM "AuthThrottle"'); self.f.conn.commit()

    def test_locked_member_sees_a_clear_message_and_cannot_sign_in_by_any_route(self):
        f = self.f
        tokens = f.login_mobile()
        member_lock.lock(f.conn, 'owner', 'admin-1', REASON)
        self.assertEqual(f.client.get('/api/v1/me', headers=f.bearer(tokens)).status_code, 401)
        self.assertEqual(f.post('refresh', {'refresh_token': tokens['refresh_token']}).status_code, 401)
        self.clear_pacing()
        challenge = f.challenge()
        refused = f.post('verify', {'challenge_id': challenge, 'code': '123456'})
        self.assertEqual(refused.status_code, 403)
        self.assertEqual(refused.json['error']['code'], 'account_locked')
        self.assertEqual(refused.json['error']['message'], member_lock.MESSAGE)
        with mock.patch.dict('os.environ', {'DHASHU_TESTER_NO_OTP': 'true', 'DHASHU_TESTER_USER_IDS': 'owner'}):
            self.assertEqual(f.post('tester', {'phone': '+919876543210'}).status_code, 403)
        with self.assertRaises(member_lock.AccountLocked):
            sessions.issue(f.conn, 'owner')
        self.assertTrue(member_lock.is_locked(f.conn, 'owner'))
        member_lock.unlock(f.conn, 'owner', 'admin-1', 'Investigation closed, ticket 4411')
        self.clear_pacing()
        self.assertEqual(f.client.get('/api/v1/me', headers=f.bearer(f.login_mobile())).status_code, 200)


if __name__ == '__main__':
    unittest.main()
