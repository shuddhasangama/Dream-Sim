"""Offline two-step CLI integration. Synthetic provider responses, no API credits."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from cryptography.fernet import Fernet
import signzy_test
from signzy.receipts import read_private
from signzy.digilocker_eaadhaar import identity_fields

class DigiLockerFlowTests(unittest.TestCase):
    def test_create_consent_receipt_then_fetch_same_request(self):
        request_id='synthetic_session_123'
        link='https://api.digitallocker.gov.in/public/oauth2/1/authorize?state='+request_id
        bodies=[{'result':{'url':link,'requestId':request_id}},
                {'result':{'name':'SYNTHETIC PERSON','dob':'01/01/1990','address':'SYNTHETIC ADDRESS',
                           'uid':'SYNTHETIC UID','photo':'https://example.invalid/private','gender':'FEMALE','x509Data':{}}}]
        responses=[]
        for body in bodies:
            r=io.BytesIO(json.dumps(body).encode());r.code=200;responses.append(r)
        env={'SIGNZY_ENV':'preproduction','SIGNZY_TEST_API_KEY':'synthetic-api-key',
             'SIGNZY_RECEIPT_ENCRYPTION_KEY':Fernet.generate_key().decode(),
             'SIGNZY_DIGILOCKER_CALLBACK_BASE':'https://backend.example/public/signzy/digilocker/callback'}
        original=Path.cwd()
        with tempfile.TemporaryDirectory() as tmp,patch.dict(os.environ,env),patch('db.get_connection') as database,patch('urllib.request.build_opener') as opener:
            try:
                os.chdir(tmp);opener.return_value.open.side_effect=responses
                with patch('sys.argv',['signzy_test.py','digilocker_create_url']),patch('builtins.input',return_value='DhaShu'),contextlib.redirect_stdout(io.StringIO()) as create_output:
                    signzy_test.main()
                directory=Path('data/signzy-test-receipts')
                create_receipt=next(directory.glob('*.fernet.enc'))
                create_data=read_private(create_receipt)
                self.assertEqual(create_data['provider_response']['json']['result']['requestId'],request_id)
                self.assertIn(link,create_output.getvalue())
                # An incomplete human consent step must not call the provider.
                with patch('sys.argv',['signzy_test.py','digilocker_eaadhaar','--create-receipt',str(create_receipt)]),patch('builtins.input',return_value='NO'),contextlib.redirect_stdout(io.StringIO()):
                    with self.assertRaisesRegex(ValueError,'Complete consent'):signzy_test.main()
                self.assertEqual(opener.return_value.open.call_count,1)
                with patch('sys.argv',['signzy_test.py','digilocker_eaadhaar','--create-receipt',str(create_receipt)]),patch('builtins.input',return_value='YES'),contextlib.redirect_stdout(io.StringIO()) as fetched_output:
                    signzy_test.main()
                requests=[call.args[0] for call in opener.return_value.open.call_args_list]
                self.assertEqual(len(requests),2)
                self.assertEqual(json.loads(requests[1].data),{'requestId':request_id,'extraDigitalCertificateParams':'false','getEAadhaarPdf':False,'getEAadhaarJpeg':False})
                self.assertTrue(all(r.full_url.startswith('https://api-preproduction.signzy.app/') for r in requests))
                records=[read_private(f) for f in directory.glob('*.fernet.enc')]
                self.assertEqual(len(records),2)
                fetched=next(r for r in records if r['operation']=='digilocker_eaadhaar')
                fields=identity_fields(fetched['provider_response']['json'])
                self.assertEqual(set(fields),{'name','dob','address'})
                self.assertFalse(fetched['wrapper_summary']['automatic_verification'])
                for private in ['SYNTHETIC PERSON','SYNTHETIC ADDRESS','SYNTHETIC UID','synthetic-api-key']:
                    self.assertNotIn(private,fetched_output.getvalue())
                    for file in directory.iterdir():self.assertNotIn(private.encode(),file.read_bytes())
                database.assert_not_called()
            finally:os.chdir(original)
