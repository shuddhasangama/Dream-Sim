"""Pair ownership, overlap gates, repeat cycles and immutable booking inputs."""
import json
import os
from unittest import mock

import booking_coordination
import auth_sessions
import db
import test_planning_api
from test_segment_efg_routes import RouteTestCase, app_module


class BookingTests(RouteTestCase):
    request = test_planning_api.PlanningApiTests.request
    align = test_planning_api.PlanningApiTests.align

    def setUp(self):
        super().setUp()
        config = mock.patch.dict(app_module.app.config, {'AUTH_ENABLED': True})
        config.start()
        self.addCleanup(config.stop)
        self.headers = {}
        for who in ('owner', 'partner', 'stranger'):
            self.make_user(who)
            db.insert_row(self.conn, 'Account', {'id': who, 'user_id': who, 'email': who+'@test.example',
                'auth_enabled': 1, 'verification_required': 1, 'verified_email': 1, 'created_at': 'test'})
            token = auth_sessions.issue(self.conn, who)
            self.headers[who] = {'Authorization': 'Bearer '+token['access_token']}
        self.set_clock()
        self.make_lockin('owner', 'partner')
        self.base = '/lock-ins/lock-1'
        self.slot = {'day': 'Sat', 'meal_slot': 'dinner'}
        flag = mock.patch.dict(os.environ, {'DHASHU_BOOKING_COORDINATION_ENABLED': '1'})
        flag.start()
        self.addCleanup(flag.stop)

    def view(self, uid='owner'):
        return self.request(self.base+'/calendar', uid=uid).json['data']['booking']

    def choose(self, uid='owner', places=None, **extra):
        state = self.view(uid)
        body = {'scope': state.get('scope'), 'revision': state.get('revision'),
                'neighbourhoods': places or ['indiranagar'], **extra}
        return self.request(self.base+'/neighbourhoods', uid=uid, method='PUT', body=body)

    def prepare(self):
        for who in ('owner', 'partner'):
            self.assertEqual(self.align(who).status_code, 200)
            self.assertEqual(self.choose(who).status_code, 200)
            self.assertEqual(self.request(self.base+'/availability', uid=who, method='PUT', body={'slots': [self.slot]}).status_code, 200)

    def confirm(self):
        return self.request(self.base+'/date-plan', method='POST', body=self.slot)

    def test_shared_choices_and_frozen_snapshot_are_private_and_stable(self):
        self.prepare()
        self.choose('owner', ['indiranagar', 'koramangala'])
        self.assertEqual(self.view('partner')['shared_neighbourhoods'], ['indiranagar'])
        self.assertEqual(self.view('partner')['mine'], ['indiranagar'])
        self.assertTrue(self.view()['ready'])
        result = self.confirm()
        self.assertEqual(result.status_code, 200, result.json)
        pid = result.json['data']['id']
        self.assertEqual(result.json['data']['venue'], 'Restaurant booking pending')
        snapshot = self.view()['snapshot']
        self.assertEqual(snapshot['dateplan_id'], pid)
        self.assertEqual(snapshot['radius_steps_km'], [1, 2, 3])
        self.assertEqual(snapshot['reservation_status'], 'not_requested')
        self.assertEqual(snapshot['neighbourhoods'][0]['id'], 'indiranagar')
        self.assertEqual(self.confirm().json['data']['id'], pid)
        self.assertEqual(len(db.fetch_all(self.conn, 'BookingSnapshot')), 1)
        self.assertEqual(self.choose().status_code, 409)
        self.conn.execute('UPDATE User SET stats_json=? WHERE id=?', (json.dumps({'city':'Delhi'}), 'owner'))
        self.conn.commit()
        self.assertEqual(self.view()['snapshot'], snapshot)

    def test_no_overlap_never_generates_plan(self):
        self.prepare()
        self.choose('partner', ['jayanagar'])
        self.assertEqual(self.view()['state'], 'no_neighbourhood_overlap')
        self.assertEqual(self.confirm().status_code, 409)
        self.assertEqual(db.fetch_all(self.conn, 'DatePlan'), [])
        self.assertEqual(db.fetch_all(self.conn, 'BookingSnapshot'), [])

    def test_missing_cuisine_and_budget_are_explicit(self):
        self.prepare()
        stats = db.load_json_field(db.fetch_one(self.conn, 'User', id='partner')['stats_json'], {})
        stats['cuisine'] = ['unshared']
        self.conn.execute('UPDATE User SET stats_json=? WHERE id=?', (json.dumps(stats), 'partner'))
        self.conn.commit()
        self.assertEqual(self.view()['state'], 'no_cuisine_overlap')
        self.assertEqual(self.confirm().status_code, 409)
        stats['cuisine'] = db.load_json_field(db.fetch_one(self.conn, 'User', id='owner')['stats_json'], {})['cuisine']
        stats['budget'] = ['unshared']
        self.conn.execute('UPDATE User SET stats_json=? WHERE id=?', (json.dumps(stats), 'partner'))
        self.conn.commit()
        self.assertEqual(self.view()['state'], 'no_budget_overlap')

    def test_ownership_validation_and_stale_writes(self):
        self.assertEqual(self.request(self.base+'/calendar', uid='stranger').status_code, 404)
        state = self.view()
        self.assertEqual(self.choose(places=['not-a-place']).status_code, 400)
        self.assertEqual(self.choose(places=['indiranagar', 'indiranagar']).status_code, 400)
        self.assertEqual(self.choose().status_code, 200)
        self.assertEqual(self.choose(places=['jayanagar'], revision=state['revision']).status_code, 409)
        self.assertEqual(self.choose(scope='different-cycle').status_code, 409)
        self.assertEqual(self.request(self.base+'/neighbourhoods', uid='stranger', method='PUT', body={'scope':state['scope'],'revision':0,'neighbourhoods':['indiranagar']}).status_code, 404)

    def test_next_cycle_requires_new_choices_and_rollback_is_atomic(self):
        self.prepare()
        original = __import__('planning_service').save
        def fail_plan(conn, table, row):
            if table == 'DatePlan':
                raise RuntimeError('write failed')
            return original(conn, table, row)
        with mock.patch('planning_service.save', side_effect=fail_plan):
            with self.assertRaises(RuntimeError):
                __import__('planning_service').confirm(self.conn, 'owner', 'lock-1', 'Sat', 'dinner', lambda *a: 'test')
        self.assertEqual(db.fetch_all(self.conn, 'BookingSnapshot'), [])
        self.assertEqual(self.confirm().status_code, 200)
        self.conn.execute("UPDATE DatePlan SET status='completed'")
        self.conn.commit()
        self.assertEqual(self.view()['mine'], [])
        self.assertEqual(self.view()['state'], 'your_preferences')

    def test_disabled_and_unsupported_city(self):
        with mock.patch.dict(os.environ, {'DHASHU_BOOKING_COORDINATION_ENABLED':'0'}):
            self.assertIsNone(self.view())
        self.conn.execute('UPDATE User SET stats_json=? WHERE id=?', (json.dumps({'city':'Unknown'}), 'owner'))
        self.conn.commit()
        self.assertEqual(self.view()['state'], 'unsupported_market')
        self.assertEqual(self.choose().status_code, 409)

    def test_read_is_readonly_and_identical_save_does_not_bump_revision(self):
        before = list(self.conn.iterdump())
        self.view()
        self.assertEqual(before, list(self.conn.iterdump()))
        self.choose()
        revision = self.view()['revision']
        self.choose()
        self.assertEqual(self.view()['revision'], revision)

    def test_web_calendar_uses_same_preferences_and_reset_cascades(self):
        self.login('owner')
        with mock.patch.dict(app_module.app.config, {'AUTH_ENABLED': False}), mock.patch.object(app_module, 'unlocked_or_redirect', return_value=None):
            page = self.client.get('/calendar')
        self.assertEqual(page.status_code, 200)
        self.assertIn(b'Save neighbourhoods', page.data)
        state = self.view()
        with mock.patch.dict(app_module.app.config, {'AUTH_ENABLED': False}):
            result = self.client.post('/calendar/neighbourhoods', data={
                'scope':state['scope'], 'revision':state['revision'], 'neighbourhood':['indiranagar']})
        self.assertEqual(result.status_code, 302)
        self.assertEqual(self.view()['mine'], ['indiranagar'])
        self.prepare()
        self.assertEqual(self.confirm().status_code, 200)
        self.conn.execute('DELETE FROM DatePlan')
        self.conn.execute('DELETE FROM Availability')
        self.conn.execute('DELETE FROM LockIn')
        self.conn.commit()
        self.assertEqual(db.fetch_all(self.conn, 'BookingSnapshot'), [])
        self.assertEqual(db.fetch_all(self.conn, 'BookingPreference'), [])
