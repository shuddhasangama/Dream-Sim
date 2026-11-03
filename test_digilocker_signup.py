import io
import json
import os
import sqlite3
import unittest
import uuid
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch
from cryptography.fernet import Fernet
from flask import Flask, g
from api_contract import ApiError
import digilocker_signup as service
import digilocker_api

class DigiLockerSignupTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{'DHASHU_DIGILOCKER_ENABLED':'1','DHASHU_DIGILOCKER_TESTERS':'u1,u2',
            'SIGNZY_ENV':'preproduction','SIGNZY_TEST_API_KEY':'synthetic',
            'SIGNZY_RECEIPT_ENCRYPTION_KEY':Fernet.generate_key().decode(),
            'SIGNZY_DIGILOCKER_CALLBACK_BASE':'https://example.com/public/signzy/digilocker/callback'})
        self.env.start()
        self.conn=sqlite3.connect(':memory:'); self.conn.row_factory=sqlite3.Row
        self.conn.executescript('CREATE TABLE "User" (id TEXT PRIMARY KEY, bgv_status TEXT); INSERT INTO "User" VALUES (\'u1\',\'declared\'); INSERT INTO "User" VALUES (\'u2\',\'declared\');')
        schema=Path('schema.sql').read_text(encoding='utf-8')
        self.conn.executescript(schema[schema.index('CREATE TABLE IF NOT EXISTS "DigiLockerSession"'):])
        self.body={'request_id':str(uuid.uuid4()),'consent':True,'consent_version':service.VERSION}
    def tearDown(self):
        self.conn.close(); self.env.stop()
    def provider(self,body,status=200):
        response=io.BytesIO(json.dumps(body).encode()); response.code=status
        mock=patch('urllib.request.build_opener'); opener=mock.start()
        self.addCleanup(mock.stop); opener.return_value.open.return_value=response
        return opener.return_value.open
    def create(self):
        call=self.provider({'result':{'requestId':'request_12345678','url':'https://api.digitallocker.gov.in/public/oauth2/1/authorize?state=request_12345678'}})
        service.create(self.conn,'u1',self.body)
        self.assertEqual(call.call_count,1)
        return self.body['request_id']
    def test_full_flow_idempotent_and_minimal_encrypted_identity(self):
        sid=self.create()
        service.create(self.conn,'u1',self.body)
        self.assertEqual(service.view(self.conn,'u1')['session']['state'],'awaiting_consent')
        self.assertIsNone(service.view(self.conn,'u2')['session'])
        photo='https://persist.wayne-rta.com/api/files/document/download/private-reference.jpeg'
        call=self.provider({'result':{'name':'SYNTHETIC PERSON','dob':'01/01/1995','address':'Synthetic address','uid':'DO NOT STORE','photo':photo}})
        service.complete(self.conn,'u1',sid,{'consent_completed':True})
        payload=json.loads(call.call_args.args[0].data)
        self.assertEqual(payload,{'requestId':'request_12345678','extraDigitalCertificateParams':'false','getEAadhaarPdf':False,'getEAadhaarJpeg':True})
        result=service.view(self.conn,'u1')['session']
        self.assertEqual(result['state'],'complete')
        self.assertEqual(result['identity']['name'],'SYNTHETIC PERSON')
        self.assertFalse(result['identity']['current_address_verified'])
        self.assertNotIn('uid',result['identity'])
        self.assertTrue(result['reference_photo_available'])
        self.assertNotIn(photo,json.dumps(result))
        self.assertNotIn(photo,json.dumps(dict(self.conn.execute('SELECT * FROM "DigiLockerSession"').fetchone())))
        service.complete(self.conn,'u1',sid,{'consent_completed':True})
        self.assertEqual(call.call_count,1)
        stored=json.dumps(dict(self.conn.execute('SELECT * FROM "DigiLockerSession"').fetchone()))
        for secret in ('SYNTHETIC PERSON','request_12345678','Synthetic address','DO NOT STORE'):
            self.assertNotIn(secret,stored)
        self.assertEqual(self.conn.execute('SELECT bgv_status FROM "User" WHERE id=\'u1\'').fetchone()[0],'declared')
    def test_v3_requests_pan_and_records_bundle_consent_without_inline_screening(self):
        self.body['consent_version']=service.BUNDLE_VERSION
        call=self.provider({'result':{'requestId':'request_12345678','url':'https://api.digitallocker.gov.in/public/oauth2/1/authorize'}})
        service.create(self.conn,'u1',self.body)
        self.assertEqual(json.loads(call.call_args.args[0].data)['docType'],['ADHAR','PANCR'])
        call=self.provider({'result':{'name':'SYNTHETIC PERSON','dob':'01/01/1990','address':'SYNTHETIC ADDRESS'}})
        service.complete(self.conn,'u1',self.body['request_id'],{'consent_completed':True})
        self.assertEqual(call.call_count,1)
        public=service.view(self.conn,'u1')
        self.assertEqual(public['consent_version'],service.BUNDLE_VERSION)
        self.assertNotIn('_bundle',public['session']['identity'])
        private=service.Protection().open(dict(self.conn.execute('SELECT * FROM "DigiLockerSession"').fetchone())['protected_result'])
        self.assertTrue(private['_bundle']['pan_scope'])
        self.assertEqual(private['_bundle']['version'],service.BUNDLE_VERSION)

    def test_consent_ownership_and_expiry(self):
        with self.assertRaises(ApiError): service.create(self.conn,'u1',{**self.body,'consent':False})
        sid=self.create()
        for uid,body in [('u2',{'consent_completed':True}),('u1',{'consent_completed':False})]:
            with self.assertRaises(ApiError): service.complete(self.conn,uid,sid,body)
        self.conn.execute('UPDATE "DigiLockerSession" SET expires_at=?',((service.now()-timedelta(seconds=1)).isoformat(),)); self.conn.commit()
        with self.assertRaises(ApiError): service.complete(self.conn,'u1',sid,{'consent_completed':True})
        self.assertEqual(service.view(self.conn,'u1')['session']['state'],'expired')
    def test_timeout_never_replayed(self):
        sid=self.create()
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect=TimeoutError()
            service.complete(self.conn,'u1',sid,{'consent_completed':True})
            with self.assertRaises(ApiError): service.complete(self.conn,'u1',sid,{'consent_completed':True})
            self.assertEqual(opener.return_value.open.call_count,1)
        self.assertEqual(service.view(self.conn,'u1')['session']['state'],'outcome_unknown')
    def test_unconfirmed_attempt_cooldown_and_no_repeat_vendor_call(self):
        sid=self.create(); call=self.provider({},202)
        service.complete(self.conn,'u1',sid,{'consent_completed':True})
        result=service.view(self.conn,'u1')['session']
        self.assertEqual(result['state'],'not_confirmed'); self.assertTrue(result['cooling_down'])
        self.assertNotIn('consent_url',result)
        with self.assertRaises(ApiError): service.complete(self.conn,'u1',sid,{'consent_completed':True})
        with self.assertRaises(ApiError): service.create(self.conn,'u1',{**self.body,'request_id':str(uuid.uuid4())})
        self.assertEqual(call.call_count,1)
        later=service.now()+timedelta(minutes=31)
        with patch.object(service,'now',return_value=later):
            with self.assertRaises(ApiError): service.complete(self.conn,'u1',sid,{'consent_completed':True})
            self.assertTrue(service.view(self.conn,'u1')['session']['can_restart'])
            self.body['request_id']=str(uuid.uuid4()); self.create()
        self.assertEqual(call.call_count,1)
    def test_invalid_identity_not_approved(self):
        sid=self.create()
        self.provider({'result':{'name':'Test','dob':'not a date','address':'Test'}})
        service.complete(self.conn,'u1',sid,{'consent_completed':True})
        self.assertEqual(service.view(self.conn,'u1')['session']['state'],'needs_review')
    def test_age_boundary(self):
        body={'result':{'name':'Test','dob':'03/11/2008','address':'Test'}}
        self.assertFalse(service.projection(body,date(2026,11,2))['adult'])
        self.assertEqual(service.projection(body,date(2026,11,3))['age'],18)
        body['result']['dob']='01/01/2099'
        with self.assertRaises(ValueError): service.projection(body,date(2026,11,2))
    def test_api_e2e_boundary(self):
        app=Flask(__name__); self.actor='u1'
        @app.before_request
        def auth():
            g.api_user={'user_id':self.actor}; g.auth_session={'kind':'mobile'} if self.actor else None
        @app.errorhandler(ApiError)
        def error(exc): return {'error':exc.message},exc.status
        digilocker_api.register(app,lambda:self.conn)
        client=app.test_client(); headers={'Authorization':'Bearer synthetic'}
        self.assertEqual(client.get('/verification/digilocker').status_code,401)
        self.provider({'result':{'requestId':'request_12345678','url':'https://api.digitallocker.gov.in/public/oauth2/1/authorize'}})
        result=client.post('/verification/digilocker/sessions',json=self.body,headers=headers)
        self.assertEqual(result.status_code,200); self.assertEqual(result.headers['Cache-Control'],'no-store')
        sid=result.json['session']['id']; self.actor='u2'
        self.assertEqual(client.post('/verification/digilocker/sessions/'+sid+'/complete',json={'consent_completed':True},headers=headers).status_code,404)
        self.actor='u1'
        self.assertEqual(client.post('/verification/digilocker/sessions/'+sid+'/complete',json={'consent_completed':True,'requestId':'other'},headers=headers).status_code,400)
        self.provider({'result':{'name':'Test','dob':'01/01/1990','address':'Test'}})
        result=client.post('/verification/digilocker/sessions/'+sid+'/complete',json={'consent_completed':True},headers=headers)
        self.assertEqual(result.json['session']['state'],'complete')
    def test_disabled_and_tester_scope(self):
        self.assertFalse(service.view(self.conn,'ordinary_user')['enabled'])
        with patch.dict(os.environ,{'DHASHU_DIGILOCKER_ENABLED':'0'}):
            with self.assertRaises(ApiError): service.create(self.conn,'u1',self.body)
    def test_old_consent_never_requests_photo_and_allows_new_photo_consent(self):
        sid=self.create()
        self.conn.execute('UPDATE "DigiLockerSession" SET consent_version=? WHERE id=?',('digilocker-identity-v1',sid)); self.conn.commit()
        call=self.provider({'result':{'name':'Test','dob':'01/01/1990','address':'Test','photo':'https://persist.wayne-rta.com/api/files/ref/download/photo.jpeg'}})
        service.complete(self.conn,'u1',sid,{'consent_completed':True})
        self.assertFalse(json.loads(call.call_args.args[0].data)['getEAadhaarJpeg'])
        result=service.view(self.conn,'u1')['session']
        self.assertFalse(result['can_request_photo']); self.assertFalse(result['reference_photo_available'])
        later=service.now()+timedelta(minutes=31)
        with patch.object(service,'now',return_value=later):
            self.assertTrue(service.view(self.conn,'u1')['session']['can_request_photo'])
            self.body['request_id']=str(uuid.uuid4()); self.create()

if __name__=='__main__': unittest.main()
