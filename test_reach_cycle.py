"""REACH freezes for the displayed batch before any mutual pairing exists."""
import json
from unittest.mock import patch
import db
import reach_access
from clock import SimulationClock
from test_segment_efg_routes import RouteTestCase,app_module

class ReachCycleTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.make_user('owner')
        for i in range(1,4): self.make_user('candidate'+str(i))
        self.user={'user_id':'owner','journey_state':'dating'}
    def batch(self,count=3):
        for i in range(1,count+1):
            reveal=SimulationClock.at(1,['Mon','Tue','Wed'][i-1],12)
            closes=SimulationClock.at(1,['Tue','Wed','Wed'][i-1],12 if i<3 else 18)
            db.insert_row(self.conn,'Match',{'id':'m'+str(i),'user_id':'owner','candidate_id':'candidate'+str(i),
                'week':1,'slot':i,'revealed_at':str(reveal),'window_closes_at':str(closes),'action':'none'})
        self.conn.commit()
    def locked(self,day,hour=12):
        return reach_access.state(self.conn,self.user,SimulationClock.at(1,day,hour))['locked']
    def test_locks_at_first_reveal_without_mutual_match(self):
        self.batch()
        self.assertFalse(self.locked('Mon',11)); self.assertTrue(self.locked('Mon'))
        self.assertTrue(self.locked('Tue')); self.assertTrue(self.locked('Wed'))
    def test_empty_batch_remains_available(self):
        self.assertFalse(self.locked('Wed'))
    def test_does_not_unlock_between_daily_passes(self):
        self.batch()
        self.conn.execute('UPDATE "Match" SET action=? WHERE id=?',('pass','m1')); self.conn.commit()
        self.assertTrue(self.locked('Mon',13))
        self.conn.execute('UPDATE "Match" SET action=? WHERE id=?',('pass','m2')); self.conn.commit()
        self.assertTrue(self.locked('Tue',13))
        self.conn.execute('UPDATE "Match" SET action=? WHERE id=?',('pass','m3')); self.conn.commit()
        self.assertFalse(self.locked('Wed',13))
    def test_received_passes_resolve_three_daily_candidates(self):
        self.batch()
        for i in range(1,4):
            db.insert_row(self.conn,'Match',{'id':'reverse'+str(i),'user_id':'candidate'+str(i),'candidate_id':'owner',
                'week':1,'slot':1,'revealed_at':'W1 Mon 12:00','window_closes_at':'W1 Wed 18:00','action':'pass'})
        self.conn.commit()
        self.assertTrue(self.locked('Tue',13)); self.assertFalse(self.locked('Wed',13))
    def test_pair_freezes_planning_date_and_debrief_across_week(self):
        self.make_lockin('owner','candidate1')
        self.assertTrue(self.locked('Thu')); self.assertTrue(self.locked('Sun'))
        self.assertTrue(reach_access.state(self.conn,self.user,SimulationClock.at(2,'Mon',10))['locked'])
        self.conn.execute('UPDATE "LockIn" SET status=?',('released',)); self.conn.commit()
        self.assertFalse(self.locked('Sun'))
    def test_release_ignores_historical_mutual_interest(self):
        self.batch(1); self.make_lockin('owner','candidate1')
        self.conn.execute('UPDATE "Match" SET action=?',('interest',))
        self.conn.execute('UPDATE "LockIn" SET status=?',('released',)); self.conn.commit()
        self.assertFalse(self.locked('Mon',13))
    def test_rehearsal_does_not_expire_unanswered_match(self):
        self.batch(1)
        with patch.dict('os.environ',{'DHASHU_ASYNC_TEST':'true','DHASHU_SIMULATED_CLOCK':'true'}):
            self.assertTrue(self.locked('Fri'))
    def test_backend_blocks_read_and_write_and_hides_nav_surface(self):
        self.batch(); self.set_clock(day='Mon',hour=13); self.login('owner')
        self.assertEqual(self.client.get('/api/v1/reach').status_code,403)
        self.assertEqual(self.client.post('/api/v1/reach/set-range',json={'lever':'age','min':25,'max':40}).status_code,403)
        result=self.client.get('/api/v1/journey/status')
        self.assertEqual(result.status_code,200)
        surface=next(s for s in result.json['data']['surfaces'] if s['key']=='reach')
        self.assertFalse(surface['eligible']); self.assertIsNone(surface['request'])
    def test_review_lock_does_not_disable_match_decisions(self):
        self.batch(); self.set_clock(day='Mon',hour=13)
        with app_module.app.test_request_context('/'):
            user=app_module.load_user('owner')
            self.assertTrue(app_module.reach_locked(user))
            row=db.fetch_one(self.conn,'Match',id='m1')
            self.assertIn('pass',app_module._api_match_view(user,row)['allowed_actions'])
