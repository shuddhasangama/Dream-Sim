import io
import json
import unittest
from unittest.mock import patch
from signzy import digilocker_create_url as create, digilocker_eaadhaar as fetch
from signzy.client import Client,Config

class DigiLockerTests(unittest.TestCase):
    def test_callback_is_sandbox_acknowledgement_only(self):
        from flask import Flask
        import auth
        import signzy_digilocker_callback
        app=Flask(__name__);app.secret_key='synthetic-secret-with-at-least-32-characters'
        with patch.dict('os.environ',{'AUTH_ENABLED':'1','AUTH_PUBLIC_ORIGIN':'https://backend.example','SECRET_KEY':app.secret_key}),patch('auth_delivery.configured',return_value=True):
            auth.register_auth(app,lambda:None)
        signzy_digilocker_callback.register(app)
        client=app.test_client();path='/public/signzy/digilocker/callback/'+'a'*32
        self.assertEqual(client.post(path).status_code,404)
        with patch.dict('os.environ',{'SIGNZY_DIGILOCKER_SANDBOX_CALLBACK_ENABLED':'1','SIGNZY_ENV':'preproduction'}):
            result=client.post(path,json={'name':'PRIVATE PERSON','verified':True})
            self.assertEqual(result.status_code,200)
            self.assertEqual(result.json,{'received':True})
            self.assertEqual(client.post(path+'/other').status_code,403)
            self.assertEqual(client.post('/calendar/availability').status_code,403)
            self.assertEqual(client.post('/public/signzy/digilocker/callback/not-a-nonce').status_code,404)
        with patch.dict('os.environ',{'SIGNZY_DIGILOCKER_SANDBOX_CALLBACK_ENABLED':'1','SIGNZY_ENV':'production'}):
            self.assertEqual(client.post(path).status_code,404)

    def test_minimal_document_scope_and_disabled_files(self):
        p=create.payload({'callbackUrl':'https://dhashu.com/callback','internalId':'synthetic_123','serviceName':'DhaShu'})
        self.assertEqual(p['docType'],['ADHAR'])
        for key in ['getBase64Files','getEAadhaarPdf','getEAadhaarJpeg']:self.assertIs(p[key],False)
        p=fetch.payload({'requestId':'synthetic_123'})
        self.assertEqual(p,{'requestId':'synthetic_123','extraDigitalCertificateParams':'false','getEAadhaarPdf':False,'getEAadhaarJpeg':False})
        for extra in [{'getEAadhaarPdf':True},{'extraDigitalCertificateParams':True}]:
            with self.assertRaises(ValueError):fetch.payload({'requestId':'synthetic_123',**extra})

    def test_callback_and_consent_link_validation(self):
        for url in ['http://dhashu.com/callback','https://<callbackURL>.com/','https://user:password@dhashu.com/callback','https://dhashu.com/callback\n']:
            with self.assertRaises(ValueError):create.https_url(url)
        good={'result':{'requestId':'synthetic_123','url':'https://api.digitallocker.gov.in/public/oauth2/1/authorize?state=synthetic_123'}}
        self.assertTrue(create.summarize(200,good)['consent_link_received'])
        self.assertFalse(create.summarize(403,good)['consent_link_received'])
        bad={'result':{'requestId':'synthetic_123','url':'https://untrusted.example/link'}}
        self.assertFalse(create.summarize(200,bad)['consent_link_received'])

    def test_only_requested_fields_in_private_projection(self):
        body={'result':{'name':'SYNTHETIC PERSON','dob':'01/01/1990','address':'SYNTHETIC ADDRESS',
                        'uid':'PRIVATE_UID','photo':'https://example.invalid/private','x509Data':{},'aadhaarPdf':'PRIVATE_URL'}}
        self.assertEqual(set(fetch.identity_fields(body)),{'name','dob','address'})
        summary=fetch.summarize(200,body)
        self.assertTrue(summary['name_received']);self.assertFalse(summary['automatic_verification'])
        self.assertNotIn('SYNTHETIC',json.dumps(summary));self.assertNotIn('PRIVATE',json.dumps(summary))
        self.assertFalse(fetch.summarize(403,body)['name_received'])
        self.assertEqual(fetch.summarize(202,{})['outcome'],'accepted_pending_confirmation')

    def test_shared_transport_is_sandbox_single_call_with_encrypted_sink_contract(self):
        response=io.BytesIO(json.dumps({'result':{'name':'SYNTHETIC PERSON','dob':'01/01/1990','address':'PLACE'}}).encode());response.code=200
        evidence=[]
        with patch('urllib.request.build_opener') as opener:
            opener.return_value.open.return_value=response
            result=Client(Config(token='synthetic-key')).execute('digilocker_eaadhaar',{'requestId':'synthetic_123'},consent_confirmed=True,evidence_sink=evidence.append)
            self.assertEqual(opener.return_value.open.call_count,1)
            request=opener.return_value.open.call_args.args[0]
            self.assertEqual(request.full_url,'https://api-preproduction.signzy.app/api/v3/digilocker-v2/geteAadhaar')
            self.assertFalse(json.loads(request.data)['getEAadhaarPdf'])
        self.assertTrue(result['address_received']);self.assertEqual(len(evidence),1)
        self.assertNotIn('SYNTHETIC PERSON',json.dumps(result))
