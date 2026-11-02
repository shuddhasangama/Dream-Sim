import json
import os
import sqlite3
import unittest
from pathlib import Path
from unittest.mock import patch
from cryptography.fernet import Fernet
from flask import Flask
import waitlist_service as service
import waitlist_api
from waitlist_admin import set_launch
from api_contract import ApiError

class WaitlistTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,{'DHASHU_WAITLIST_ENABLED':'1','WAITLIST_ENCRYPTION_KEY':Fernet.generate_key().decode(),'WAITLIST_HASH_KEY':'test-only-secret-at-least-32-characters'})
        self.env.start();self.conn=sqlite3.connect(':memory:');self.conn.row_factory=sqlite3.Row
        schema=Path('schema.sql').read_text(encoding='utf-8')
        self.conn.executescript('CREATE TABLE "User" (id TEXT PRIMARY KEY);'+schema[schema.index('CREATE TABLE IF NOT EXISTS "WaitlistMarket"'):])
    def tearDown(self):self.conn.close();self.env.stop()
    def entry(self):return {'email':'test@example.invalid','name':'Private Name','market_id':'IN-BLR','gender':'A woman','age_band':'25–29',
        'neighbourhoods':['indiranagar'],'answers':{'guru':1},'consent':True,'consent_version':service.CONSENT_VERSION}
    def test_save_encrypted_and_no_account_creation(self):
        self.assertTrue(service.submit(self.conn,self.entry())['saved'])
        row=dict(self.conn.execute('SELECT * FROM "WaitlistEntry"').fetchone())
        self.assertNotIn('Private Name',json.dumps(row));self.assertNotIn('test@example',json.dumps(row))
        self.assertEqual(row['contact_verified'],0);self.assertEqual(row['status'],'waiting')
        self.assertEqual(self.conn.execute('SELECT count(*) FROM "User"').fetchone()[0],0)
        self.assertEqual(service.statistics(self.conn)['markets']['IN-BLR']['neighbourhoods']['indiranagar'],1)
    def test_duplicate_does_not_overwrite_or_expose(self):
        body=self.entry();first=service.submit(self.conn,body)
        body.update(email='TEST@EXAMPLE.INVALID',name='Impersonator')
        self.assertEqual(first,service.submit(self.conn,body))
        rows=self.conn.execute('SELECT * FROM "WaitlistEntry"').fetchall();self.assertEqual(len(rows),1)
        data=json.loads(service.cipher().decrypt(rows[0]['protected_data'].encode()))
        self.assertEqual(data['name'],'Private Name')

    def test_statistics_cover_demographics_consent_and_test_entries(self):
        service.submit(self.conn,self.entry())
        service.submit(self.conn,self.entry()|{'email':'deployment@example.invalid','gender':'Prefer not to say',
            'age_band':'Over 50','source':'deployment-smoke-test','answers':{},'name':''})
        before=list(self.conn.iterdump())
        result=service.statistics(self.conn)
        self.assertEqual(result['total_registrations'],2)
        self.assertEqual(result['non_test_registrations'],1)
        self.assertEqual(result['synthetic_test_registrations'],1)
        totals=result['totals']
        self.assertEqual(totals['genders'],{'A woman':1,'Prefer not to say':1})
        self.assertEqual(totals['age_bands'],{'25–29':1,'Over 50':1})
        self.assertEqual(totals['consent_versions'],{'waitlist-v1':2})
        self.assertEqual(totals['consent_recorded'],2)
        self.assertEqual(totals['with_story_answers'],1)
        self.assertEqual(totals['without_story_answers'],1)
        self.assertEqual(totals['with_name'],1)
        self.assertEqual(totals['with_email'],2)
        self.assertEqual(result['markets']['IN-BLR']['genders'],totals['genders'])
        self.assertEqual(result['markets']['IN-BLR']['city'],'Bengaluru')
        self.assertNotIn('Private Name',json.dumps(result))
        self.assertNotIn('test@example.invalid',json.dumps(result))
        self.assertEqual(before,list(self.conn.iterdump()))
    def test_invalid_preferences_or_consent(self):
        for change in ({'consent':False},{'neighbourhoods':['unknown']},{'neighbourhoods':['indiranagar']*4},
                       {'market_id':'US-FAKE'},{'email':'bad'},{'website':'spam'}):
            with self.assertRaises(ApiError):service.submit(self.conn,self.entry()|change)
    def test_launch_is_manual_and_does_not_activate(self):
        service.submit(self.conn,self.entry());set_launch(self.conn,'IN-BLR','open','test-operator')
        self.assertEqual(service.public_config(self.conn)['markets'][0]['launch_status'],'open')
        self.assertEqual(self.conn.execute('SELECT status FROM "WaitlistEntry"').fetchone()[0],'waiting')
        self.assertEqual(self.conn.execute('SELECT count(*) FROM "WaitlistAudit"').fetchone()[0],1)
    def test_origin_and_failure_responses(self):
        app=Flask(__name__);waitlist_api.register(app,lambda:self.conn);client=app.test_client()
        self.assertEqual(client.post('/public/waitlist',json=self.entry()).status_code,403)
        headers={'Origin':'https://dhashu.com'}
        with patch('auth_sessions.throttle',return_value=True):
            result=client.post('/public/waitlist',json=self.entry(),headers=headers)
        self.assertEqual(result.status_code,201);self.assertTrue(result.json['saved'])
        self.assertEqual(result.headers['Access-Control-Allow-Origin'],'https://dhashu.com')
        self.assertEqual(result.headers['Cache-Control'],'no-store')
        with patch.dict(os.environ,{'DHASHU_WAITLIST_ENABLED':'0'}):
            self.assertEqual(client.get('/public/waitlist/config',headers=headers).status_code,503)

    def test_public_waitlist_with_secure_auth_enabled(self):
        import auth
        app=Flask(__name__);app.secret_key='test-only-secret-with-more-than-32-characters'
        with patch.dict(os.environ,{'AUTH_ENABLED':'1','AUTH_PUBLIC_ORIGIN':'https://backend.example','SECRET_KEY':app.secret_key}), patch('auth_delivery.configured',return_value=True):
            auth.register_auth(app,lambda:self.conn)
        waitlist_api.register(app,lambda:self.conn)
        client=app.test_client()
        with patch('auth_sessions.throttle',return_value=True):
            result=client.post('/public/waitlist',json=self.entry(),headers={'Origin':'https://dhashu.com'})
        self.assertEqual(result.status_code,201)
        self.assertEqual(self.conn.execute('SELECT count(*) FROM "WaitlistEntry"').fetchone()[0],1)
        self.assertEqual(client.post('/public/waitlist',json=self.entry(),headers={'Origin':'https://untrusted.example'}).status_code,403)
        self.assertEqual(client.post('/public/waitlist',json=self.entry()).status_code,403)
        # Nearby routes and ordinary browser writes retain the global boundary.
        self.assertEqual(client.post('/public/waitlist/other',headers={'Origin':'https://dhashu.com'}).status_code,403)
        self.assertEqual(client.post('/calendar/availability',headers={'Origin':'https://dhashu.com'}).status_code,403)
