import unittest
from unittest.mock import patch
import signzy_probe as probe


class ProbeTests(unittest.TestCase):
    def test_success_is_not_verification(self):
        result = probe.summary(200, {'resultCode': 200, 'employmentSummary': {'is_employed': False, 'date_of_exit_marked': True, 'matching_uan': 'PRIVATE'}, 'uanDetails': {'PRIVATE': {}}})
        self.assertFalse(result['automatic_verification'])
        self.assertFalse(result['is_employed'])
        self.assertNotIn('PRIVATE', str(result))

    def test_error_payload_not_disclosed(self):
        result = probe.summary(400, {'resultCode': 'PRIVATE', 'error': 'PRIVATE', 'employmentSummary': {'is_employed': True}})
        self.assertIsNone(result['is_employed'])
        self.assertNotIn('PRIVATE', str(result))

    def test_malformed_response(self):
        self.assertIsNone(probe.summary(200, ['unexpected'])['result_code'])

    def test_redirect_blocked(self):
        self.assertIsNone(probe.NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example.com'))

    def test_transport_mapping_without_network(self):
        from io import BytesIO
        response = BytesIO(b'{"resultCode":200,"employmentSummary":{"is_employed":true}}')
        response.code = 200
        with patch.object(probe.urllib.request, 'build_opener') as factory:
            factory.return_value.open.return_value = response
            result = probe.call('synthetic-test-key', '9000000000', 'AAAAA0000A')
            self.assertTrue(result['is_employed'])
            self.assertEqual(factory.return_value.open.call_count, 1)


if __name__ == '__main__':
    unittest.main()
