"""Regression tests for observed envelopes, saved-receipt repair and original portrait cache."""
import io
import json
import unittest
import uuid
from unittest.mock import patch
from PIL import Image
import db
import bgv_app
import bgv_bundle
import digilocker_photo_cache as photos
from signzy import individual_result as court,fir_result as fir
import test_bgv_bundle as fixtures

class LegalShapeTests(unittest.TestCase):
    def test_http_200_court_pending_never_becomes_empty_completed_result(self):
        body={'status':0,'message':'Process pending.','cases':[]}
        for value in (body,{'result':body}):
            result=court.summarize(200,value)
            self.assertEqual(result['outcome'],'accepted_pending_confirmation')
            self.assertFalse(result['processing_complete']);self.assertIsNone(result['cases_returned'])
    def test_nested_fir_and_counter_disagreement_remain_candidates(self):
        body={'result':{'status':1,'message':'Processing done','cases':[{},{}],'numResults':2,'total':0}}
        result=fir.summarize(200,body)
        self.assertTrue(result['processing_complete']);self.assertEqual(result['candidates_returned'],2)
        self.assertEqual(result['numresults_reported'],2);self.assertTrue(result['provider_count_discrepancy'])
        self.assertFalse(result['automatic_verification']);self.assertEqual(result['fir_clearance'],'not_evaluated')
    def test_ambiguous_envelope_unknown_status_and_nonrecords_fail_closed(self):
        for body in ({'result':{'status':1,'message':'Processing done','cases':[]},'cases':[{}]},
                     {'status':0,'message':'Unexpected','cases':[]},{'status':True,'message':'Processing done','cases':[]},
                     {'status':1,'message':'Processing done','cases':['invalid']}):
            self.assertFalse(court.summarize(200,body)['processing_complete'])
            self.assertFalse(fir.summarize(200,body)['processing_complete'])
    def test_empty_completed_result_is_distinct_from_pending(self):
        result=court.summarize(200,{'status':1,'cases':[]})
        self.assertTrue(result['processing_complete']);self.assertEqual(result['cases_returned'],0)
        self.assertIn('no candidate records',bgv_app.public_message('individual_result','needs_review',result))

class RepairAndPhotoTests(unittest.TestCase):
    setUp=fixtures.BundleTests.setUp
    session=fixtures.BundleTests.session
    def request(self,op,body,state='needs_review'):
        rid=str(uuid.uuid4());evidence={'receipt_id':str(uuid.uuid4()),'provider_response':{'http_status':200,'json':body}}
        encrypted=self.protection.seal(evidence)
        self.conn.execute('INSERT INTO "BgvRequest" (id,user_id,operation,environment,state,protected_input,protected_result,summary_json,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)',
            (rid,'u1',op,'preproduction',state,self.protection.seal({'inputs':{},'declared':{}}),encrypted,json.dumps({'fields':{},'message':'Review your declared details'}),bgv_app.stamp(),bgv_app.stamp()));self.conn.commit()
        return rid,encrypted
    def test_repair_is_idempotent_no_vendor_calls_and_preserves_raw_evidence(self):
        rid,raw=self.request('individual_result',{'status':0,'message':'Process pending.','cases':[]})
        fid,_=self.request('fir_result',{'result':{'status':1,'message':'Processing done','cases':[{}],'numResults':1,'total':0}})
        with patch('bgv_app.Client.execute') as provider:
            self.assertEqual(bgv_app.reproject_saved(self.conn,'u1'),2)
            self.assertEqual(bgv_app.reproject_saved(self.conn,'u1'),0)
            provider.assert_not_called()
        row=db.fetch_one(self.conn,'BgvRequest',id=rid)
        self.assertEqual(row['state'],'pending');self.assertEqual(row['protected_result'],raw)
        self.assertTrue(bgv_app.view(self.conn,'u1')['results'])
        self.assertIn('previous possible-match',json.loads(db.fetch_one(self.conn,'BgvRequest',id=fid)['summary_json'])['message'])
        self.assertEqual(db.fetch_all(self.conn,'BgvAttempt'),[])
        self.assertEqual(db.fetch_one(self.conn,'User',id='u1')['bgv_status'],'declared')
    def test_repair_never_touches_other_users_or_unknown_submissions(self):
        rid,raw=self.request('individual_result',{'cases':[]},'outcome_unknown')
        self.assertEqual(bgv_app.reproject_saved(self.conn,'u2'),0)
        self.assertEqual(bgv_app.reproject_saved(self.conn,'u1'),0)
        self.assertEqual(db.fetch_one(self.conn,'BgvRequest',id=rid)['state'],'outcome_unknown')
    def test_original_portrait_is_downloaded_once_encrypted_and_not_exposed(self):
        self.session();url='https://persist.wayne-rta.com/api/files/synthetic/download/portrait.jpeg'
        self.conn.execute('UPDATE "DigiLockerSession" SET protected_photo=?',(self.protection.seal({'url':url}),));self.conn.commit()
        raw=io.BytesIO();Image.new('RGB',(32,40),'red').save(raw,'JPEG');image=raw.getvalue()
        class Response(io.BytesIO):status=200
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.return_value=Response(image)
            self.assertTrue(photos.cache(self.conn,db.fetch_one(self.conn,'DigiLockerSession',id=self.sid)))
            self.assertFalse(photos.cache(self.conn,db.fetch_one(self.conn,'DigiLockerSession',id=self.sid)))
            self.assertEqual(opener.return_value.open.call_count,1)
        value=db.fetch_one(self.conn,'DigiLockerSession',id=self.sid)['protected_photo']
        self.assertNotIn(url,value)
        private=self.protection.open(value);self.assertEqual(private['download_state'],'received')
        view=bgv_bundle.view(self.conn,'u1');self.assertTrue(view['photo_sources']['aadhaar_image_available'])
        self.assertFalse(view['photo_sources']['pan_photo_available'])
        self.assertNotIn(private['image_base64'],json.dumps(view));self.assertNotIn(url,json.dumps(view))
        private['image_expires_at']='2000-01-01T00:00:00+00:00'
        self.conn.execute('UPDATE "DigiLockerSession" SET protected_photo=?',(self.protection.seal(private),));self.conn.commit()
        self.assertEqual(photos.purge_expired(self.conn),1)
        self.assertFalse(bgv_bundle.view(self.conn,'u1')['photo_sources']['aadhaar_image_available'])
        self.assertEqual(photos.purge_expired(self.conn),0)
    def test_invalid_and_redirected_sources_are_not_silently_used(self):
        with patch('urllib.request.build_opener') as opener:
            with self.assertRaises(ValueError):photos.download('https://untrusted.example/photo.jpeg')
            opener.assert_not_called()
        self.session();self.conn.execute('UPDATE "DigiLockerSession" SET protected_photo=?',(self.protection.seal({'url':'https://persist.wayne-rta.com/api/files/ref/download/photo.jpeg'}),));self.conn.commit()
        with patch.object(photos,'download',side_effect=ValueError('unavailable')) as download:
            self.assertFalse(photos.cache(self.conn,db.fetch_one(self.conn,'DigiLockerSession',id=self.sid)))
            self.assertFalse(photos.cache(self.conn,db.fetch_one(self.conn,'DigiLockerSession',id=self.sid)))
            self.assertEqual(download.call_count,1)
