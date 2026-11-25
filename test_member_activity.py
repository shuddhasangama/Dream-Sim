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
 def test_last_seen_is_written_at_most_once_per_interval(self):
  member_activity._recent.clear()
  original=__import__('db').get_connection
  writes=[]
  def connect():
   conn=original(self.path);conn.set_trace_callback(lambda sql:writes.append(sql) if 'UserActivity' in sql else None);return conn
  def last_seen():return self.conn.execute('SELECT last_seen_at FROM "UserActivity" WHERE user_id=?',('u2',)).fetchone()['last_seen_at']
  with patch.dict(os.environ,{'DHASHU_LAST_SEEN_INTERVAL':'300'}),patch('member_activity.db.get_connection',side_effect=connect):
   with patch('member_activity.time.time',return_value=self.now):member_activity.record('u2','mobile','Android')
   self.assertEqual(last_seen(),self.now);writes.clear()
   for offset in (1,60,299):                      # same process: skipped in memory, no SQL at all
    with patch('member_activity.time.time',return_value=self.now+offset):member_activity.record('u2','mobile','Android')
   self.assertEqual(writes,[]);self.assertEqual(last_seen(),self.now)
   member_activity._recent.clear()                # another process/replica: the SQL guard holds
   with patch('member_activity.time.time',return_value=self.now+120):member_activity.record('u2','mobile','Android')
   self.assertEqual(last_seen(),self.now)
   # That process remembers +120 in memory, so its next write is due at +420.
   with patch('member_activity.time.time',return_value=self.now+300):member_activity.record('u2','mobile','Android')
   self.assertEqual(last_seen(),self.now)
   with patch('member_activity.time.time',return_value=self.now+420):member_activity.record('u2','mobile','Android')
   self.assertEqual(last_seen(),self.now+420)      # interval elapsed: written again
 def test_interval_setting_is_clamped(self):
  for value,expected in (('300',300),('5',60),('99999',3600),('abc',300)):
   with patch.dict(os.environ,{'DHASHU_LAST_SEEN_INTERVAL':value}):self.assertEqual(member_activity.interval(),expected)
  with patch.dict(os.environ,{},clear=False):
   os.environ.pop('DHASHU_LAST_SEEN_INTERVAL',None);self.assertEqual(member_activity.interval(),300)
 def test_auth_hook_requires_authenticated_session(self):
  from flask import Flask
  import auth
  app=Flask(__name__);app.config['AUTH_ENABLED']=True
  for authenticated in (None,{'user_id':'u1'}):
   with app.test_request_context('/api/v1/me',headers={'Authorization':'Bearer '+'a'*40}),patch.dict(os.environ,{'DHASHU_ACTIVITY_ENABLED':'1'}),patch('auth.sessions.authenticate',return_value=authenticated),patch('member_activity.record') as record:
    self.assertEqual(auth.resolve(lambda:None),authenticated)
    self.assertEqual(record.call_count,1 if authenticated else 0)

if __name__=='__main__':unittest.main()
