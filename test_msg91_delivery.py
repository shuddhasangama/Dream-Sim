"""MSG91 contract and failure tests; no real SMS sent."""
import json
import os
import unittest
from unittest import mock
from urllib.parse import urlparse, parse_qs
import auth_delivery as d

class Msg91Tests(unittest.TestCase):
    def setUp(self):
        patch=mock.patch.dict(os.environ, {'DHASHU_SMS_PROVIDER':'msg91',
            'MSG91_AUTH_KEY':'test-secret','MSG91_TEMPLATE_ID':'a'*24})
        patch.start(); self.addCleanup(patch.stop)

    def response(self, payload):
        response=mock.MagicMock()
        response.__enter__.return_value.read.return_value=json.dumps(payload).encode()
        return response

    def test_send_and_verify_contract(self):
        with mock.patch.object(d.urllib.request,'build_opener') as factory:
            factory.return_value.open.return_value=self.response({'type':'success','request_id':'request123'})
            sid=d.start('phone','+919876543210')
            req=factory.return_value.open.call_args.args[0]
            self.assertEqual(req.method,'POST')
            self.assertEqual(req.get_header('Authkey'),'test-secret')
            self.assertNotIn('test-secret',req.full_url)
            self.assertEqual(parse_qs(urlparse(req.full_url).query), {
                'mobile':['919876543210'],'template_id':['a'*24],'otp_length':['6'],'otp_expiry':['10']})
            factory.return_value.open.return_value=self.response({'type':'success','message':'OTP verified success'})
            self.assertTrue(d.check(sid,'123456'))
            req=factory.return_value.open.call_args.args[0]
            self.assertEqual(req.method,'GET')
            self.assertEqual(parse_qs(urlparse(req.full_url).query),{'mobile':['919876543210'],'otp':['123456']})

    def test_errors_and_already_used_are_not_approval(self):
        for payload in ({'type':'error','message':'OTP not match'},
                        {'type':'error','message':'OTP expired'},
                        {'type':'success','message':'Already verified'},
                        {'type':'success'}):
            with mock.patch.object(d,'_msg91_request',return_value=payload):
                self.assertFalse(d.check('msg91:919876543210:req','123456'))

    def test_failure_never_falls_back_to_twilio(self):
        with mock.patch.object(d,'_msg91_request',return_value={'type':'error','message':'private'}), mock.patch.object(d,'_post') as twilio:
            with self.assertRaises(d.DeliveryUnavailable):d.start('phone','+919876543210')
            twilio.assert_not_called()

    def test_india_validation_before_network(self):
        with mock.patch.object(d,'_msg91_request') as send:
            for phone in ('+91987654321','+9198765432100','+14155552671','+910123456789'):
                with self.assertRaises(d.DeliveryUnavailable):d.start('phone',phone)
            send.assert_not_called()

    def test_missing_key_and_unknown_provider_fail_closed(self):
        with mock.patch.dict(os.environ,{'MSG91_AUTH_KEY':''}): self.assertFalse(d.configured())
        with mock.patch.dict(os.environ,{'DHASHU_SMS_PROVIDER':'typo'}): self.assertFalse(d.configured())

    def test_network_failure_sanitized(self):
        with mock.patch.object(d.urllib.request,'build_opener') as factory:
            factory.return_value.open.side_effect=TimeoutError('secret phone otp')
            with self.assertRaises(d.DeliveryUnavailable) as caught:d.start('phone','+919876543210')
            self.assertNotIn('secret',str(caught.exception))

    def test_pending_challenge_still_uses_original_provider(self):
        with mock.patch.dict(os.environ,{'DHASHU_SMS_PROVIDER':'twilio'}), mock.patch.object(d,'_msg91_request',return_value={'type':'success','message':'OTP verified success'}):
            self.assertTrue(d.check('msg91:919876543210:req','123456'))
        with mock.patch.object(d,'_post',return_value={'status':'approved','sid':'VE'+'c'*32}):
            self.assertTrue(d.check('VE'+'c'*32,'123456'))
