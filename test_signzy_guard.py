import io, json, sqlite3, unittest
from pathlib import Path
from unittest.mock import Mock, patch
import signzy_guard as guard
from signzy.client import Config, Client
from signzy.errors import classify
from test_bgv_app import BgvAppTests

class GuardTests(unittest.TestCase):
 def setUp(self):
  self.conn=sqlite3.connect(':memory:');self.conn.row_factory=sqlite3.Row
  schema=Path('schema.sql').read_text(encoding='utf-8');self.conn.executescript(schema[schema.index('CREATE TABLE IF NOT EXISTS "SignzyGuard"'):]);self.cfg=Config(token='synthetic')
 def tearDown(self): self.conn.close()
 def test_wallet_reason_embedded_and_paused_without_network(self):
  summary=classify(200,{'error':{'status':'400','reason':'Insufficient wallet balance','message':'ERROR'}})
  self.assertEqual(summary['error_code'],'credits_unavailable');guard.record(self.conn,self.cfg,'fir_search',summary)
  client=Mock();evidence=[]
  result=guard.execute(self.conn,self.cfg,client,'employment_history',{},evidence_sink=evidence.append)
  client.execute.assert_not_called();self.assertFalse(result['provider_request_sent']);self.assertFalse(evidence[0]['provider_request_sent'])
  self.assertIsNone(guard.blocked(self.conn,Config(token='different'),'fir_search'))
  self.assertIsNone(guard.blocked(self.conn,Config('production','synthetic'),'fir_search'))
  guard.resume(self.conn,self.cfg,'*','Wallet reconciled')
  self.assertIsNone(guard.blocked(self.conn,self.cfg,'fir_search'))
 def test_error_envelope_overrides_success_and_malformed_auth_pauses(self):
  payload={'result':{'verified':True,'matchPercentage':'99.00%'},'error':{'status':402,'reason':'Wallet empty'}}
  for status,raw in [(200,json.dumps(payload).encode()),(401,b'not JSON')]:
   response=io.BytesIO(raw);response.code=status;evidence=[]
   with patch('urllib.request.build_opener') as factory:
    factory.return_value.open.return_value=response
    result=guard.execute(self.conn,self.cfg,Client(self.cfg),'face_match',{'firstImage':'https://example.com/a.jpg','secondImage':'https://example.com/b.jpg','threshold':0.5},consent_confirmed=True,evidence_sink=evidence.append)
   self.assertNotEqual(result.get('face_match_passed'),True)
   self.assertEqual(result['error_code'],'credits_unavailable' if status==200 else 'authentication_failed')
   self.assertTrue(guard.blocked(self.conn,self.cfg,'employment_history'))
   self.assertEqual(len(evidence),1)
   guard.resume(self.conn,self.cfg,'*','Synthetic recovery')
 def test_string_error_is_not_success(self):
  self.assertEqual(classify(200,{'error':'Unexpected provider problem'})['error_code'],'provider_error')
 def test_scope_and_temporary_pauses(self):
  guard.record(self.conn,self.cfg,'fir_search',classify(403,{}))
  self.assertTrue(guard.blocked(self.conn,self.cfg,'fir_search'));self.assertIsNone(guard.blocked(self.conn,self.cfg,'individual_search'))
  with patch('signzy_guard.time.time',return_value=1000):guard.record(self.conn,self.cfg,'individual_search',classify(429,{}))
  with patch('signzy_guard.time.time',return_value=1061):self.assertIsNone(guard.blocked(self.conn,self.cfg,'individual_search'))
 def test_no_record_not_clearance_and_timeout_not_replayed(self):
  self.assertEqual(classify(404,{'error':{'reason':'No record(s) found'}})['error_code'],'no_records_found')
  guard.record(self.conn,self.cfg,'fir_result',{'error_code':'network_error_outcome_unknown'})
  self.assertIsNone(guard.blocked(self.conn,self.cfg,'fir_result'))
  self.assertFalse(classify(500,{})['retry_automatically'])

class WorkerGuardTests(BgvAppTests):
 def test_wallet_preserves_unsent_queue_and_resume_only_unsent(self):
  import bgv_app
  first=self.body();second=self.body();bgv_app.submit(self.conn,'u1',first);bgv_app.submit(self.conn,'u2',second)
  self.run_response(200,{'error':{'reason':'Wallet empty','status':402}})
  self.assertFalse(bgv_app.work_one(self.conn))
  self.assertEqual(self.conn.execute('SELECT COUNT(*) FROM "BgvRequest" WHERE state="queued"').fetchone()[0],1)
  failed=self.conn.execute('SELECT id FROM "BgvRequest" WHERE state="unavailable"').fetchone()[0]
  guard.resume(self.conn,bgv_app.config(),'*','Top up confirmed')
  self.run_response()
  self.assertEqual(self.conn.execute('SELECT state FROM "BgvRequest" WHERE id=?',(failed,)).fetchone()[0],'unavailable')
 def test_202_error_is_not_pending(self):
  import bgv_app
  bgv_app.submit(self.conn,'u1',self.body());self.run_response(202,{'error':{'reason':'Insufficient credits','status':402}})
  self.assertEqual(bgv_app.view(self.conn,'u1')['results'][0]['state'],'unavailable')

if __name__=='__main__':unittest.main()
