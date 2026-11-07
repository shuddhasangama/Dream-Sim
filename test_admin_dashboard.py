import base64
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch
from cryptography.fernet import Fernet
import db
from admin_dashboard import reports,security
from admin_dashboard.manage import initialize
from admin_dashboard.app import create_app

class AdminDashboardTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.path=str(Path(self.temp.name)/'dashboard.db')
  self.env=patch.dict(os.environ,{'DATABASE_URL':'','ADMIN_ALLOW_HTTP':'1','ADMIN_PUBLIC_ORIGIN':'http://localhost','ADMIN_LOCAL_DB_PATH':self.path,'ADMIN_TOTP_ENCRYPTION_KEY':Fernet.generate_key().decode(),'DHASHU_TESTER_NO_OTP':'false'})
  self.env.start();self.conn=db.get_connection(self.path);db.init_db(self.conn);initialize(self.conn)
  self.now=int(time.time())//30*30;self.secret=base64.b32encode(b'12345678901234567890').decode();self.password='Private-dashboard-password-2026'
  with patch('time.time',return_value=self.now-60):security.create_identity(self.conn,'office@shuddhasangama.org',self.password,self.secret,security.code(self.secret,(self.now-60)//30))
  for uid,phone,enabled in [('u1','+919000000001',1),('u2','+919000000002',0)]:
   db.insert_row(self.conn,'User',{'id':uid,'journey_state':'onboarding','bgv_status':'declared','stats_json':json.dumps({'signup_version':3,'city':'Bangalore','vision_schema_version':2,'signup_stats_saved':True,'health_shared':{'secret':'PRIVATE_HEALTH'},'pan':'PRIVATE_PAN'})})
   db.insert_row(self.conn,'Account',{'id':'a'+uid,'user_id':uid,'phone':phone,'auth_enabled':enabled,'verified_phone':1,'created_at':str(self.now)})
  db.insert_row(self.conn,'User',{'id':'seed_without_account','journey_state':'dating'})
  self.app=create_app();self.app.config['TESTING']=True;self.client=self.app.test_client()
 def tearDown(self):self.conn.close();self.env.stop();self.temp.cleanup()
 def login(self,email='office@shuddhasangama.org',role=None):
  if role:
   self.conn.execute('UPDATE "AdminIdentity" SET role=? WHERE email=?',(role,email));self.conn.commit()
  with patch('time.time',return_value=self.now):
   return self.client.post('/api/login',json={'email':email,'password':self.password,'code':security.code(self.secret,self.now//30)},headers={'Origin':'http://localhost'})
 def csrf(self):return self.client.get('/api/session').get_json()['csrf']
 def test_rfc_totp(self):
  self.assertEqual(security.code(self.secret,1),'287082')
  self.assertIsNone(security.counter_for(self.secret,'\u0661'*6))
 def test_no_auth_no_data_and_cross_origin_login_rejected(self):
  r=self.client.get('/api/reports/users');self.assertEqual(r.status_code,401);self.assertNotIn('9000000001',r.text)
  r=self.client.post('/api/login',json={},headers={'Origin':'https://foreign.example'});self.assertEqual(r.status_code,403)
 def test_owner_reports_mask_sensitive_fields_and_seed_counts(self):
  self.assertEqual(self.login().status_code,200)
  for name in ('overview','users','sessions','checks','marketing','audit'):
   r=self.client.get('/api/reports/'+name);self.assertEqual(r.status_code,200,r.text)
   self.assertNotIn('PRIVATE_HEALTH',r.text);self.assertNotIn('PRIVATE_PAN',r.text);self.assertNotIn('+919000000001',r.text)
  data=self.client.get('/api/reports/overview').get_json();metrics={x['label']:x['value'] for x in data['metrics']}
  self.assertEqual(metrics['Enabled accounts'],1);self.assertEqual(metrics['Disabled accounts'],1)
 def test_search_body_only_and_parameterized(self):
  self.login();headers={'Origin':'http://localhost','X-CSRF-Token':self.csrf()}
  r=self.client.post('/api/search/users',json={'q':'+919000000001'},headers=headers);self.assertEqual(r.status_code,200);self.assertEqual(r.get_json()['rows'][0]['phone'],'•••• 0001')
  r=self.client.get('/api/reports/users?q=9000000001');self.assertEqual(r.status_code,400)
  r=self.client.post('/api/search/users',json={'q':"' OR 1=1 --"},headers=headers);self.assertEqual(r.get_json()['rows'],[])
  self.assertNotIn('9000000001',self.client.get('/api/reports/audit').text)
 def test_csrf_logout_and_session_revocation(self):
  self.login();self.assertEqual(self.client.post('/api/logout',json={},headers={'Origin':'http://localhost'}).status_code,403)
  self.assertEqual(self.client.post('/api/logout',json={},headers={'Origin':'http://localhost','X-CSRF-Token':self.csrf()}).status_code,200)
  self.assertEqual(self.client.get('/api/reports/users').status_code,401)
 def test_marketing_cannot_read_support_or_users(self):
  self.login(role='marketing')
  self.assertEqual(self.client.get('/api/reports/marketing').status_code,200)
  for name in ('overview','users','sessions','checks','audit'):self.assertEqual(self.client.get('/api/reports/'+name).status_code,403)
  self.assertEqual(self.client.post('/api/search/users',json={'q':'u1'},headers={'Origin':'http://localhost','X-CSRF-Token':self.csrf()}).status_code,403)
 def test_totp_replay_and_login_throttle(self):
  self.assertEqual(self.login().status_code,200);self.assertEqual(self.login().status_code,401)
  for _ in range(12):r=self.client.post('/api/login',json={'email':'unknown@example.com','password':'bad','code':'000000'},headers={'Origin':'http://localhost'})
  self.assertEqual(r.status_code,429)
 def test_read_only_reporting_connection_rejects_writes(self):
  with reports.connection() as c:
   with self.assertRaises(sqlite3.OperationalError):c.execute('DELETE FROM "Account"')
  self.assertEqual(len(db.fetch_all(self.conn,'Account')),2)
 def test_idle_expiry_and_security_headers(self):
  r=self.login();self.assertIn('HttpOnly',r.headers.getlist('Set-Cookie')[0]);self.assertIn('SameSite=Strict',r.headers.getlist('Set-Cookie')[0])
  self.conn.execute('UPDATE "AdminSession" SET last_seen_at=?',(int(time.time())-1801,));self.conn.commit()
  self.assertEqual(self.client.get('/api/session').status_code,401)
  r=self.client.get('/');self.assertEqual(r.headers['X-Frame-Options'],'DENY');self.assertEqual(r.headers['Cache-Control'],'no-store')
 def test_session_status_respects_refresh_and_disabled_account(self):
  now=int(time.time())
  for sid,uid in [('s1','u1'),('s2','u2')]:
   self.conn.execute('INSERT INTO "AuthSession" (id,user_id,access_hash,kind,created_at,access_expires_at,expires_at) VALUES (?,?,?,?,?,?,?)',(sid,uid,'hash'+sid,'mobile',now,now-10,now+86400))
   self.conn.execute('INSERT INTO "AuthRefresh" (id,session_id,expires_at) VALUES (?,?,?)',('r'+sid,sid,now+100))
  self.conn.commit();data=reports.sessions(self.conn)
  self.assertEqual({r['user_id']:r['status'] for r in data['rows']},{'u1':'Refresh available','u2':'Account disabled'})
 def test_user_support_summary_is_bounded_and_private(self):
  self.login();headers={'Origin':'http://localhost','X-CSRF-Token':self.csrf()}
  r=self.client.post('/api/user-summary',json={'user_id':'u1'},headers=headers)
  self.assertEqual(r.status_code,200);self.assertEqual(r.get_json()['account'][0]['user_id'],'u1')
  self.assertNotIn('PRIVATE_HEALTH',r.text);self.assertNotIn('PRIVATE_PAN',r.text)
  self.assertEqual(self.client.post('/api/user-summary',json={'user_id':'missing'},headers=headers).status_code,404)
 def test_marketing_cannot_open_support_summary(self):
  self.login(role='marketing');headers={'Origin':'http://localhost','X-CSRF-Token':self.csrf()}
  self.assertEqual(self.client.post('/api/user-summary',json={'user_id':'u1'},headers=headers).status_code,403)
 def test_invalid_production_settings_fail_closed(self):
  with patch.dict(os.environ,{'ADMIN_PUBLIC_ORIGIN':'https://admin.shuddhasangama.org','ADMIN_ALLOW_HTTP':'0','DATABASE_URL':''}):
   with self.assertRaises(ValueError):create_app()


 def test_metric_drilldowns_match_counts_and_reject_unknown_filters(self):
  self.login()
  metrics=self.client.get('/api/reports/overview').get_json()['metrics']
  for m in metrics:
   r=self.client.get('/api/reports/users?filter='+m['filter'])
   self.assertEqual(r.status_code,200,r.text)
   self.assertEqual(len(r.get_json()['rows']),m['value'] or 0)
  self.assertEqual(self.client.get('/api/reports/users?filter=stage:onboarding').status_code,200)
  self.assertEqual(self.client.get('/api/reports/users?filter=stats').status_code,200)
  self.assertEqual(self.client.get('/api/reports/users?filter=not_a_filter').status_code,400)
  self.assertEqual(self.client.get('/api/reports/users?filter=disabled').get_json()['rows'][0]['user_id'],'u2')


 def test_check_record_details_and_privacy_boundary(self):
  self.login()
  r=self.client.get('/api/check-records?operation=criminal&environment=preproduction&state=completed')
  self.assertEqual(r.status_code,200,r.text)
  self.assertEqual(r.get_json()['rows'],[])
  self.assertEqual(self.client.get('/api/check-records?operation=x&environment=x&state=x&page=0').status_code,400)
  self.assertEqual(self.client.get('/api/reports/users?filter=city:Bangalore').get_json()['rows'][0]['user_id'],'u1')
  self.assertEqual(self.client.get('/api/reports/users?filter=payment:sandbox').status_code,200)

if __name__=='__main__':unittest.main()
