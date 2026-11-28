"""Client answer 9: the store reviewer account. Synthetic phone and password only."""
import io
import json
import os
from contextlib import redirect_stdout
from unittest import mock

import account_deletion
import db
import reviewer_accounts
import week_service
import test_auth
from tools import create_reviewer_account as tool

PHONE = '+919000000555'          # synthetic test number
PASSWORD = 'Synthetic-Reviewer-Pass-1'


# The secure-auth fixture only: AuthenticationTests' own tests are not re-run here.
_SecureAuthFixture = type('_SecureAuthFixture', (test_auth.AuthenticationTests,),
                          {name: None for name in dir(test_auth.AuthenticationTests) if name.startswith('test_')})


class ReviewerAccountTests(_SecureAuthFixture):
    def run_tool(self, argv=('--apply',), answers=(PHONE, PASSWORD, PASSWORD), yes='YES'):
        replies = iter(answers)
        out = io.StringIO()
        with redirect_stdout(out):
            code = tool.main(list(argv), ask=lambda _prompt: next(replies), confirm=lambda _prompt: yes,
                             connect=lambda: self._shared())
        return code, out.getvalue()

    def _shared(self):
        class Keep:                       # the tool closes its connection; keep the test's open
            def __init__(s, conn): s._c = conn
            def __getattr__(s, name): return getattr(s._c, name)
            def close(s): pass
        return Keep(self.conn)

    def reviewer(self):
        row = self.conn.execute('SELECT * FROM "Account" WHERE reviewer = 1').fetchall()
        self.assertEqual(len(row), 1)
        return dict(row[0])

    # ── the tool ──────────────────────────────────────────────────────────
    def test_refuses_without_apply_and_asks_nothing(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = tool.main([], ask=mock.Mock(side_effect=AssertionError('asked')), confirm=mock.Mock(side_effect=AssertionError('asked')))
        self.assertEqual(code, 2)
        self.assertIn('nothing was changed', out.getvalue())
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM "Account" WHERE reviewer = 1').fetchone()[0], 0)

    def test_creates_then_updates_one_reviewer_and_never_prints_the_secrets(self):
        code, out = self.run_tool()
        self.assertEqual(code, 0, out)
        self.assertIn('Reviewer account created', out)
        first = self.reviewer()
        code, out2 = self.run_tool(answers=(PHONE, 'Second-Synthetic-Pass-2', 'Second-Synthetic-Pass-2'))
        self.assertEqual(code, 0, out2)
        self.assertIn('Reviewer account updated', out2)
        self.assertEqual(self.reviewer()['user_id'], first['user_id'])
        for text in (out, out2):
            self.assertNotIn('9000000555', text)
            self.assertNotIn('Synthetic-Reviewer-Pass-1', text)
            self.assertNotIn('Second-Synthetic-Pass-2', text)
        self.assertNotIn(PASSWORD, self.reviewer()['password_hash'])
        self.assertTrue(self.reviewer()['password_hash'].startswith('scrypt:'))

    def test_cancel_mismatch_and_bad_input_change_nothing(self):
        self.assertEqual(self.run_tool(yes='no')[0], 1)
        self.assertEqual(self.run_tool(answers=(PHONE, PASSWORD, 'different-password-x'))[0], 2)
        self.assertEqual(self.run_tool(answers=('12345', PASSWORD, PASSWORD))[0], 2)
        self.assertEqual(self.run_tool(answers=(PHONE, 'short', 'short'))[0], 2)
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM "Account" WHERE reviewer = 1').fetchone()[0], 0)

    def test_never_turns_a_member_into_a_reviewer_and_keeps_one_reviewer(self):
        code, out = self.run_tool(answers=('+919876543210', PASSWORD, PASSWORD))   # the member 'owner'
        self.assertEqual(code, 2)
        self.assertIn('belongs to a member account', out)
        self.assertEqual(self.run_tool()[0], 0)
        code, out = self.run_tool(answers=('+919000000556', PASSWORD, PASSWORD))
        self.assertEqual(code, 2)
        self.assertIn('Another reviewer account already exists', out)

    def test_works_under_prod_guard_without_any_test_switch(self):
        import prod_guard
        with mock.patch.dict(os.environ, {'RAILWAY_ENVIRONMENT': 'production'}):
            for name in prod_guard.TEST_SWITCHES:          # the route fixture turns some on; production has none
                os.environ.pop(name, None)
            self.assertEqual(self.run_tool()[0], 0)
        with mock.patch.dict(os.environ, {'RAILWAY_ENVIRONMENT': 'production', 'DHASHU_TESTER_NO_OTP': 'true'}):
            code, out = self.run_tool()
        self.assertEqual(code, 2)
        self.assertIn('Test-only settings are forbidden in production', out)
        with mock.patch.dict(os.environ, {'SECRET_KEY': 'short'}):
            self.assertEqual(self.run_tool()[0], 2)

    def test_tool_takes_no_secret_from_arguments(self):
        with self.assertRaises(SystemExit), redirect_stdout(io.StringIO()), mock.patch('sys.stderr', io.StringIO()):
            tool.main(['--apply', '--phone', PHONE])
        with self.assertRaises(SystemExit), redirect_stdout(io.StringIO()), mock.patch('sys.stderr', io.StringIO()):
            tool.main(['--apply', '--password', PASSWORD])

    # ── signing in and what the reviewer sees ──────────────────────────────
    def test_reviewer_signs_in_with_phone_and_password_and_no_sms(self):
        self.run_tool()
        self.start.reset_mock(); self.check.reset_mock()
        challenges = self.conn.execute('SELECT COUNT(*) FROM "AuthChallenge"').fetchone()[0]
        r = self.post('password/login', {'identifier': PHONE, 'password': PASSWORD})
        self.assertEqual(r.status_code, 200, r.json)
        self.start.assert_not_called(); self.check.assert_not_called()       # no OTP sent or checked
        self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM "AuthChallenge"').fetchone()[0], challenges)
        headers = self.bearer(r.json['data'])
        state = self.client.get('/api/v1/signup/state', headers=headers)
        self.assertEqual(state.status_code, 200, state.json)
        self.assertTrue(state.json['data']['admitted'])                        # verification gates skipped
        self.assertEqual(state.json['data']['next_step'], 3)
        me = self.client.get('/api/v1/me', headers=headers)
        self.assertEqual(me.status_code, 200)
        self.assertEqual(self.post('password/login', {'identifier': PHONE, 'password': 'wrong-password-123'}).status_code, 400)

    def test_reviewer_is_never_shown_to_or_matched_with_members(self):
        self.run_tool()
        uid = self.reviewer()['user_id']
        self.assertIn(uid, account_deletion.hidden_ids(self.conn))
        self.assertTrue(reviewer_accounts.is_reviewer(self.conn, uid))
        self.assertFalse(reviewer_accounts.is_reviewer(self.conn, 'owner'))
        from clock import SimulationClock
        self.assertEqual(week_service.prepare(self.conn, uid, SimulationClock.at(1, 'Tue', 12)), [])
        self.assertEqual(db.fetch_all(self.conn, 'Match', user_id=uid), [])
        stats = json.loads(db.fetch_one(self.conn, 'User', id=uid)['stats_json'])
        self.assertTrue(stats['reviewer'])
        events = [r['kind'] for r in self.conn.execute('SELECT kind FROM "SecurityEvent" WHERE user_id = ?', (uid,))]
        self.assertIn('reviewer_account_created', events)
