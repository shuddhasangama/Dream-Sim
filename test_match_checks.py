import json
import os
import sqlite3
import unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
import db
import bgv_policy
import match_checks as checks
import stats_edit
from generate_users import from_user_row
from api_contract import ApiError

class MatchCheckTests(unittest.TestCase):
 def setUp(self):
  self.env=patch.dict(os.environ,{'SIGNZY_ENV':'preproduction'});self.env.start();self.addCleanup(self.env.stop)
  self.conn=sqlite3.connect(':memory:');self.conn.row_factory=sqlite3.Row;db.init_db(self.conn);self.addCleanup(self.conn.close)
  for uid in ('a','b'):self.conn.execute('INSERT INTO "User" (id,journey_state,bgv_status,stats_json) VALUES (?,?,?,?)',(uid,'dating','verified',json.dumps({'share_verification_summary':'Yes','employment_category':'Salaried'})))
  self.conn.commit();bgv_policy.seed(self.conn);self.case=bgv_policy.assign(self.conn,'b','IN','BLR','synthetic test')
  self.now=datetime(2026,11,3,12,tzinfo=timezone.utc)
 def user(self,uid='b'):return from_user_row(db.fetch_one(self.conn,'User',id=uid))
 def evidence(self,days=1,employment='verified',env='preproduction'):
  for op,key,summary in [('individual_result','criminal_court',{'match_type':'exact','processing_complete':True,'candidate_count':0}),('fir_result','fir',{'match_type':'exact','processing_complete':True,'candidate_count':0}),('current_employer','current_employer',{'employment_record':{'current_employment_confirmed':employment=='verified'},'private':'SHOULD_NOT_APPEAR'})]:
   check=db.fetch_one(self.conn,'BgvCaseCheck',case_id=self.case,check_definition_id=key)
   stamp=(self.now-timedelta(days=days)).isoformat()
   self.conn.execute('INSERT INTO "BgvRequest" (id,user_id,operation,environment,state,protected_input,protected_result,summary_json,created_at,updated_at,case_check_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)',(op,'b',op,env,employment if op=='current_employer' else 'verified','PRIVATE_INPUT','PRIVATE_BODY',json.dumps(summary),stamp,stamp,check['id']))
  self.conn.commit()
 def owner(self,**prefs):return {'preferences':{'work_verification':{**checks.DEFAULT,**prefs}}}
 def test_redacted_consented_summary_dates_and_no_provider_io(self):
  self.evidence()
  with patch('bgv_app.Client.execute') as vendor:
   user=checks.attach(self.conn,[self.user()],self.now)[0];public=checks.public(user);vendor.assert_not_called()
  self.assertTrue(public['shared']);self.assertTrue(public['sandbox']);self.assertEqual(len(public['checks']),3)
  self.assertEqual(public['checks'][0]['checked_on'],'2026-11-02')
  text=json.dumps(public)
  for private in ('PRIVATE_INPUT','PRIVATE_BODY','SHOULD_NOT_APPEAR','case_check_id','checked_at','parent_request_id'):self.assertNotIn(private,text)
  self.assertTrue(checks.fits(self.owner(verified_only=True),user,self.now))
 def test_opt_in_and_withdrawal_never_fall_back_to_legacy_verified(self):
  self.evidence();user=self.user();user['stats'].pop('share_verification_summary')
  hidden=checks.attach(self.conn,[user],self.now)[0]
  self.assertEqual(checks.public(hidden),{'shared':False,'sandbox':False,'checks':[]})
  self.assertFalse(checks.fits(self.owner(verified_only=True),hidden,self.now))
  self.assertTrue(stats_edit.editable('share_verification_summary',{'keenness':True})['editable'])
  self.assertFalse(stats_edit.editable('employment_category',{'keenness':True})['editable'])
 def test_history_is_not_current_employment_and_dates_do_not_upgrade_it(self):
  self.evidence(employment='history_available');user=checks.attach(self.conn,[self.user()],self.now)[0]
  self.assertEqual(user['_match_checks']['checks'][2]['status'],'history_found')
  self.assertFalse(checks.fits(self.owner(verified_only=True),user,self.now))
  self.assertTrue(checks.fits(self.owner(),user,self.now))
 def test_freshness_90_180_and_any_use_real_check_timestamps(self):
  self.evidence(days=100);user=checks.attach(self.conn,[self.user()],self.now)[0]
  self.assertFalse(checks.fits(self.owner(verified_only=True,max_age_days=90),user,self.now))
  self.assertTrue(checks.fits(self.owner(verified_only=True,max_age_days=180),user,self.now))
  self.assertTrue(checks.fits(self.owner(verified_only=True,max_age_days=0),user,self.now))
 def test_categories_unknowns_and_show_all(self):
  user=self.user();user['stats']['employment_category']='Freelancer'
  self.assertFalse(checks.fits(self.owner(categories=['Salaried']),user))
  self.assertTrue(checks.fits(self.owner(categories=['Freelancer']),user))
  user['stats'].pop('employment_category')
  self.assertTrue(checks.fits(self.owner(categories=['Salaried']),user))
  self.assertFalse(checks.fits(self.owner(categories=['Salaried'],include_undisclosed=False),user))
  owner=self.owner(verified_only=True);owner['preferences']['work_verification_ignored']=True
  self.assertTrue(checks.fits(owner,user))
 def test_other_environment_and_foreign_case_do_not_provide_proof(self):
  self.evidence(env='production');user=checks.attach(self.conn,[self.user()],self.now)[0]
  self.assertFalse(checks.fits(self.owner(verified_only=True),user,self.now))
  self.conn.execute('UPDATE "BgvRequest" SET environment=?,user_id=?',('preproduction','a'));self.conn.commit()
  wrong=checks.attach(self.conn,[self.user('a')],self.now)[0]
  self.assertFalse(checks.fits(self.owner(verified_only=True),wrong,self.now))
 def test_new_search_hides_previous_completed_result(self):
  self.evidence();stamp=self.now.isoformat();cid=db.fetch_one(self.conn,'BgvCaseCheck',case_id=self.case,check_definition_id='criminal_court')['id']
  self.conn.execute('INSERT INTO "BgvRequest" (id,user_id,operation,environment,state,protected_input,created_at,updated_at,case_check_id) VALUES (?,?,?,?,?,?,?,?,?)',('new-search','b','individual_search','preproduction','queued','PRIVATE',stamp,stamp,cid));self.conn.commit()
  user=checks.attach(self.conn,[self.user()],self.now)[0]
  self.assertEqual(user['_match_checks']['checks'][0]['status'],'pending')
  self.assertFalse(checks.fits(self.owner(verified_only=True),user,self.now))
 def test_validation_and_future_date_fail_closed(self):
  for body in ({**checks.DEFAULT,'categories':['Invented']},{**checks.DEFAULT,'max_age_days':90},{**checks.DEFAULT,'max_age_days':True},{**checks.DEFAULT,'verified_only':'yes'}):
   with self.assertRaises(ApiError):checks.validate(body)
  self.evidence(days=-1);user=checks.attach(self.conn,[self.user()],self.now)[0]
  self.assertFalse(checks.fits(self.owner(verified_only=True),user,self.now))

 def test_bound_operator_review_can_override_auto_result_but_old_reviews_cannot(self):
  self.evidence();casecheck=db.fetch_one(self.conn,'BgvCaseCheck',case_id=self.case,check_definition_id='criminal_court')['id']
  stamp=(self.now-timedelta(hours=1)).isoformat()
  self.conn.execute('INSERT INTO "BgvAttempt" (id,request_id,protected_evidence,created_at) VALUES (?,?,?,?)',('attempt-now','individual_result','PRIVATE',stamp))
  self.conn.execute('INSERT INTO "BgvReview" (id,case_check_id,source_id,decision,protected_note,created_at) VALUES (?,?,?,?,?,?)',('review',casecheck,'attempt-now','not_satisfied','PRIVATE',stamp));self.conn.commit()
  user=checks.attach(self.conn,[self.user()],self.now)[0]
  self.assertEqual(user['_match_checks']['checks'][0]['status'],'review_required')
  self.assertFalse(checks.fits(self.owner(verified_only=True),user,self.now))
  self.conn.execute('UPDATE "BgvReview" SET source_id=?',('old-attempt',));self.conn.commit()
  user=checks.attach(self.conn,[self.user()],self.now)[0]
  self.assertEqual(user['_match_checks']['checks'][0]['status'],'verified')
