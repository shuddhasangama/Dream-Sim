import json
from unittest.mock import patch
import db
import week_service
from clock import SimulationClock
from test_segment_efg_routes import RouteTestCase

class SignupMatchingTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        for uid,gender in [('a','male'),('b','female'),('c','male')]:
            self.make_user(uid)
            db.insert_row(self.conn,'User',{**db.fetch_one(self.conn,'User',id=uid),'stats_json':json.dumps({'city':'Bengaluru','gender':gender})})
            db.insert_row(self.conn,'Account',dict(id=uid,user_id=uid,created_at=0,verified_phone=1,auth_enabled=1))
        p=patch('async_rehearsal.enabled',return_value=False);p.start();self.addCleanup(p.stop)
        p=patch('fixed_test_pairs.configured',return_value={});p.start();self.addCleanup(p.stop)
    def test_reciprocal_offer_reserves_both_partners(self):
        clock=SimulationClock.at(1,'Mon',12)
        rows=week_service.prepare(self.conn,'a',clock)
        self.assertEqual(len(rows),1)
        partner=week_service.prepare(self.conn,'b',clock)
        self.assertEqual(partner[0]['candidate_id'],'a')
        third=week_service.prepare(self.conn,'c',clock)
        self.assertFalse(any(r['slot']==1 for r in third))
    def test_late_signup_preview_does_not_create_dates(self):
        self.assertEqual(week_service.prepare(self.conn,'a',SimulationClock.at(1,'Wed',10)),[])
        self.assertEqual(db.fetch_all(self.conn,'Match'),[])
    def test_empty_batch_rechecks_when_compatible_member_arrives(self):
        self.conn.execute('UPDATE User SET bgv_status=? WHERE id=?',('declared','b'));self.conn.commit()
        clock=SimulationClock.at(1,'Tue',14)
        self.assertEqual(week_service.prepare(self.conn,'a',clock),[])
        self.conn.execute('UPDATE User SET bgv_status=? WHERE id=?',('verified','b'));self.conn.commit()
        rows=week_service.prepare(self.conn,'a',clock)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['slot'],2)
        self.assertEqual(week_service.prepare(self.conn,'a',clock),rows)
