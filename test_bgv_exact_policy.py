import json
import uuid
import unittest
from unittest.mock import patch
import db
import bgv_app
import bgv_bundle
import bgv_result_policy as policy
import test_bgv_phase1 as fixtures
import test_bgv_bundle as bundles
from api_contract import ApiError

class ExactPolicyTests(unittest.TestCase):
    setUp=fixtures.Phase1Tests.setUp
    tearDown=fixtures.Phase1Tests.tearDown
    body=fixtures.Phase1Tests.body
    work=fixtures.Phase1Tests.work
    def chain(self,op='individual_search',result=None):
        request=self.body(op);bgv_app.submit(self.conn,'u1',request)
        sent=self.work({'caseId':'synthetic_case_123'} if op=='individual_search' else {'result':{'status':1,'verifyId':'synthetic_fir_123'}})
        self.assertEqual(sent['matchType'],'exact')
        child=str(uuid.uuid4());bgv_app.fetch_result(self.conn,'u1',request['request_id'],child)
        self.work(result)
        return request,db.fetch_one(self.conn,'BgvRequest',id=child)
    def test_completed_exact_zero_verifies_only_that_check(self):
        for op in ('individual_search','fir_search'):
            _,row=self.chain(op,{'status':1,'message':'Processing done','total':0,'cases':[],'numResults':0})
            self.assertEqual(row['state'],'verified')
            self.assertIn('completed exact',json.loads(row['summary_json'])['message'])
        self.assertEqual(db.fetch_one(self.conn,'User',id='u1')['bgv_status'],'declared')
        with patch('bgv_app.Client.execute') as provider:
            bgv_app.reproject_saved(self.conn,'u1');provider.assert_not_called()
        self.assertTrue(all(r['state']=='verified' for r in db.fetch_all(self.conn,'BgvRequest') if r['operation'] in bgv_app.RESULTS.values()))
    def test_exact_cases_require_review_not_automatic_adverse_decision(self):
        _,row=self.chain('fir_search',{'result':{'status':1,'message':'Processing done','cases':[{}],'total':0,'numResults':1}})
        self.assertEqual(row['state'],'needs_review');self.assertIn('Exact search returned 1',json.loads(row['summary_json'])['message'])
    def test_pending_empty_and_conflicting_zero_do_not_verify(self):
        _,row=self.chain(result={'status':0,'message':'Process pending.','cases':[],'total':0})
        self.assertEqual(row['state'],'pending')
        _,row=self.chain('fir_search',{'result':{'status':1,'message':'Processing done','cases':[],'numResults':0,'total':15}})
        self.assertEqual(row['state'],'unavailable')
    def test_possible_results_are_not_relabelled_as_exact(self):
        parent,row=self.chain(result={'status':1,'cases':[],'total':0})
        protection=bgv_app.Protection();source=db.fetch_one(self.conn,'BgvRequest',id=parent['request_id']);data=protection.open(source['protected_input']);data['inputs']['matchType']='possible'
        self.conn.execute('UPDATE "BgvRequest" SET protected_input=? WHERE id=?',(protection.seal(data),source['id']));self.conn.commit()
        bgv_app.reproject_saved(self.conn,'u1')
        self.assertEqual(db.fetch_one(self.conn,'BgvRequest',id=row['id'])['state'],'not_confirmed')
    def test_app_rejects_possible_for_both_searches(self):
        for op in ('individual_search','fir_search'):
            body=self.body(op);body['inputs']['matchType']='possible'
            with self.assertRaises(ApiError):bgv_app.submit(self.conn,'u1',body)
    def test_employment_history_is_not_current_employment_or_unemployment(self):
        state,public=policy.employment({'employmentSummary':{'recent_employer_data':{'establishment_name':'Synthetic Ltd','date_of_joining':'2021-05-20','date_of_exit':'2022-05-23','member_id':'PRIVATE'}}},{'result_code':200,'is_employed':False},'needs_review')
        self.assertEqual(state,'history_available');self.assertIn('1 year, 3 days',public['message'])
        self.assertNotIn('PRIVATE',json.dumps(public));self.assertFalse(public['employment_record']['current_employment_confirmed'])
        self.assertEqual(public['employment_record']['duration_days'],368)
    def test_worker_retains_employment_evidence_and_shows_history(self):
        body={'request_id':str(uuid.uuid4()),'operation':'current_employer','inputs':{'panNumber':'AAAPA0000A','mobile':'9000000000'},'declared':{'employer':'New Company'},'consent':True,'consent_version':bgv_app.VERSION}
        bgv_app.submit(self.conn,'u1',body)
        self.work({'resultCode':200,'employmentSummary':{'is_employed':False,'date_of_exit_marked':True,'recent_employer_data':{'establishment_name':'Synthetic Ltd','date_of_joining':'2021-05-20','date_of_exit':'2022-05-23'}}})
        row=db.fetch_one(self.conn,'BgvRequest',id=body['request_id']);self.assertEqual(row['state'],'history_available')
        self.assertIn('Last recorded employer',json.loads(row['summary_json'])['message'])
        self.assertEqual(bgv_app.reproject_saved(self.conn,'u1'),0)
        self.assertEqual(len(db.fetch_all(self.conn,'BgvAttempt')),1)

class ExactMigrationTests(unittest.TestCase):
    setUp=bundles.BundleTests.setUp
    session=bundles.BundleTests.session
    def test_old_possible_search_is_preserved_and_exact_scheduled_once(self):
        self.session();old=str(uuid.uuid4());stamp=bgv_app.stamp()
        snapshot={'inputs':{'name':'SYNTHETIC PERSON','address':'SYNTHETIC ADDRESS','caseCategory':'criminal','matchType':'possible'},'declared':{},'bundle_session_id':self.sid}
        protected=self.protection.seal(snapshot)
        self.conn.execute('INSERT INTO "BgvRequest" (id,user_id,operation,environment,state,protected_input,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)',(old,'u1','individual_search','preproduction','result_available',protected,stamp,stamp));self.conn.commit()
        bgv_bundle.schedule(self.conn);bgv_bundle.schedule(self.conn)
        rows=db.fetch_all(self.conn,'BgvRequest',operation='individual_search');self.assertEqual(len(rows),2)
        self.assertEqual(db.fetch_one(self.conn,'BgvRequest',id=old)['protected_input'],protected)
        self.assertFalse(db.fetch_all(self.conn,'BgvRequest',parent_request_id=old))
        new=next(r for r in rows if r['id']!=old);self.assertEqual(self.protection.open(new['protected_input'])['inputs']['matchType'],'exact')
