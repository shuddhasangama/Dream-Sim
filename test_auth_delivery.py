"""Provider protocol tests: all HTTPS traffic is mocked."""
import io
import json
import os
import unittest
from unittest import mock
import urllib.error
import urllib.parse

import auth_delivery as delivery


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.env = mock.patch.dict(os.environ, {'TWILIO_ACCOUNT_SID': 'AC' + 'a' * 32,
            'TWILIO_VERIFY_SERVICE_SID': 'VA' + 'b' * 32, 'TWILIO_AUTH_TOKEN': 'test-secret'})
        self.env.start()
        self.addCleanup(self.env.stop)

    def respond(self, value):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps(value).encode()
        return response

    def test_email_and_sms_request_shape(self):
        with mock.patch.object(delivery.urllib.request, 'build_opener') as factory:
            factory.return_value.open.return_value = self.respond({'status': 'pending', 'sid': 'VE' + 'c' * 32})
            for channel, destination, expected in (('email', 'tester@example.test', 'email'), ('phone', '+919876543210', 'sms')):
                self.assertEqual(delivery.start(channel, destination), 'VE' + 'c' * 32)
                request = factory.return_value.open.call_args.args[0]
                self.assertEqual(request.full_url, 'https://verify.twilio.com/v2/Services/VA' + 'b' * 32 + '/Verifications')
                self.assertEqual(urllib.parse.parse_qs(request.data.decode()), {'To': [destination], 'Channel': [expected]})
                self.assertEqual(factory.return_value.open.call_args.kwargs['timeout'], 10)

    def test_check_requires_approved_matching_sid(self):
        with mock.patch.object(delivery, '_post') as post:
            post.return_value = {'status': 'approved', 'sid': 'VE' + 'c' * 32}
            self.assertTrue(delivery.check('VE' + 'c' * 32, '123456'))
            post.assert_called_with('VerificationCheck', {'VerificationSid': 'VE' + 'c' * 32, 'Code': '123456'})
            post.return_value = {'status': 'pending', 'sid': 'VE' + 'c' * 32}
            self.assertFalse(delivery.check('VE' + 'c' * 32, '123456'))
            post.return_value = {'status': 'approved', 'sid': 'VE' + 'd' * 32}
            self.assertFalse(delivery.check('VE' + 'c' * 32, '123456'))

    def test_provider_failures_do_not_expose_payload(self):
        with mock.patch.object(delivery.urllib.request, 'build_opener') as factory:
            for error in (TimeoutError('sensitive'), urllib.error.URLError('sensitive'),
                          urllib.error.HTTPError('https://verify.twilio.com', 500, 'sensitive', {}, io.BytesIO(b'secret'))):
                factory.return_value.open.side_effect = error
                with self.assertRaises(delivery.DeliveryUnavailable) as caught:
                    delivery.start('email', 'tester@example.test')
                self.assertNotIn('sensitive', str(caught.exception))

    def test_no_configuration_cannot_send(self):
        with mock.patch.dict(os.environ, {'TWILIO_AUTH_TOKEN': ''}), mock.patch.object(delivery.urllib.request, 'build_opener') as factory:
            with self.assertRaises(delivery.DeliveryUnavailable):
                delivery.start('email', 'tester@example.test')
            factory.assert_not_called()

    def test_redirects_are_not_followed(self):
        self.assertIsNone(delivery.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://other.test'))
