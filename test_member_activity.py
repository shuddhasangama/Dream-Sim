import os
from unittest.mock import patch,Mock
import unittest
import member_activity
import test_admin_dashboard as fixtures

class ActivityTests(unittest.TestCase):
 def setUp(self):
  self.fixture=fixtures.AdminDashboardTests();self.fixture.setUp()
  self.path=self.fixture.path;self.conn=self.fixture.conn;self.now=self.fixture.now
 def tearDown(self):self.fixture.tearDown()
 def test_activity_records_real_request_once_and_failure_is_nonfatal(self):
  member_activity._recent.clear()
  original=__import__('db').get_connection
  with patch('member_activity.db.get_connection',side_effect=lambda:original(self.path)),patch('member_activity.time.time',return_value=self.now):
   member_activity.record('u1','mobile','iPhone');member_activity.record('u1','mobile','iPhone')
  r=self.conn.execute('SELECT * FROM "UserActivity" WHERE user_id=?',('u1',)).fetchone()
  self.assertEqual(r['last_seen_at'],self.now);self.assertEqual(r['platform'],'ios');self.assertEqual(r['first_seen_at'],self.now)
  with patch('member_activity.db.get_connection',side_effect=RuntimeError('unavailable')):
   member_activity.record('synthetic-missing','mobile','Android')
 def test_auth_hook_requires_authenticated_session(self):
  from flask import Flask
  import auth
  app=Flask(__name__);app.config['AUTH_ENABLED']=True
  for authenticated in (None,{'user_id':'u1'}):
   with app.test_request_context('/api/v1/me',headers={'Authorization':'Bearer '+'a'*40}),patch.dict(os.environ,{'DHASHU_ACTIVITY_ENABLED':'1'}),patch('auth.sessions.authenticate',return_value=authenticated),patch('member_activity.record') as record:
    self.assertEqual(auth.resolve(lambda:None),authenticated)
    self.assertEqual(record.call_count,1 if authenticated else 0)

if __name__=='__main__':unittest.main()
