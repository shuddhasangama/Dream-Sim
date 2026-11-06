import copy,json,unittest,uuid
from unittest.mock import patch
import db,bgv_app,bgv_bundle,employment_lookup
from test_bgv_bundle import BundleTests

class EmploymentLookupTests(unittest.TestCase):
    def body(self):
        return {'result':[{'name':'SYNTHETIC PERSON','establishmentName':'Synthetic Ltd','dateOfJoining':'17-JAN-2022','dateOfExit':''}]}
    def test_matching_open_record_is_history_not_current_proof(self):
        state,extra=employment_lookup.assess(self.body(),{'name':'synthetic person','employer':'Synthetic Ltd'})
        self.assertEqual(state,'history_available');self.assertFalse(extra['employment_record']['current_employment_confirmed'])
        self.assertIn('No exit is recorded',extra['message'])
    def test_wrong_employee_cannot_match_father_or_leak_employer(self):
        body=self.body();body['result'][0].update(name='Other Person',fatherOrHusbandName='SYNTHETIC PERSON')
        state,extra=employment_lookup.assess(body,{'name':'SYNTHETIC PERSON','employer':'Synthetic Ltd'})
        self.assertEqual(state,'employment_mismatch');self.assertNotIn('employment_record',extra);self.assertNotIn('Synthetic Ltd',extra['message'])
    def test_historical_and_invalid_dates(self):
        body=self.body();body['result'][0]['dateOfExit']='14-JAN-2023'
        state,extra=employment_lookup.assess(body,{'name':'SYNTHETIC PERSON','employer':'Synthetic Ltd'})
        self.assertEqual(state,'history_available');self.assertEqual(extra['employment_record']['date_of_exit'],'2023-01-14')
        body['result'][0]['dateOfExit']='14-JAN-2020'
        self.assertEqual(employment_lookup.assess(body,{'name':'SYNTHETIC PERSON'})[0],'needs_review')
        self.assertEqual(employment_lookup.assess({'result':[]},{})[0],'not_confirmed')

class EmploymentWorkflowTests(BundleTests):
    def test_pan_only_history_call_and_saved_projection(self):
        self.session();bgv_bundle.schedule(self.conn)
        details_id=bgv_bundle.request_id(self.sid,'digilocker_details')
        evidence={'operation':'digilocker_details','provider_response':{'http_status':200,'json':self.details()}}
        self.conn.execute('UPDATE "BgvRequest" SET state=?,protected_result=? WHERE id=?',('needs_review',self.protection.seal(evidence),details_id));self.conn.commit()
        bgv_bundle.schedule(self.conn)
        row=db.fetch_all(self.conn,'BgvRequest',operation='current_employer')[0]
        self.conn.execute('UPDATE "BgvRequest" SET state=? WHERE operation!=?',('outcome_unknown','current_employer'));self.conn.commit()
        calls=[]
        def execute(op,values,**kw):
            calls.append((op,values));body={'result':[{'name':'SYNTHETIC PERSON','establishmentName':'Synthetic Ltd','dateOfJoining':'17-JAN-2022','dateOfExit':''}]}
            from signzy.client import OPERATIONS
            summary={'http_status':200,**OPERATIONS[op].summarize(200,body)}
            kw['evidence_sink']({'operation':op,'receipt_id':uuid.uuid4().hex,'provider_response':{'http_status':200,'json':body},'wrapper_summary':summary})
            return summary
        with patch('bgv_app.Client.execute',side_effect=execute):
            self.assertTrue(bgv_app.work_one(self.conn));bgv_bundle.schedule(self.conn)
        self.assertEqual(calls,[('employment_history',{'pan':'ABCDE1234F'})])
        saved=db.fetch_one(self.conn,'BgvRequest',id=row['id']);self.assertEqual(saved['state'],'history_available')
        self.assertEqual(bgv_app.reproject_saved(self.conn,'u1'),0)
        bgv_bundle.schedule(self.conn);self.assertEqual(len(db.fetch_all(self.conn,'BgvRequest',operation='current_employer')),1)
    def test_only_verified_account_mobile_is_fallback(self):
        identity={'name':'SYNTHETIC PERSON'}
        self.assertIsNone(employment_lookup.inputs(self.conn,'u1',identity,None))
        db.insert_row(self.conn,'Account',{'id':'account','user_id':'u1','auth_enabled':1,'verified_phone':1,'phone':'+919000000001','created_at':'0'})
        self.assertEqual(employment_lookup.inputs(self.conn,'u1',identity,None),{'mobile':'9000000001'})
        details={'name':'SYNTHETIC PERSON','pan':'ABCDE1234F'}
        self.assertEqual(employment_lookup.inputs(self.conn,'u1',identity,details),{'pan':'ABCDE1234F'})
        details['name']='Other Person'
        self.assertEqual(employment_lookup.inputs(self.conn,'u1',identity,details),{'mobile':'9000000001'})
