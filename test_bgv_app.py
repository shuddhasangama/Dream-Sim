import io
import json
import os
import sqlite3
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch
from cryptography.fernet import Fernet
from flask import Flask, g
import bgv_app
import bgv_app_api
from api_contract import ApiError

class BgvAppTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'DHASHU_BGV_APP_ENABLED':'1','SIGNZY_ENV':'preproduction',
            'SIGNZY_TEST_API_KEY':'synthetic', 'SIGNZY_RECEIPT_ENCRYPTION_KEY':Fernet.generate_key().decode()})
        self.env.start()
        self.conn = sqlite3.connect(':memory:'); self.conn.row_factory = sqlite3.Row
        self.conn.executescript('CREATE TABLE "User" (id TEXT PRIMARY KEY); INSERT INTO "User" VALUES (\'u1\'); INSERT INTO "User" VALUES (\'u2\');')
        schema = Path('schema.sql').read_text(encoding='utf-8')
        self.conn.executescript(schema[schema.index('CREATE TABLE IF NOT EXISTS "BgvEvidence"'):])
    def tearDown(self):
        self.conn.close(); self.env.stop()
    def body(self):
        return {'request_id':str(uuid.uuid4()),'operation':'pan_simple','inputs':{'panNumber':'AAAPA0000A'},
            'declared':{'name':'Jane Doe','dob':'2000-01-01'},'consent':True,'consent_version':bgv_app.VERSION}
    def run_response(self, status=200, body=None):
        if body is None:
            body={'result':{'name':'JANE DOE','dob':'2000-01-01','panStatus':'VALID'}}
        response = io.BytesIO(json.dumps(body).encode()); response.code = status
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.return_value = response
            self.assertTrue(bgv_app.work_one(self.conn))
            self.assertEqual(opener.return_value.open.call_count, 1)
    def test_queue_worker_encryption_and_ownership(self):
        request = self.body(); bgv_app.submit(self.conn,'u1',request)
        bgv_app.submit(self.conn,'u1',request)
        self.assertEqual(len(bgv_app.view(self.conn,'u2')['results']), 0)
        raw = self.conn.execute('SELECT protected_input FROM "BgvRequest"').fetchone()[0]
        self.assertNotIn('Jane',raw)
        self.run_response()
        result = bgv_app.view(self.conn,'u1')['results'][0]
        self.assertEqual(result['state'],'verified')
        self.assertEqual(result['environment'],'preproduction')
        self.assertNotIn('Jane',json.dumps(result))
        self.assertFalse(bgv_app.work_one(self.conn))
    def test_missing_consent_and_duplicate_active(self):
        body=self.body(); body['consent']=False
        with self.assertRaises(ApiError): bgv_app.submit(self.conn,'u1',body)
        body['consent']=True; bgv_app.submit(self.conn,'u1',body)
        with self.assertRaises(ApiError): bgv_app.submit(self.conn,'u1',self.body())
        with self.assertRaises(ApiError): bgv_app.submit(self.conn,'u2',body)
    def test_provider_denial_is_unavailable_not_mismatch(self):
        bgv_app.submit(self.conn,'u1',self.body())
        self.run_response(403,{'message':'You cannot consume this service'})
        self.assertEqual(bgv_app.view(self.conn,'u1')['results'][0]['state'],'unavailable')
    def test_timeout_never_retried(self):
        bgv_app.submit(self.conn,'u1',self.body())
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.side_effect=TimeoutError()
            bgv_app.work_one(self.conn)
        self.assertEqual(bgv_app.view(self.conn,'u1')['results'][0]['state'],'outcome_unknown')
        self.assertFalse(bgv_app.work_one(self.conn))
        with self.assertRaises(ApiError): bgv_app.submit(self.conn,'u1',self.body())
    def test_disabled_fails_closed(self):
        with patch.dict(os.environ,{'DHASHU_BGV_APP_ENABLED':'0'}):
            self.assertFalse(bgv_app.view(self.conn,'u1')['enabled'])
            with self.assertRaises(ApiError): bgv_app.submit(self.conn,'u1',self.body())
    def test_api_bearer_and_private_response(self):
        app=Flask(__name__)
        @app.before_request
        def actor():
            g.auth_session = {'kind':'mobile'} if self.authenticated else None
            g.api_user={'user_id':'u1'}
        @app.errorhandler(ApiError)
        def error(exc): return {'error':exc.message},exc.status
        bgv_app_api.register(app,lambda:self.conn)
        client=app.test_client(); self.authenticated=False
        self.assertEqual(client.get('/verification').status_code,401)
        self.authenticated=True
        result=client.get('/verification',headers={'Authorization':'Bearer synthetic'})
        self.assertEqual(result.status_code,200)
        self.assertEqual(result.headers['Cache-Control'],'no-store')
