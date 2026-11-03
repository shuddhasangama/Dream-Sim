import json
from unittest.mock import patch
import auth_sessions
import db
import matching
import test_week_api
from test_segment_efg_routes import RouteTestCase,app_module

class MatchCheckRouteTests(RouteTestCase):
 request=test_week_api.WeekApiTests.request
 match=test_week_api.WeekApiTests.match
 def setUp(self):
  super().setUp();p=patch.dict(app_module.app.config,{'AUTH_ENABLED':True});p.start();self.addCleanup(p.stop)
  self.headers={}
  for uid in ('owner','partner','stranger'):
   self.make_user(uid)
   row=db.fetch_one(self.conn,'User',id=uid);stats=json.loads(row['stats_json']);stats.update(city='Bangalore',gender='male' if uid=='partner' else 'female',employment_category='Freelancer' if uid=='partner' else 'Salaried')
   row['stats_json']=json.dumps(stats);row['preferences_json']=json.dumps({'fixed':{'dealbreakers':[]},'adjustable':{'distance_km':[0,5000]}});db.insert_row(self.conn,'User',row)
   db.insert_row(self.conn,'Account',{'id':uid,'user_id':uid,'auth_enabled':1,'verified_email':1,'email':uid+'@test.example','created_at':'test'})
   self.headers[uid]={'Authorization':'Bearer '+auth_sessions.issue(self.conn,uid)['access_token']}
  self.set_clock(day='Mon',hour=11)
 def body(self,**changes):return {'categories':[],'include_undisclosed':True,'verified_only':False,'max_age_days':0,**changes}
 def test_preferences_persist_affect_matching_counts_and_generation(self):
  r=self.request('/reach/work-verification',method='POST',body=self.body(categories=['Salaried']))
  self.assertEqual(r.status_code,200,r.json)
  self.assertEqual(r.json['data']['counts']['fits_user_filters'],0)
  again=self.request('/reach').json['data'];self.assertEqual(again['work_verification_filter']['preferences']['categories'],['Salaried'])
  r=self.request('/reach/work-verification',method='POST',body=self.body(categories=['Freelancer']))
  self.assertEqual(r.json['data']['counts']['fits_user_filters'],1)
  self.set_clock(day='Mon',hour=12)
  r=self.request('/week/prepare',method='POST',body={});self.assertEqual(r.status_code,200,r.json)
  self.assertEqual([r['candidate_id'] for r in db.fetch_all(self.conn,'Match',user_id='owner')],['partner'])
 def test_filter_route_auth_validation_and_freeze_are_enforced(self):
  self.assertIn(self.client.post('/api/v1/reach/work-verification',json=self.body()).status_code,(401,403))
  for bad in (self.body(categories=['invented']),self.body(max_age_days=90),self.body(verified_only='yes'),{**self.body(),'user_id':'partner'}):
   self.assertEqual(self.request('/reach/work-verification',method='POST',body=bad).status_code,400)
  mid=self.match('owner','partner');self.set_clock(day='Mon',hour=12)
  before=db.fetch_one(self.conn,'User',id='owner')['preferences_json']
  self.assertEqual(self.request('/reach/work-verification',method='POST',body=self.body(verified_only=True)).status_code,403)
  self.assertEqual(db.fetch_one(self.conn,'User',id='owner')['preferences_json'],before)
 def test_match_view_respects_nonsharing_and_existing_like_pass(self):
  mid=self.match('owner','partner');self.set_clock(day='Mon',hour=12)
  first=self.request('/matches/'+mid);self.assertEqual(first.status_code,200,first.json)
  candidate=first.json['data']['candidate']
  self.assertEqual(candidate['employment_category'],'Freelancer');self.assertFalse(candidate['verification_summary']['shared'])
  self.assertIn('pass',first.json['data']['allowed_actions'])
  self.assertEqual(self.request('/matches/'+mid,uid='stranger').status_code,404)
  passed=self.request('/matches/'+mid+'/actions',method='POST',body={'action':'pass'})
  self.assertEqual(passed.status_code,200,passed.json)
  self.assertEqual(db.fetch_one(self.conn,'Match',id=mid)['action'],'pass')
 def test_employment_edit_freeze_and_privacy_withdrawal(self):
  self.make_lockin('owner','partner')
  before=db.fetch_one(self.conn,'User',id='owner')['stats_json']
  r=self.request('/profile/stats',method='PATCH',body={'fields':{'employment_category':'Self-employed'}})
  self.assertEqual(r.status_code,409,r.json);self.assertEqual(db.fetch_one(self.conn,'User',id='owner')['stats_json'],before)
  r=self.request('/profile/stats',method='PATCH',body={'fields':{'share_verification_summary':'No'}})
  self.assertEqual(r.status_code,200,r.json)
  self.assertEqual(json.loads(db.fetch_one(self.conn,'User',id='owner')['stats_json'])['share_verification_summary'],'No')
 def test_verified_filter_requires_real_shared_proof_not_legacy_verified(self):
  r=self.request('/reach/work-verification',method='POST',body=self.body(verified_only=True,max_age_days=90))
  self.assertEqual(r.status_code,200,r.json);self.assertEqual(r.json['data']['counts']['fits_user_filters'],0)
  self.set_clock(day='Mon',hour=12);self.request('/week/prepare',method='POST',body={})
  self.assertEqual(db.fetch_all(self.conn,'Match',user_id='owner'),[])
 def test_category_validation_and_show_all_preserve_filters(self):
  r=self.request('/profile/stats',method='PATCH',body={'fields':{'employment_category':'Invented'}});self.assertEqual(r.status_code,400)
  self.request('/reach/work-verification',method='POST',body=self.body(categories=['Salaried']))
  shown=self.request('/reach/show-all',method='POST',body={'ignore':True});self.assertEqual(shown.status_code,200,shown.json)
  saved=json.loads(db.fetch_one(self.conn,'User',id='owner')['preferences_json'])
  self.assertTrue(saved['work_verification_ignored']);self.assertEqual(saved['work_verification']['categories'],['Salaried'])
  restored=self.request('/reach/show-all',method='POST',body={'ignore':False})
  self.assertFalse(restored.json['data']['work_verification_filter']['ignored'])
