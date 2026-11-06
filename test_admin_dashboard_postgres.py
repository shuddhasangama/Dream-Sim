"""Opt-in localhost-only PostgreSQL coverage; never uses the live Railway database."""
import base64
import json
import os
import time
import unittest
import uuid
from unittest.mock import patch
from cryptography.fernet import Fernet
import db
from admin_dashboard import reports,security
from admin_dashboard.manage import initialize
from admin_dashboard.app import create_app

@unittest.skipUnless(os.getenv('ADMIN_TEST_POSTGRES_URL'),'No isolated PostgreSQL test configured')
class AdminPostgresTests(unittest.TestCase):
 def setUp(self):
  import psycopg
  from psycopg import sql
  from psycopg.conninfo import conninfo_to_dict
  base=os.environ['ADMIN_TEST_POSTGRES_URL']
  if conninfo_to_dict(base).get('host')!='127.0.0.1':raise ValueError('Tests require isolated localhost PostgreSQL.')
  self.control=psycopg.connect(base,autocommit=True);self.schema='admin_test_'+uuid.uuid4().hex
  self.control.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(self.schema)))
  self.env=patch.dict(os.environ,{'DATABASE_URL':base+'?options=-csearch_path%3D'+self.schema,'ADMIN_PUBLIC_ORIGIN':'https://admin.shuddhasangama.org','ADMIN_ALLOW_HTTP':'0','ADMIN_TOTP_ENCRYPTION_KEY':Fernet.generate_key().decode()});self.env.start()
  self.c=db.get_connection();db.init_db(self.c);initialize(self.c)
  db.insert_row(self.c,'User',{'id':'sample','journey_state':'onboarding','stats_json':json.dumps({'city':'Bangalore','signup_version':3,'signup_stats_saved':True})})
  db.insert_row(self.c,'Account',{'id':'sample-a','user_id':'sample','phone':'+919000000001','auth_enabled':1,'created_at':str(int(time.time()))})
  self.secret=base64.b32encode(b'12345678901234567890').decode();self.password='Synthetic-local-test-password'
  now=int(time.time())
  with patch('time.time',return_value=now-60):security.create_identity(self.c,'office@shuddhasangama.org',self.password,self.secret,security.code(self.secret,(now-60)//30))
 def tearDown(self):
  from psycopg import sql
  self.c.close();self.env.stop();self.control.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(self.schema)));self.control.close()
 def test_login_reports_search_and_read_only(self):
  import psycopg
  client=create_app().test_client();origin='https://admin.shuddhasangama.org'
  r=client.post('/api/login',json={'email':'office@shuddhasangama.org','password':self.password,'code':security.code(self.secret,int(time.time())//30)},base_url=origin,headers={'Origin':origin})
  self.assertEqual(r.status_code,200,r.text)
  for name in ('overview','users','sessions','checks','marketing','audit'):
   r=client.get('/api/reports/'+name,base_url=origin);self.assertEqual(r.status_code,200,r.text)
  csrf=client.get('/api/session',base_url=origin).get_json()['csrf']
  r=client.post('/api/search/users',json={'q':'+919000000001'},base_url=origin,headers={'Origin':origin,'X-CSRF-Token':csrf});self.assertEqual(r.status_code,200,r.text);self.assertEqual(len(r.get_json()['rows']),1)
  r=client.post('/api/user-summary',json={'user_id':'sample'},base_url=origin,headers={'Origin':origin,'X-CSRF-Token':csrf});self.assertEqual(r.status_code,200,r.text)
  with reports.connection() as conn:
   with self.assertRaises(psycopg.errors.ReadOnlySqlTransaction):conn.execute('DELETE FROM "Account"')
  self.assertEqual(len(db.fetch_all(self.c,'Account')),1)
 def test_throttle_upsert_and_schema_idempotency(self):
  for _ in range(11):result,issue=security.login(self.c,'wrong@example.test','wrong','000000','test')
  self.assertEqual(issue,'throttled');initialize(self.c);self.assertEqual(len(db.fetch_all(self.c,'Account')),1)

if __name__=='__main__':unittest.main()
