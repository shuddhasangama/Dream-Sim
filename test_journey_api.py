"""Phase 4 block 1: read projections, real bearer sessions, no provider calls."""
import json
from unittest import mock

import auth_sessions
import db
import disclosure
from test_segment_efg_routes import RouteTestCase, app_module


class JourneyApiTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        for index, uid in enumerate(('owner', 'partner', 'stranger')):
            self.make_user(uid)
            self.conn.execute('UPDATE User SET preferences_json = ? WHERE id = ?',
                              (json.dumps({'fixed': {'dealbreakers': []}, 'adjustable': {}}), uid))
            self.conn.commit()
            db.insert_row(self.conn, 'Account', {
                'id': 'account-' + uid, 'user_id': uid,
                'email': uid + '@private.test', 'phone': '+91999999999' + str(index),
                'auth_enabled': 1, 'verification_required': 1,
                'verified_phone': 1, 'created_at': 'test'})
        self.mode = mock.patch.dict(app_module.app.config, {'AUTH_ENABLED': True})
        self.mode.start()
        self.addCleanup(self.mode.stop)
        self.token = auth_sessions.issue(self.conn, 'owner')
        self.headers = {'Authorization': 'Bearer ' + self.token['access_token']}

    def get(self, path='/journey/status', **kwargs):
        return self.client.get('/api/v1' + path, headers=self.headers, **kwargs)

    def test_dashboard_and_status_are_same_own_read_model(self):
        response = self.get()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers['Cache-Control'], 'no-store')
        state = response.json['data']
        self.assertEqual(state, self.get('/dashboard').json['data'])
        self.assertEqual(state, self.get('/dashboard?user_id=stranger').json['data'])
        self.assertEqual(state['user']['user_id'], 'owner')
        self.assertEqual(state['clock'], {'mode': 'simulation', 'week': 1, 'day': 'Mon', 'hour': 12})
        self.assertEqual(state['contact_verification'], {
            'required': True, 'satisfied': True, 'verified_email': False, 'verified_phone': True})
        self.assertIsNone(state['current_lock_in'])
        self.assertIsNone(state['current_date_plan'])
        self.assertIsNone(state['current_couple'])

    def test_reads_never_generate_matches_resolve_outcomes_or_change_clock(self):
        self.make_lockin('owner', 'partner')
        self.make_plan('lock-1', status='confirmed')
        self.set_clock(day='Sun', hour=23)
        before = list(self.conn.iterdump())
        clock_before = app_module.SIM_STATE_PATH.read_bytes()
        with (mock.patch.object(app_module, '_get_or_generate_matches', side_effect=AssertionError('Generated')),
              mock.patch.object(app_module, '_auto_resolve_stale_outcome', side_effect=AssertionError('Resolved'))):
            for path in ('/dashboard', '/journey/status', '/guidance'):
                for _ in range(2):
                    self.assertEqual(self.get(path).status_code, 200)
        self.assertEqual(list(self.conn.iterdump()), before)
        self.assertEqual(app_module.SIM_STATE_PATH.read_bytes(), clock_before)

    def test_pair_rows_are_allowlisted_and_foreign_pairs_do_not_leak(self):
        self.make_lockin('owner', 'partner')
        self.make_plan('lock-1')
        self.make_lockin('stranger', 'partner', lockin_id='private-foreign-pair')
        self.make_plan('private-foreign-pair', plan_id='private-foreign-plan')
        state = self.get().json['data']
        self.assertEqual(set(state['current_lock_in']), {'id', 'status', 'week', 'dates_completed'})
        self.assertEqual(set(state['current_date_plan']), {'id', 'status', 'datetime'})
        body = json.dumps(state)
        for private in ('private-foreign', '@private.test', '+919999999999',
                        'password_hash', 'selections_a', 'selections_b', 'user_a', 'user_b'):
            self.assertNotIn(private, body)
        reach = next(s for s in state['surfaces'] if s['key'] == 'reach')
        self.assertFalse(reach['eligible'])
        self.assertIsNone(reach['request'])
        self.assertTrue(reach['blocked_reason'])
        self.assertEqual(self.get('/reach').status_code, 403)

    def test_unimplemented_destinations_never_advertise_a_callable_url(self):
        state = self.get().json['data']
        for item in state['surfaces']:
            if not item['api_available'] or not item['eligible']:
                self.assertIsNone(item['request'])
            else:
                self.assertEqual(self.client.open(item['request']['path'], method=item['request']['method'],
                                                headers=self.headers).status_code, 200)
        self.assertEqual(self.get('/guidance').json['data'], state['next_action'])

    def test_ineligible_user_can_read_status_but_not_guidance(self):
        self.conn.execute('UPDATE User SET bgv_status = ? WHERE id = ?', ('pending', 'owner'))
        self.conn.commit()
        state = self.get().json['data']
        self.assertEqual(state['milestones'], ['registered'])
        self.assertFalse(state['stage_indicator']['show'])
        self.assertEqual(self.get('/guidance').status_code, 403)
        week = next(s for s in state['surfaces'] if s['key'] == 'week')
        self.assertFalse(week['eligible'])
        self.assertTrue(week['blocked_reason'])

    def test_every_journey_state_is_preserved_including_non_display_stages(self):
        for stage in ('onboarding', 'dating', 'relationship', 'engaged', 'married',
                      'exiting', 'cooloff', 're-entry'):
            with self.subTest(stage=stage):
                self.conn.execute('UPDATE User SET journey_state = ? WHERE id = ?', (stage, 'owner'))
                self.conn.commit()
                state = self.get().json['data']
                self.assertEqual(state['user']['journey_state'], stage)
                if stage in disclosure.RELATIONSHIP_STATES:
                    self.assertEqual(state['stage_indicator']['current'], stage)

    def test_couple_summary_excludes_other_party_and_consent_details(self):
        self.conn.execute('UPDATE User SET journey_state = ? WHERE id = ?', ('relationship', 'owner'))
        self.conn.commit()
        db.insert_row(self.conn, 'Couple', {'id': 'couple-1', 'partner_a_id': 'owner',
            'partner_b_id': 'partner', 'stage': 'relationship', 'entered_via': 'progression',
            'start_date': '2026-01-01', 'consent_version': 'private-consent'})
        result = self.get().json['data']['current_couple']
        self.assertEqual(result, {'id': 'couple-1', 'stage': 'relationship', 'stage_week_index': 0})

    def test_anonymous_invalid_and_revoked_bearer_cannot_read_status(self):
        for path in ('/dashboard', '/journey/status', '/guidance'):
            for headers in ({}, {'Authorization': 'Bearer invalid'}):
                response = self.client.get('/api/v1' + path, headers=headers)
                self.assertEqual(response.status_code, 401)
                self.assertNotIn('Location', response.headers)
        self.client.post('/api/v1/auth/logout', headers=self.headers)
        self.assertEqual(self.get().status_code, 401)

    def test_refresh_rotates_access_for_new_reads(self):
        response = self.client.post('/api/v1/auth/refresh', json={'refresh_token': self.token['refresh_token']})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.get().status_code, 401)
        self.headers = {'Authorization': 'Bearer ' + response.json['data']['access_token']}
        self.assertEqual(self.get().status_code, 200)

    def test_foreign_projection_is_rejected(self):
        self.make_lockin('stranger', 'partner')
        with mock.patch.object(app_module, '_my_active_lockin', return_value=db.fetch_one(self.conn, 'LockIn', id='lock-1')):
            response = self.get()
        self.assertEqual(response.status_code, 500)
        self.assertNotIn('stranger', response.get_data(as_text=True))

    def test_wrong_method_returns_existing_error_contract(self):
        response = self.client.post('/api/v1/journey/status', json={}, headers=self.headers)
        self.assertEqual(response.status_code, 405)
        self.assertEqual(response.json['error']['code'], 'method_not_allowed')
        self.assertIsNone(response.json['data'])
