import json
import unittest
from datetime import datetime,timezone,timedelta
from verification_progress import record_dates,request_progress,stalled
from bgv_result_policy import employment

class ProgressTests(unittest.TestCase):
    def test_no_declaration_is_not_a_mismatch_or_verified(self):
        state,data=employment({'employmentSummary':{'recent_employer_data':{'establishment_name':'Example'}}},
            {'result_code':200,'is_employed':True},'unverified',False)
        self.assertEqual(state,'record_available')
        self.assertFalse(data['employment_record']['current_employment_confirmed'])

    def test_dates_are_stable_and_only_verified_fields_receive_dates(self):
        public={'fields':{'employer':'verified','dob':'unverified'}}
        record_dates(public,'partially_verified','2026-11-15T00:00:00+00:00')
        record_dates(public,'partially_verified','2026-11-16T00:00:00+00:00')
        self.assertNotIn('verified_at',public)
        self.assertEqual(public['field_verified_at'],{'employer':'2026-11-15T00:00:00+00:00'})
        public['fields']['employer']='unverified';record_dates(public,'unverified','later')
        self.assertEqual(public['field_verified_at'],{})

    def test_stalled_processing_has_safe_recovery_without_retry(self):
        row={'state':'processing','updated_at':(datetime.now(timezone.utc)-timedelta(minutes=11)).isoformat(),'summary_json':'{}'}
        result=request_progress(row,None)
        self.assertTrue(result['recovery_required']);self.assertFalse(result['can_resubmit'])
        self.assertIsNone(result['verified_at'])
        row['state']='verified';self.assertFalse(stalled(row))

    def test_http_success_does_not_supply_verification_date(self):
        class Store:
            def open(self,value):return {'finished_at_utc':'2026-11-15T00:00:00+00:00'}
        row={'state':'needs_review','summary_json':'{}','protected_result':'encrypted'}
        result=request_progress(row,Store())
        self.assertTrue(result['received_at']);self.assertIsNone(result['verified_at'])
