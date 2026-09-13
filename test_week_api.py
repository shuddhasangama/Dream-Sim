"""Two-user API journey and retry/race checks; isolated SQLite, no OTP delivery."""
import concurrent.futures
import json
from unittest import mock

import auth_sessions
import db
import week_service
from api_contract import ApiError
from test_segment_efg_routes import RouteTestCase, app_module


class WeekApiTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.config = mock.patch.dict(app_module.app.config, {'AUTH_ENABLED': True})
        self.config.start()
        self.addCleanup(self.config.stop)
        self.headers = {}
        for uid in ('owner', 'partner', 'stranger'):
            self.make_user(uid)
            self.conn.execute('UPDATE User SET preferences_json = ? WHERE id = ?',
                              (json.dumps({'fixed': {'dealbreakers': []}, 'adjustable': {'distance_km': [0, 5000]}}), uid))
            self.conn.commit()
            db.insert_row(self.conn, 'Account', {'id': uid, 'user_id': uid, 'email': uid+'@test.example',
                'auth_enabled': 1, 'verification_required': 1, 'verified_email': 1, 'created_at': 'test'})
            token = auth_sessions.issue(self.conn, uid)
            self.headers[uid] = {'Authorization': 'Bearer '+token['access_token']}
        self.set_clock()

    def request(self, path, *, uid='owner', body=None, method='GET'):
        return self.client.open('/api/v1'+path, method=method, json=body, headers=self.headers[uid])

    def match(self, uid, other, slot=1, reveal='Mon', close='Tue'):
        mid = f'{uid}:1:{slot}'
        db.insert_row(self.conn, 'Match', {'id':mid, 'user_id':uid,'candidate_id':other,
            'week':1,'slot':slot,'revealed_at':str(app_module.clock_module.SimulationClock.at(1,reveal,12)),
            'window_closes_at':str(app_module.clock_module.SimulationClock.at(1,close,12))})
        return mid

    def action(self, uid, mid, action, **extra):
        return self.request('/matches/'+mid+'/actions',uid=uid,method='POST',body={'action':action,**extra})

    def test_get_is_read_only_and_prepare_is_explicit_idempotent_even_when_empty(self):
        before = list(self.conn.iterdump())
        result = self.request('/week')
        self.assertEqual(result.status_code,200)
        self.assertFalse(result.json['data']['prepared'])
        self.assertEqual(list(self.conn.iterdump()),before)
        first = self.request('/week/prepare',method='POST',body={})
        self.assertEqual(first.status_code,200,first.json)
        self.assertTrue(first.json['data']['prepared'])
        # All fixtures are female, so this is a genuinely empty batch.
        self.assertEqual(first.json['data']['matches'],[])
        before = list(self.conn.iterdump())
        second = self.request('/week/prepare',method='POST',body={})
        self.assertEqual(first.json,second.json)
        self.assertEqual(list(self.conn.iterdump()),before)

    def test_future_matches_hide_identity_and_are_not_directly_readable(self):
        mid = self.match('owner','partner',slot=2,reveal='Tue',close='Wed')
        data = self.request('/week').json['data']['matches'][0]
        self.assertIsNone(data['candidate'])
        self.assertFalse(data['their_interest'])
        self.assertEqual(data['allowed_actions'],[])
        self.assertEqual(self.request('/matches/'+mid).status_code,404)
        self.assertEqual(self.action('owner',mid,'interest').status_code,409)
        self.set_clock(day='Tue')
        data = self.request('/matches/'+mid).json['data']
        self.assertEqual(data['candidate']['display_name'],app_module.MASKED_NAME)
        self.assertNotIn('user_id',data['candidate'])
        self.assertNotIn('preferences',data['candidate'])

    def test_generated_batch_is_stable_and_excludes_post_dating_profiles(self):
        for uid in ('partner','stranger'):
            row=db.fetch_one(self.conn,'User',id=uid)
            stats=json.loads(row['stats_json'])
            stats['gender']='male'
            self.conn.execute('UPDATE User SET stats_json=? WHERE id=?',(json.dumps(stats),uid))
        self.conn.execute('UPDATE User SET journey_state=? WHERE id=?',('relationship','stranger'))
        self.conn.commit()
        response=self.request('/week/prepare',method='POST',body={})
        self.assertEqual(response.status_code,200,response.json)
        matches=db.fetch_all(self.conn,'Match',user_id='owner')
        self.assertEqual([m['candidate_id'] for m in matches],['partner'])
        self.conn.execute('UPDATE User SET journey_state=? WHERE id=?',('dating','stranger'))
        self.conn.commit()
        self.request('/week/prepare',method='POST',body={})
        self.assertEqual(db.fetch_all(self.conn,'Match',user_id='owner'),matches)

    def test_mutual_interest_clears_other_candidates_and_replays_once(self):
        a=self.match('owner','partner')
        b=self.match('partner','owner')
        self.match('owner','stranger',slot=2,reveal='Tue',close='Wed')
        self.match('partner','stranger',slot=2,reveal='Tue',close='Wed')
        self.assertEqual(self.action('owner',a,'interest').status_code,200)
        self.assertEqual(db.fetch_all(self.conn,'LockIn'),[])
        self.assertTrue(self.request('/matches/'+b,uid='partner').json['data']['their_interest'])
        self.assertEqual(self.action('partner',b,'interest').status_code,200)
        self.assertEqual(len(db.fetch_all(self.conn,'LockIn')),1)
        self.assertEqual(len(db.fetch_all(self.conn,'Match')),2)
        for uid,mid in [('owner',a),('partner',b)]:
            self.assertTrue(self.action(uid,mid,'interest').json['data']['replayed'])
            self.assertEqual(self.request('/reach',uid=uid).status_code,403)
            self.assertEqual(self.request('/week',uid=uid).json['data']['mode'],'locked_in')
            self.assertIsNotNone(self.request('/lock-ins/current',uid=uid).json['data']['lock_in'])
        self.assertEqual(len(db.fetch_all(self.conn,'LockIn')),1)

    def test_foreign_missing_invalid_and_changed_decisions_do_not_write(self):
        mid=self.match('owner','partner')
        before=list(self.conn.iterdump())
        self.assertEqual(self.action('stranger',mid,'interest').status_code,404)
        self.assertEqual(self.request('/matches/'+mid,uid='stranger').status_code,404)
        self.assertEqual(self.action('owner','missing','pass').status_code,404)
        for value in (None,[],{},True,'invalid'):
            self.assertEqual(self.action('owner',mid,value).status_code,400)
        self.assertEqual(self.action('owner',mid,'pass',user_id='partner').status_code,400)
        self.assertEqual(list(self.conn.iterdump()),before)
        self.assertEqual(self.action('owner',mid,'pass',pass_reason='not a fit').status_code,200)
        self.assertEqual(self.action('owner',mid,'interest').status_code,409)
        self.assertEqual(self.action('owner',mid,'pass',pass_reason='changed').status_code,409)

    def test_expired_and_unverified_contact_checks(self):
        mid=self.match('owner','partner')
        self.conn.execute('UPDATE Account SET verified_email=0 WHERE user_id=?',('owner',))
        self.conn.commit()
        self.assertEqual(self.action('owner',mid,'interest').status_code,403)
        self.assertEqual(self.action('owner',mid,'pass').status_code,200)
        other=self.match('partner','owner')
        self.set_clock(day='Wed')
        self.assertEqual(self.action('partner',other,'interest').status_code,409)
        self.assertEqual(self.request('/matches/'+other,uid='partner').json['data']['status'],'no_response')

    def test_prepare_requires_verified_dating_user_and_started_week(self):
        self.set_clock(hour=11)
        self.assertEqual(self.request('/week/prepare',method='POST',body={}).status_code,409)
        self.set_clock()
        self.conn.execute('UPDATE User SET bgv_status=? WHERE id=?',('pending','owner'))
        self.conn.commit()
        self.assertEqual(self.request('/week').status_code,403)
        self.assertEqual(self.request('/week/prepare',method='POST',body={}).status_code,403)
        self.assertEqual(db.fetch_all(self.conn,'MatchBatch'),[])

    def test_web_uses_same_service_and_json_reports_same_decision(self):
        mid=self.match('owner','partner')
        with mock.patch.dict(app_module.app.config,{'AUTH_ENABLED':False}):
            self.login('owner')
            self.assertEqual(self.client.post('/week/act',data={'match_id':mid,'action':'pass'}).status_code,302)
        self.assertEqual(self.request('/matches/'+mid).json['data']['action'],'pass')
        self.assertTrue(self.action('owner',mid,'pass').json['data']['replayed'])

    def test_mid_transition_failure_rolls_back_interest_and_lockin(self):
        a=self.match('owner','partner')
        b=self.match('partner','owner')
        self.action('owner',a,'interest')
        original=week_service.sql
        def fail(conn, statement, values=()):
            if statement.startswith('DELETE FROM "Match"'):
                raise RuntimeError('injected write failure')
            return original(conn,statement,values)
        with mock.patch.object(week_service,'sql',side_effect=fail):
            with self.assertRaises(RuntimeError):
                week_service.decide(self.conn,'partner',b,'interest',None,app_module.get_clock())
        self.assertEqual(db.fetch_one(self.conn,'Match',id=b)['action'],'none')
        self.assertEqual(db.fetch_all(self.conn,'LockIn'),[])

    def test_competing_mutual_interests_cannot_create_parallel_lockins(self):
        a=self.match('owner','partner')
        b=self.match('partner','owner')
        c=self.match('owner','stranger',slot=2)
        d=self.match('stranger','owner')
        self.action('partner',b,'interest')
        self.action('stranger',d,'interest')
        clock=app_module.get_clock()
        def run(mid):
            conn=db.get_connection(self.db_path)
            try:
                try:
                    return week_service.decide(conn,'owner',mid,'interest',None,clock)
                except ApiError as exc:
                    return exc.code
            finally:
                conn.close()
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as ex:
            results=list(ex.map(run,[a,c]))
        self.assertEqual(sum(isinstance(r,dict) for r in results),1)
        self.assertEqual(len(db.fetch_all(self.conn,'LockIn')),1)
