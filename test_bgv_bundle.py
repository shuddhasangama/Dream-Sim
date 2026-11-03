"""Synthetic combined DigiLocker -> criminal/FIR/employer workflow acceptance."""
import json
import os
import sqlite3
import unittest
import uuid
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
from cryptography.fernet import Fernet
import db
import bgv_app
import bgv_bundle
import digilocker_signup as identity
from api_contract import ApiError
from signzy.digilocker_details import documents,payload

class BundleTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{'DHASHU_BGV_APP_ENABLED':'1','DHASHU_BGV_POLICY_ENABLED':'0','SIGNZY_ENV':'preproduction','SIGNZY_TEST_API_KEY':'synthetic','SIGNZY_RECEIPT_ENCRYPTION_KEY':Fernet.generate_key().decode()})
        self.env.start();self.addCleanup(self.env.stop)
        self.conn=sqlite3.connect(':memory:');self.conn.row_factory=sqlite3.Row;db.init_db(self.conn);self.addCleanup(self.conn.close)
        self.conn.execute('INSERT INTO "User" (id,journey_state) VALUES (?,?)',('u1','onboarding'));self.conn.commit()
        self.sid=str(uuid.uuid4());self.protection=bgv_app.Protection()
    def session(self,bundle=True,version=identity.BUNDLE_VERSION):
        value={'name':'SYNTHETIC PERSON','dob':'1990-01-01','age':36,'document_address':'SYNTHETIC ADDRESS','adult':True}
        if bundle:value['_bundle']={'version':identity.BUNDLE_VERSION,'accepted_at':bgv_app.stamp(),'pan_scope':version==identity.BUNDLE_VERSION,'employer':'Synthetic Ltd'}
        stamp=bgv_app.stamp()
        self.conn.execute('INSERT INTO "DigiLockerSession" (id,user_id,environment,state,protected_session,protected_result,consent_version,created_at,updated_at,expires_at,attempts) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
            (self.sid,'u1','preproduction','complete',self.protection.seal({'requestId':'synthetic_request_123'}),self.protection.seal(value),version,stamp,stamp,stamp,1));self.conn.commit()
    def details(self,pan=True,mobile='9876543210',name='SYNTHETIC PERSON'):
        return {'result':{'userDetails':{'name':name,'mobile':mobile},'files':[{'doctype':'PANCR','issuerid':'in.gov.pan','id':'in.gov.pan-PANCR-ABCDE1234F'}] if pan else []}}
    def execute(self,operation,values,**kwargs):
        from signzy.client import OPERATIONS
        body={'individual_search':{'caseId':'synthetic_case_123'},'fir_search':{'result':{'status':1,'verifyId':'synthetic_fir_123'}},'individual_result':{'status':1,'cases':[],'total':0},'fir_result':{'status':1,'message':'Processing done','cases':[]},'digilocker_details':self.details()}[operation]
        kwargs['evidence_sink']({'receipt_id':str(uuid.uuid4()),'provider_response':{'http_status':200,'json':body}})
        return {'http_status':200,**OPERATIONS[operation].summarize(200,body)}
    def test_full_background_chain_and_duplicate_refresh_safety(self):
        self.session()
        called=[]
        def execute(op,values,**kwargs):
            called.append((op,values));return self.execute(op,values,**kwargs)
        with patch('bgv_app.Client.execute',side_effect=execute):
            for _ in range(12):
                bgv_bundle.schedule(self.conn)
                if db.fetch_all(self.conn,'BgvRequest',operation='current_employer'):break
                bgv_app.work_one(self.conn)
            # Finish criminal/FIR lookups without invoking employer in this fixture.
            for _ in range(4):bgv_bundle.schedule(self.conn)
        rows=db.fetch_all(self.conn,'BgvRequest')
        self.assertEqual(len(rows),6)
        for op in ('individual_search','fir_search','digilocker_details','current_employer','individual_result','fir_result'):
            self.assertEqual(sum(r['operation']==op for r in rows),1)
        employer=next(r for r in rows if r['operation']=='current_employer')
        private=self.protection.open(employer['protected_input'])
        self.assertEqual(private['inputs'],{'panNumber':'ABCDE1234F','mobile':'9876543210'})
        self.assertEqual(private['declared'],{'employer':'Synthetic Ltd'})
        for op,values in called:
            if op in ('individual_search','fir_search'):
                self.assertEqual(values['name'],'SYNTHETIC PERSON');self.assertEqual(values['address'],'SYNTHETIC ADDRESS')
        public=json.dumps(bgv_app.view(self.conn,'u1'))
        self.assertNotIn('ABCDE1234F',public);self.assertNotIn('9876543210',public)
        self.assertEqual(db.fetch_one(self.conn,'User',id='u1')['bgv_status'],'declared')
        self.assertEqual(bgv_bundle.view(self.conn,'u1')['pan_state'],'received')
    def test_no_retroactive_screening_and_owner_bound_consent(self):
        self.session(bundle=False,version=identity.VERSION)
        bgv_bundle.schedule(self.conn);self.assertEqual(db.fetch_all(self.conn,'BgvRequest'),[])
        body={'session_id':self.sid,'consent':True,'consent_version':identity.BUNDLE_VERSION}
        with self.assertRaises(ApiError):bgv_bundle.consent(self.conn,'u2',body)
        with self.assertRaises(ApiError):bgv_bundle.consent(self.conn,'u1',{**body,'consent':False})
        bgv_bundle.consent(self.conn,'u1',body);bgv_bundle.schedule(self.conn)
        self.assertEqual({r['operation'] for r in db.fetch_all(self.conn,'BgvRequest')},{'individual_search','fir_search'})
    def test_missing_pan_or_mobile_does_not_block_legal_checks(self):
        self.session();bgv_bundle.schedule(self.conn)
        with patch('bgv_app.Client.execute',side_effect=lambda op,values,**kw:self.missing_details(op,values,kw)):
            for _ in range(6):
                bgv_app.work_one(self.conn);bgv_bundle.schedule(self.conn)
        self.assertFalse(db.fetch_all(self.conn,'BgvRequest',operation='current_employer'))
        self.assertTrue(db.fetch_all(self.conn,'BgvRequest',operation='individual_result'))
        self.assertTrue(db.fetch_all(self.conn,'BgvRequest',operation='fir_result'))
        self.assertEqual(bgv_bundle.view(self.conn,'u1')['pan_state'],'not_shared')
    def missing_details(self,op,values,kwargs):
        if op!='digilocker_details':return self.execute(op,values,**kwargs)
        kwargs['evidence_sink']({'receipt_id':str(uuid.uuid4()),'provider_response':{'http_status':200,'json':self.details(False)}})
        return {'http_status':200,'outcome':'document_listing_received'}
    def test_unknown_outcome_is_never_automatically_replayed(self):
        self.session();bgv_bundle.schedule(self.conn)
        self.conn.execute('UPDATE "BgvRequest" SET state=?',('outcome_unknown',));self.conn.commit()
        for _ in range(3):bgv_bundle.schedule(self.conn)
        self.assertEqual(len(db.fetch_all(self.conn,'BgvRequest')),3)
        self.assertFalse(bgv_app.work_one(self.conn))
    def test_get_details_contract_rejects_ambiguous_or_untrusted_identifiers(self):
        self.assertEqual(payload({'requestId':'synthetic_request_123'}),{'requestId':'synthetic_request_123'})
        with self.assertRaises(ValueError):payload({'requestId':'synthetic_request_123','user_id':'u2'})
        body=self.details();body['result']['files'][0]['issuerid']='untrusted'
        self.assertIsNone(documents(body)['pan'])
        body=self.details();body['result']['files'].append({'doctype':'PANCR','issuerid':'in.gov.pan','id':'in.gov.pan-PANCR-BCDEF2345G'})
        self.assertEqual(documents(body)['pan_state'],'needs_review');self.assertIsNone(documents(body)['pan'])
