import io
import json
import unittest
import urllib.error
from unittest.mock import patch
from signzy.client import Client, Config
from signzy import pan_extensive


class SignzyClientTests(unittest.TestCase):
    def test_environment_credentials_do_not_fallback(self):
        with patch.dict('os.environ', {'SIGNZY_ENV': 'production', 'SIGNZY_TEST_API_KEY': 'test'}, clear=True):
            self.assertEqual(Config.from_env().token, '')
            with self.assertRaises(ValueError):
                Client(Config.from_env())

    def test_disabled_production(self):
        with self.assertRaises(ValueError):
            Client(Config('production', 'synthetic'))

    def test_unknown_environment(self):
        with self.assertRaises(ValueError):
            Client(Config('typo', 'synthetic'))

    def test_optional_boolean(self):
        self.assertEqual(pan_extensive.payload({'panNumber': 'aaaaa0000a'}), {'panNumber': 'AAAAA0000A'})
        with self.assertRaises(ValueError):
            pan_extensive.payload({'panNumber': 'AAAAA0000A', 'getStatusInfo': 'true'})

    def test_no_consent_no_request(self):
        with patch('urllib.request.build_opener') as factory:
            with self.assertRaises(ValueError):
                Client(Config(token='synthetic')).execute('pan_extensive', {})
            factory.assert_not_called()

    def test_exact_environment_urls_and_redaction(self):
        for environment, host in [('preproduction', 'api-preproduction.signzy.app'), ('production', 'api.signzy.app')]:
            response = io.BytesIO(b'{"name":"PRIVATE","dob":"PRIVATE","error":"PRIVATE"}')
            response.code = 200
            with patch('urllib.request.build_opener') as factory:
                factory.return_value.open.return_value = response
                receipt = Client(Config(environment, 'synthetic', production_enabled=True)).execute(
                    'pan_extensive', {'panNumber': 'AAAAA0000A', 'getStatusInfo': False}, consent_confirmed=True)
                request = factory.return_value.open.call_args.args[0]
                self.assertEqual(request.full_url, 'https://' + host + '/api/v3/panextensive')
                self.assertFalse(json.loads(request.data)['getStatusInfo'])
                self.assertNotIn('PRIVATE', str(receipt))
                self.assertEqual(receipt['name_match'], 'not_evaluated')

    def test_timeout_not_retried(self):
        with patch('urllib.request.build_opener') as factory:
            factory.return_value.open.side_effect = TimeoutError()
            receipt = Client(Config(token='synthetic')).execute('pan_extensive', {'panNumber': 'AAAAA0000A'}, consent_confirmed=True)
            self.assertEqual(receipt['outcome'], 'transport_error_outcome_unknown')
            self.assertEqual(factory.return_value.open.call_count, 1)

    def test_reject_unknown_operations_and_fields(self):
        client = Client(Config(token='synthetic'))
        with self.assertRaises(ValueError):
            client.execute('arbitrary_url', {}, consent_confirmed=True)
        with self.assertRaises(ValueError):
            client.execute('pan_extensive', {'panNumber': 'AAAAA0000A', 'url': 'https://example.com'}, consent_confirmed=True)

    def test_repr_hides_token(self):
        self.assertNotIn('secret-test', repr(Config(token='secret-test')))

    def test_pan_runner_only_prompts_for_pan(self):
        import signzy_test
        with patch('sys.argv', ['signzy_test.py', 'pan_extensive']), \
             patch.object(signzy_test.Config, 'from_env', return_value=Config(token='synthetic')), \
             patch.object(signzy_test, 'Client') as factory, \
             patch.object(signzy_test.getpass, 'getpass', return_value='AAAAA0000A') as prompt, \
             patch('builtins.input', side_effect=AssertionError('Unexpected extra prompt')), \
             patch.object(signzy_test, 'Path'), patch.object(signzy_test, 'ReceiptStore'), patch('builtins.print'):
            factory.return_value.execute.return_value = {}
            signzy_test.main()
            prompt.assert_called_once()
            factory.return_value.execute.assert_called_once_with('pan_extensive',
                {'panNumber': 'AAAAA0000A', 'getStatusInfo': True}, consent_confirmed=True, evidence_sink=unittest.mock.ANY)


if __name__ == '__main__':
    unittest.main()
