"""Phase 1 synthetic app/worker tests; no vendor calls or personal data."""
import io
import json
import os
import sqlite3
import unittest
import uuid
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from cryptography.fernet import Fernet
from flask import Flask,g
import db
import bgv_app
import bgv_app_api
import bgv_policy
import digilocker_signup
from api_contract import ApiError
from signzy.client import Client,Config
from signzy import smart_verification,fir_search,document_photo

class Phase1Tests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{'DHASHU_BGV_APP_ENABLED':'1','DHASHU_BGV_POLICY_ENABLED':'0',
            'SIGNZY_ENV':'preproduction','SIGNZY_TEST_API_KEY':'synthetic',
            'SIGNZY_RECEIPT_ENCRYPTION_KEY':Fernet.generate_key().decode()})
        self.env.start(); self.conn=sqlite3.connect(':memory:'); self.conn.row_factory=sqlite3.Row
        db.init_db(self.conn)
        self.conn.executemany('INSERT INTO "User" (id,journey_state) VALUES (?,?)',[('u1','onboarding'),('u2','onboarding')]); self.conn.commit()
    def tearDown(self): self.conn.close(); self.env.stop()
    def body(self,op='individual_search'):
        inputs={'name':'SYNTHETIC PERSON','address':'SYNTHETIC ADDRESS','matchType':'possible'}
        if op=='individual_search': inputs['caseCategory']='criminal'
        return {'request_id':str(uuid.uuid4()),'operation':op,'inputs':inputs,'declared':{},'consent':True,'consent_version':bgv_app.VERSION}
    def work(self,body,status=200,timeout=False):
        response=io.BytesIO(json.dumps(body).encode()); response.code=status
        with patch('urllib.request.build_opener') as opener:
            if timeout: opener.return_value.open.side_effect=TimeoutError()
            else: opener.return_value.open.return_value=response
            self.assertTrue(bgv_app.work_one(self.conn))
            self.assertEqual(opener.return_value.open.call_count,1)
            return json.loads(opener.return_value.open.call_args.args[0].data)
    def test_criminal_chain_ownership_idempotency_and_no_clearance(self):
        request=self.body(); bgv_app.submit(self.conn,'u1',request)
        inputs=self.work({'status':1,'caseId':'synthetic_case_123'})
        self.assertEqual(inputs['caseCategory'],'criminal'); self.assertEqual(inputs['matchType'],'possible')
        parent=request['request_id']; child=str(uuid.uuid4())
        self.assertTrue(bgv_app.view(self.conn,'u1')['results'][0]['can_fetch_result'])
        with self.assertRaises(ApiError): bgv_app.fetch_result(self.conn,'u2',parent,child)
        bgv_app.fetch_result(self.conn,'u1',parent,child)
        bgv_app.fetch_result(self.conn,'u1',parent,child)
        with self.assertRaises(ApiError): bgv_app.fetch_result(self.conn,'u1',parent,str(uuid.uuid4()))
        self.assertEqual(self.work({'status':1,'cases':[],'total':0}),{'caseId':'synthetic_case_123'})
        self.assertFalse(bgv_app.work_one(self.conn))
        result=next(r for r in bgv_app.view(self.conn,'u1')['results'] if r['operation']=='individual_result')
        self.assertEqual(result['state'],'needs_review')
        self.assertNotIn('synthetic_case',json.dumps(result))
        self.assertEqual(db.fetch_one(self.conn,'User',id='u1')['bgv_status'],'declared')
        self.assertEqual(len(db.fetch_all(self.conn,'BgvAttempt')),2)
    def test_fir_observed_envelope_pending_and_bounded_poll(self):
        request=self.body('fir_search'); bgv_app.submit(self.conn,'u1',request)
        self.work({'result':{'status':1,'verifyId':'synthetic_fir_123'}})
        child=str(uuid.uuid4()); bgv_app.fetch_result(self.conn,'u1',request['request_id'],child)
        self.assertEqual(self.work({},202),{'verifyId':'synthetic_fir_123'})
        with self.assertRaises(ApiError): bgv_app.check_again(self.conn,'u1',child)
        self.conn.execute('UPDATE "BgvRequest" SET updated_at=? WHERE id=?',((datetime.now(timezone.utc)-timedelta(seconds=61)).isoformat(),child)); self.conn.commit()
        bgv_app.check_again(self.conn,'u1',child)
        with self.assertRaises(ApiError): bgv_app.check_again(self.conn,'u1',child)
        self.work({'status':1,'message':'Processing done','cases':[],'numresults':0})
        self.assertEqual(db.fetch_one(self.conn,'BgvRequest',id=child)['state'],'needs_review')
        self.assertEqual(len(db.fetch_all(self.conn,'BgvAttempt',request_id=child)),2)
    def test_timeout_cannot_be_polled_or_replayed(self):
        request=self.body(); bgv_app.submit(self.conn,'u1',request)
        self.work({},timeout=True)
        self.assertEqual(db.fetch_one(self.conn,'BgvRequest',id=request['request_id'])['state'],'outcome_unknown')
        with self.assertRaises(ApiError): bgv_app.check_again(self.conn,'u1',request['request_id'])
        with self.assertRaises(ApiError): bgv_app.fetch_result(self.conn,'u1',request['request_id'],str(uuid.uuid4()))
        self.assertFalse(bgv_app.work_one(self.conn))
    def test_pan_uan_and_civil_excluded(self):
        self.assertEqual(set(bgv_app.CHECKS),{'current_employer','individual_search','fir_search'})
        for op in ('pan_simple','pan_extensive','uan_passbook'):
            with self.assertRaises(ApiError): bgv_app.submit(self.conn,'u1',self.body(op))
        body=self.body(); body['inputs']['caseCategory']='civil'
        with self.assertRaises(ApiError): bgv_app.submit(self.conn,'u1',body)
    def test_policy_market_assignment_snapshot_and_routing(self):
        policy=bgv_policy.seed(self.conn); self.assertEqual(policy['total'],147)
        bgv_policy.seed(self.conn)
        with self.assertRaises(ValueError): bgv_policy.assign(self.conn,'u1','US','NYC','test')
        case=bgv_policy.assign(self.conn,'u1','IN','BLR','Explicit sandbox pilot')
        self.assertEqual(db.fetch_one(self.conn,'User',id='u1')['active_bgv_case_id'],case)
        with self.assertRaises(ValueError): bgv_policy.assign(self.conn,'u1','IN','BLR','reassign')
        with patch.dict(os.environ,{'DHASHU_BGV_POLICY_ENABLED':'1'}):
            with self.assertRaises(ApiError): bgv_app.submit(self.conn,'u2',self.body())
            request=self.body(); bgv_app.submit(self.conn,'u1',request)
            self.assertIsNotNone(db.fetch_one(self.conn,'BgvRequest',id=request['request_id'])['case_check_id'])
            with self.assertRaises(ApiError): bgv_policy.check_for(self.conn,'u1','liveness','preproduction')
            with self.assertRaises(ApiError): bgv_policy.check_for(self.conn,'u1','criminal_court','production')
        view=bgv_policy.view(self.conn,'u1'); self.assertFalse(view['overall_approval'])
        self.assertEqual(len(view['checks']),5); self.assertEqual(view['approval_gate'],'not_configured')
        self.assertFalse(bgv_policy.view(self.conn,'u2')['assigned'])
    def test_smart_contract_distinguishes_liveness_and_match(self):
        values={'livenessImage':'https://persist.signzy.tech/api/files/selfie/download/synthetic.jpeg',
            'faceMatchImage':'https://preproduction-persist.signzy.tech/api/files/reference/download/synthetic.jpeg',
            'livenessStrictMode':True,'faceMatchThreshold':0.7}
        self.assertEqual(smart_verification.payload(values),values)
        for url in ('http://persist.signzy.tech/api/files/a/download/b','https://evil.example/api/files/a/download/b','https://persist.signzy.tech@evil.example/api/files/a/download/b'):
            with self.assertRaises(ValueError): smart_verification.payload({**values,'livenessImage':url})
        body={'result':{'liveness':{'liveness':True,'score':1},'match':{'verified':False,'matchPercentage':'2.00%'}},'code':'S001','reason':'REQUEST_SUCCESSFUL'}
        result=smart_verification.summarize(200,body)
        self.assertTrue(result['liveness_passed']); self.assertFalse(result['face_match_passed']); self.assertFalse(result['automatic_verification'])
        self.assertIsNone(smart_verification.summarize(200,[])['liveness_passed'])
        response=io.BytesIO(json.dumps(body).encode()); response.code=200
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.return_value=response
            summary=Client(Config(token='synthetic')).execute('smart_verification',values,consent_confirmed=True)
            self.assertTrue(opener.return_value.open.call_args.args[0].full_url.endswith('/face/smart-verification'))
            self.assertNotIn('synthetic.jpeg',json.dumps(summary))
    def test_fir_conflicting_ids_fail_closed(self):
        self.assertEqual(fir_search.result_identifier({'result':{'status':1,'verifyId':'synthetic_fir_123'}}),'synthetic_fir_123')
        for body in ({'result':{'status':0,'verifyId':'synthetic_fir_123'}},{'searchId':'different_123','result':{'status':1,'verifyId':'synthetic_fir_123'}}):
            with self.assertRaises(ValueError): fir_search.result_identifier(body)
    def test_private_photo_reference_and_placeholder(self):
        photo='https://persist.wayne-rta.com/api/files/ref/download/synthetic.jpeg'
        self.assertIsNotNone(document_photo.reference({'result':{'photo':photo}}))
        self.assertIsNone(document_photo.reference({'result':{'photo':'http://127.0.0.1/private'}}))
        app=Flask(__name__)
        @app.before_request
        def auth(): g.api_user={'user_id':'u1'}; g.auth_session={'kind':'mobile'}
        @app.errorhandler(ApiError)
        def error(exc): return {'error':exc.message},exc.status
        bgv_app_api.register(app,lambda:self.conn)
        result=app.test_client().get('/verification/liveness',headers={'Authorization':'Bearer synthetic'})
        self.assertEqual(result.status_code,200); self.assertEqual(result.json['state'],'setup_required')
        self.assertFalse(result.json['enabled']); self.assertNotIn(photo,json.dumps(result.json))
    def test_additive_migration_and_no_account_approval(self):
        db.init_db(self.conn)
        self.assertIn('active_bgv_case_id',db._existing_columns(self.conn,'User'))
        self.assertIn('case_check_id',db._existing_columns(self.conn,'BgvRequest'))
        self.assertEqual(db.fetch_one(self.conn,'User',id='u1')['bgv_status'],'declared')
    def test_operator_review_bound_to_attempt_and_no_overall_approval(self):
        bgv_policy.seed(self.conn); cid=bgv_policy.assign(self.conn,'u1','IN','BLR','pilot')
        with patch.dict(os.environ,{'DHASHU_BGV_POLICY_ENABLED':'1'}):
            body=self.body(); bgv_app.submit(self.conn,'u1',body)
            self.work({'caseId':'synthetic_case_123'})
            child=str(uuid.uuid4()); bgv_app.fetch_result(self.conn,'u1',body['request_id'],child)
            self.work({'cases':[],'total':0})
        check=db.fetch_one(self.conn,'BgvCaseCheck',case_id=cid,check_definition_id='criminal_court')
        attempt=db.fetch_all(self.conn,'BgvAttempt',request_id=child)[0]
        result=bgv_policy.review(self.conn,check['id'],attempt['id'],'satisfied','Synthetic review note','operator-test')
        self.assertFalse(result['overall_approval'])
        saved=db.fetch_one(self.conn,'BgvReview',id=result['review_id'])
        self.assertNotIn('Synthetic review note',saved['protected_note'])
        status=next(c for c in bgv_policy.view(self.conn,'u1')['checks'] if c['key']=='criminal_court')
        self.assertEqual(status['state'],'reviewed_satisfied')
        other=db.fetch_one(self.conn,'BgvCaseCheck',case_id=cid,check_definition_id='fir')
        with self.assertRaises(ValueError): bgv_policy.review(self.conn,other['id'],attempt['id'],'satisfied','wrong check','operator-test')
        self.assertEqual(db.fetch_one(self.conn,'User',id='u1')['bgv_status'],'declared')
    def test_coverage_disable_prevents_queued_provider_call(self):
        bgv_policy.seed(self.conn); bgv_policy.assign(self.conn,'u1','IN','BLR','pilot')
        with patch.dict(os.environ,{'DHASHU_BGV_POLICY_ENABLED':'1'}):
            body=self.body(); bgv_app.submit(self.conn,'u1',body)
            self.conn.execute('UPDATE "BgvProviderCoverage" SET state=? WHERE check_key=?',('disabled','criminal_court')); self.conn.commit()
            with patch('urllib.request.build_opener') as opener:
                self.assertTrue(bgv_app.work_one(self.conn)); opener.assert_not_called()
        self.assertEqual(db.fetch_one(self.conn,'BgvRequest',id=body['request_id'])['state'],'unavailable')

if __name__=='__main__': unittest.main()
