"""feat-delete + feat-purge: delete with a 30-day grace period, then a permanent purge."""
import json
import os
import unittest
from unittest import mock

from werkzeug.security import generate_password_hash

import account_deletion
import auth_sessions as sessions
import db
import member_lock
import provider_jobs
import test_evolution_api

PASSWORD = 'Correct-horse-battery-1'
DAY = 86400


class DeletionTests(unittest.TestCase):
    def setUp(self):
        self.f = test_evolution_api.EvolutionApiTests('test_marriage_preset_owned_atomic_and_retry_safe')
        self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.conn = self.f.conn
        c = self.conn
        c.execute('UPDATE Account SET password_hash = ?, phone = ? WHERE user_id = ?', (generate_password_hash(PASSWORD), '+919876500011', 'owner'))
        # a shared history with the partner: a date with both sides' Debrief, a couple, an exit
        db.insert_row(c, 'DatePlan', {'id': 'plan-1', 'lockin_id': 'lock-1', 'datetime': '2026-01-10T19:30', 'meal': 'dinner',
                                      'venue': 'Toit', 'cuisine': 'Thai', 'budget_estimate': '1500', 'bill_split': 'pay-your-own', 'status': 'completed'})
        db.insert_row(c, 'DateOutcome', {'id': 'out-1', 'dateplan_id': 'plan-1', 'happened': 1, 'a_reason': 'OWNER PRIVATE REASON',
                                         'b_reason': 'partner reason', 'a_green_flags_json': '["kind"]', 'b_green_flags_json': '["warm"]'})
        db.insert_row(c, 'Payment', {'id': 'pay-1', 'user_id': 'owner', 'purpose': 'agreement', 'scope_id': 'plan-1', 'amount_inr': 499,
                                     'status': 'paid', 'reference': 'pay_ref_1', 'created_at': '1'})
        db.insert_row(c, 'ProfilePhoto', {'id': 'owner', 'data_url': 'data:image/jpeg;base64,OWNERPHOTO'})
        c.commit()
        sessions.record_security_event(c, 'owner', 'test_event', None); c.commit()
        self.token = sessions.issue(c, 'owner')

    def request(self, body):
        return self.f.post('/account/deletion', body)

    def sign_in_again(self):
        # a deletion request revokes every session: the member signs in again to cancel
        self.f.headers['owner'] = {'Authorization': 'Bearer ' + sessions.issue(self.conn, 'owner')['access_token']}

    def cells(self):
        """Every cell of every table, as text."""
        out = []
        for table in sorted(db.TABLES):
            for row in self.conn.execute(f'SELECT * FROM "{table}"').fetchall():
                out += [(table, str(v)) for v in tuple(row) if v is not None]
        return out

    def run_jobs(self, at):
        with mock.patch('auth_sessions.now', return_value=at), mock.patch('provider_jobs.now', return_value=at):
            while provider_jobs.work_one(self.conn, [account_deletion.JOB_KIND]):
                pass

    def test_request_needs_confirmation_then_hides_and_signs_out(self):
        self.assertEqual(self.request({}).status_code, 400)
        self.assertEqual(self.request({'password': 'wrong'}).status_code, 400)
        r = self.request({'password': PASSWORD})
        self.assertEqual(r.status_code, 200, r.json)
        self.assertTrue(r.json['data']['scheduled'])
        due = r.json['data']['due_at']
        self.assertAlmostEqual(due - sessions.now(), 30 * DAY, delta=60)
        self.assertEqual(self.f.client.get('/api/v1/me', headers={'Authorization': 'Bearer ' + self.token['access_token']}).status_code, 401)
        self.assertIn('owner', account_deletion.hidden_ids(self.conn))
        import app as app_module
        with app_module.app.test_request_context('/'):
            shown = app_module.named_for('partner', {'user_id': 'owner', 'gender': 'female'})
            pool, _ = app_module.reach_pool({'user_id': 'partner', 'bgv_status': 'verified'})
        self.assertEqual((shown['name'], shown['unavailable']), ('No longer available', True))
        self.assertNotIn('owner', [u['user_id'] for u in pool])
        self.sign_in_again()
        self.assertEqual(self.f.request('/journey/status').json['data']['account_deletion']['due_at'], due)

    def test_confirm_with_a_one_time_code(self):
        with mock.patch('auth_delivery.configured', return_value=True), mock.patch('auth_delivery.start', return_value='VE' + 'c' * 32), \
             mock.patch('auth_delivery.check', side_effect=lambda sid, code: code == '123456'):
            challenge = self.f.post('/account/deletion/code', {}).json['data']['challenge_id']
            self.assertEqual(self.request({'challenge_id': challenge, 'code': '000000'}).status_code, 400)
            self.assertEqual(self.request({'challenge_id': challenge, 'code': '123456'}).status_code, 200)
            self.sign_in_again()
            self.assertEqual(self.request({'challenge_id': challenge, 'code': '123456'}).status_code, 400)   # a used code never works twice
        self.assertIsNotNone(account_deletion.scheduled(self.conn, 'owner'))

    def test_cancel_restores_everything(self):
        self.request({'password': PASSWORD})
        self.sign_in_again()
        r = self.f.post('/account/deletion/cancel', {})
        self.assertFalse(r.json['data']['scheduled'])
        self.assertNotIn('owner', account_deletion.hidden_ids(self.conn))
        self.assertNotIn('account_deletion', self.f.request('/journey/status').json['data'])
        self.run_jobs(sessions.now() + 31 * DAY)                       # the cancelled job never purges
        self.assertIsNotNone(db.fetch_one(self.conn, 'User', id='owner'))

    def test_purge_after_the_grace_period_leaves_no_trace(self):
        secrets_of_owner = ('owner', '+919876500011', 'owner@test.example', 'OWNER PRIVATE REASON', 'OWNERPHOTO')
        self.request({'password': PASSWORD})
        self.run_jobs(sessions.now() + 29 * DAY)                       # not due yet: nothing happens
        self.assertIsNotNone(db.fetch_one(self.conn, 'User', id='owner'))
        self.run_jobs(sessions.now() + 31 * DAY)
        leaks = [(t, v[:60]) for t, v in self.cells() for s in secrets_of_owner if s in v and not v.startswith('deleted_')
                 and not (s == 'owner' and 'deleted_' in v)]
        self.assertEqual(leaks, [])                                   # every table scanned
        tomb = account_deletion.tombstone_id('owner')
        lock = db.fetch_one(self.conn, 'LockIn', id='lock-1')
        self.assertEqual({lock['user_a'], lock['user_b']}, {tomb, 'partner'})   # the partner keeps the history
        outcome = db.fetch_one(self.conn, 'DateOutcome', id='out-1')
        mine = 'a' if lock['user_a'] == tomb else 'b'; theirs = 'b' if mine == 'a' else 'a'
        self.assertIsNone(outcome[f'{mine}_reason']); self.assertEqual(outcome[f'{mine}_green_flags_json'], '[]')
        self.assertEqual(outcome[f'{theirs}_reason'], 'partner reason' if theirs == 'b' else 'OWNER PRIVATE REASON')
        payment = db.fetch_one(self.conn, 'Payment', id='pay-1')
        self.assertEqual((payment['user_id'], payment['amount_inr'], payment['status']), (tomb, 499, 'paid'))   # kept for the law
        self.assertTrue(db.fetch_all(self.conn, 'SecurityEvent', user_id=tomb))                              # kept until retention
        self.assertIsNone(db.fetch_one(self.conn, 'Account', user_id='owner'))
        record = db.fetch_all(self.conn, 'DeletionRecord')
        self.assertEqual(len(record), 1); self.assertGreater(record[0]['rows_deleted'], 0)
        self.assertNotIn('owner', json.dumps(record))
        self.assertIsNone(account_deletion.purge(self.conn, 'owner'))   # idempotent
        self.run_jobs(sessions.now() + 40 * DAY)
        self.assertEqual(len(db.fetch_all(self.conn, 'DeletionRecord')), 1)
        self.assertIsNotNone(db.fetch_one(self.conn, 'User', id='partner'))

    def test_locked_member_is_purged_and_lock_history_is_anonymised(self):
        member_lock.lock(self.conn, 'owner', 'admin-1', 'Reported, ticket 9001')
        account_deletion.request_deletion(self.conn, 'owner')
        self.run_jobs(sessions.now() + 31 * DAY)
        tomb = account_deletion.tombstone_id('owner')
        self.assertEqual([r['reason'] for r in db.fetch_all(self.conn, 'MemberLockEvent', user_id=tomb)], ['Reported, ticket 9001'])
        self.assertEqual(db.fetch_all(self.conn, 'MemberLockEvent', user_id='owner'), [])

    def test_retention_removes_old_security_records_only(self):
        old = sessions.now() - 200 * DAY
        self.conn.execute('INSERT INTO "SecurityEvent" (id, user_id, kind, detail, created_at) VALUES (?, ?, ?, ?, ?)', ('old', 'x', 'k', None, old))
        self.conn.execute('INSERT INTO "MemberLockEvent" (id, user_id, action, reason, admin_id, created_at) VALUES (?, ?, ?, ?, ?, ?)',
                          ('oldlock', 'x', 'lock', 'an old reason', 'a', old))
        self.conn.commit()
        self.assertEqual(account_deletion.apply_retention(self.conn), 2)
        self.assertTrue(db.fetch_all(self.conn, 'SecurityEvent', kind='test_event'))   # recent ones stay
        with mock.patch.dict(os.environ, {'DHASHU_SECURITY_RETENTION_DAYS': '8'}), \
             mock.patch('auth_sessions.now', return_value=sessions.now() + 10 * DAY):   # the floor is 7 days
            account_deletion.apply_retention(self.conn)
        self.assertEqual(db.fetch_all(self.conn, 'SecurityEvent'), [])

    # ── client answer 7: only the contact hash and the exit type remain, for 2 years ──
    def retained(self):
        return db.fetch_all(self.conn, 'DeletedContactRetention')

    def test_purge_keeps_only_a_contact_hash_and_the_exit_type(self):
        self.request({'password': PASSWORD})
        self.run_jobs(sessions.now() + 31 * DAY)
        rows = self.retained()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual((row['contact_kind'], row['exit_type']), ('phone', 'good_exit'))
        self.assertRegex(row['contact_index'], r'^[0-9a-f]{64}$')
        self.assertEqual(set(row), {'id', 'contact_kind', 'contact_index', 'index_key', 'exit_type', 'purged_at', 'delete_after'})
        self.assertAlmostEqual(row['delete_after'] - row['purged_at'], 730 * DAY, delta=1)   # default 2 years
        text = json.dumps(row)
        for secret in ('owner', '9876500011', 'owner@test.example'):
            self.assertNotIn(secret, text)                                # no member id, no readable contact
        self.assertEqual([r['exit_type'] for r in account_deletion.find_deleted_contact(self.conn, '+919876500011')], ['good_exit'])
        self.assertEqual(account_deletion.find_deleted_contact(self.conn, '+919876500099'), [])

    def test_locked_or_reported_member_is_a_bad_exit(self):
        member_lock.lock(self.conn, 'owner', 'admin-1', 'Reported, ticket 9001')
        self.assertEqual(account_deletion.exit_type(self.conn, 'owner'), 'bad_exit')
        self.assertEqual(account_deletion.exit_type(self.conn, 'partner'), 'good_exit')
        db.insert_row(self.conn, 'ComplianceEvent', {'id': 'c1', 'user_id': 'partner', 'type': 'late_cancel', 'week': 1})
        self.conn.commit()
        self.assertEqual(account_deletion.exit_type(self.conn, 'partner'), 'good_exit')   # a late cancel is not a bad exit
        db.insert_row(self.conn, 'ComplianceEvent', {'id': 'c2', 'user_id': 'partner', 'type': 'report', 'week': 1})
        self.conn.commit()
        self.assertEqual(account_deletion.exit_type(self.conn, 'partner'), 'bad_exit')
        account_deletion.request_deletion(self.conn, 'owner')
        self.run_jobs(sessions.now() + 31 * DAY)
        self.assertEqual([r['exit_type'] for r in self.retained()], ['bad_exit'])

    def test_email_is_kept_when_there_is_no_phone(self):
        self.conn.execute('UPDATE Account SET phone = NULL WHERE user_id = ?', ('owner',)); self.conn.commit()
        account_deletion.request_deletion(self.conn, 'owner')
        self.run_jobs(sessions.now() + 31 * DAY)
        self.assertEqual([r['contact_kind'] for r in self.retained()], ['email'])
        self.assertTrue(account_deletion.find_deleted_contact(self.conn, 'OWNER@test.example'))

    def test_retention_deletes_the_record_after_the_setting(self):
        start = sessions.now()
        with mock.patch.dict(os.environ, {'DHASHU_DELETED_RETENTION_DAYS': '30'}):
            account_deletion.request_deletion(self.conn, 'owner')
            self.run_jobs(start + 31 * DAY)
        self.assertEqual(len(self.retained()), 1)
        with mock.patch('auth_sessions.now', return_value=start + 31 * DAY + 29 * DAY):
            account_deletion.apply_retention(self.conn)
        self.assertEqual(len(self.retained()), 1)                          # not due yet
        with mock.patch('auth_sessions.now', return_value=start + 31 * DAY + 31 * DAY):
            account_deletion.apply_retention(self.conn)
        self.assertEqual(self.retained(), [])

    def test_deleted_retention_setting_defaults_and_bounds(self):
        for raw, expected in (('365', 365), ('0', 1), ('99999', 3650), ('soon', 730)):
            with mock.patch.dict(os.environ, {'DHASHU_DELETED_RETENTION_DAYS': raw}):
                self.assertEqual(account_deletion.deleted_retention_days(), expected, raw)
        with mock.patch.dict(os.environ, {}):
            os.environ.pop('DHASHU_DELETED_RETENTION_DAYS', None)
            self.assertEqual(account_deletion.deleted_retention_days(), 730)

    def test_members_have_no_route_to_retained_contacts(self):
        import app as app_module
        rules = [r.rule for r in app_module.app.url_map.iter_rules()]
        self.assertEqual([r for r in rules if 'deleted-contact' in r or 'retention' in r], [])

    def test_grace_setting(self):
        with mock.patch.dict(os.environ, {'DHASHU_DELETE_GRACE_DAYS': '7'}):
            state = account_deletion.request_deletion(self.conn, 'owner')
        self.assertAlmostEqual(state['due_at'] - state['requested_at'], 7 * DAY, delta=1)

    def test_owner_only_and_signed_in(self):
        self.request({'password': PASSWORD})
        self.sign_in_again()
        self.assertFalse(self.f.request('/account/deletion', uid='partner').json['data']['scheduled'])
        self.assertIn(self.f.client.post('/api/v1/account/deletion', json={'password': PASSWORD}).status_code, (401, 403))


class WebAndAdminTests(unittest.TestCase):
    def test_public_explanation_page(self):
        import app as app_module
        r = app_module.app.test_client().get('/delete-account')
        self.assertEqual(r.status_code, 200)
        text = r.get_data(as_text=True)
        for words in ('Settings', 'Delete account', 'Cancel deletion', '30 days', 'Payment records'):
            self.assertIn(words, text)


if __name__ == '__main__':
    unittest.main()
