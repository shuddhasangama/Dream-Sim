import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import signzy_test
from signzy import fir_search, fir_result
from signzy.client import Client, Config


class FirTests(unittest.TestCase):
    def test_payloads(self):
        self.assertEqual(fir_search.payload(dict(name=' Test ', address='Place', matchType='possible')),
                         dict(name='Test', address='Place', matchType='possible'))
        for values in ({}, dict(name='Test', address='Place', matchType='exact/possible'),
                       dict(name='Test', address='Place', matchType='exact', caseCategory='civil')):
            with self.assertRaises(ValueError):
                fir_search.payload(values)
        self.assertEqual(fir_result.payload({'verifyId':'synthetic123'}), {'verifyId':'synthetic123'})
        with self.assertRaises(ValueError):
            fir_result.payload({'searchId':'synthetic123'})

    def test_summaries(self):
        self.assertTrue(fir_search.summarize(200, {'searchId':'synthetic123'})['search_id_received'])
        sample={'status':1,'message':'Processing done','cases':[{'name':'PRIVATE NAME'}], 'numresults':1}
        s=fir_result.summarize(200,sample)
        self.assertEqual(s['candidates_returned'],1)
        self.assertNotIn('PRIVATE',json.dumps(s))
        self.assertFalse(s['automatic_verification'])
        self.assertEqual(s['fir_clearance'],'not_evaluated')
        self.assertEqual(fir_result.summarize(200,dict(sample,cases=[],numresults=0))['candidates_returned'],0)
        self.assertEqual(fir_result.summarize(202,{})['outcome'],'accepted_pending_confirmation')
        for b in ({},dict(sample,status=0),dict(sample,cases=[None]),dict(sample,message='Unknown')):
            self.assertFalse(fir_result.summarize(200,b)['processing_complete'])

    def test_transport_and_errors(self):
        for op,values,path in [('fir_search',dict(name='PRIVATE NAME',address='PRIVATE ADDRESS',matchType='possible'),'/fir/search'),
                               ('fir_result',{'verifyId':'synthetic123'},'/fir/result')]:
            for status in (200,403):
                body={'searchId':'synthetic123'} if status==200 else {'message':'Access denied'}
                response=io.BytesIO(json.dumps(body).encode());response.code=status
                evidence=[]
                with patch('urllib.request.build_opener') as opener:
                    opener.return_value.open.return_value=response
                    s=Client(Config(token='synthetic')).execute(op,values,consent_confirmed=True,evidence_sink=evidence.append)
                    self.assertTrue(opener.return_value.open.call_args.args[0].full_url.endswith(path))
                    self.assertEqual(opener.return_value.open.call_count,1)
                self.assertEqual(evidence[0]['provider_response']['json'],body)
                self.assertNotIn('PRIVATE',json.dumps(s))
                if status==403:self.assertEqual(s['error_code'],'access_denied')

    def test_cli_result_maps_search_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            original=os.getcwd()
            try:
                os.chdir(tmp)
                prior={'operation':'fir_search','environment':'preproduction','receipt_id':'parent',
                       'provider_response':{'http_status':200,'json':{'searchId':'synthetic123'}}}
                with patch('sys.argv',['signzy_test.py','fir_result','--search-receipt','private.enc']), \
                     patch('signzy.receipts.read_private',return_value=prior), \
                     patch.object(signzy_test.Config,'from_env',return_value=Config(token='synthetic')), \
                     patch.object(signzy_test,'ReceiptStore'),patch.object(signzy_test,'Client') as client, \
                     contextlib.redirect_stdout(io.StringIO()):
                    client.return_value.execute.return_value={'receipt_id':'child'}
                    signzy_test.main()
                    self.assertEqual(client.return_value.execute.call_args.args,('fir_result',{'verifyId':'synthetic123'}))
                s=json.loads(next(Path('data/signzy-test-receipts').glob('*.summary.json')).read_text())
                self.assertEqual(s['source_search_receipt_id'],'parent')
            finally:os.chdir(original)
