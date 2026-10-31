import io
import json
import unittest
from unittest.mock import patch
from signzy import individual_search, uan_passbook
from signzy.client import Client, Config

class AdditionalApiTests(unittest.TestCase):
    def test_search_validation(self):
        self.assertEqual(individual_search.payload({'name': ' Test ', 'address': 'Somewhere', 'matchType': 'Exact'}),
                         {'name': 'Test', 'address': 'Somewhere', 'matchType': 'exact'})
        for extra in ({'name': ''}, {'address': ''}, {'matchType': 'fuzzy'}, {'type': 'accused'},
                      {'caseCategory': 'other'}, {'dob': '2000-01-01'}, {'unknown': 'x'}):
            with self.assertRaises(ValueError):
                individual_search.payload(dict(name='Test', address='Somewhere', matchType='exact') | extra)

    def test_passbook_validation(self):
        values = {'uan': '123456789012', 'consentFlag': 'Y'}
        self.assertEqual(uan_passbook.payload(values), values | {'ttl': 0})
        for extra in ({'uan': '123'}, {'consentFlag': 'N'}, {'ttl': True}, {'ttl': 31},
                      {'ttl': -1}, {'callBackUrl': 'https://example.org'}, {'cutOffTime': '0'}):
            with self.assertRaises(ValueError):
                uan_passbook.payload(values | extra)

    def test_transport_paths_and_private_evidence(self):
        for operation, values, suffix in (
            ('individual_search', {'name': 'PRIVATE NAME', 'address': 'PRIVATE ADDRESS', 'matchType': 'exact'}, '/individual/search'),
            ('uan_passbook', {'uan': '123456789012', 'consentFlag': 'Y'}, '/underwriting/uan-passbook-without-otp')):
            for status, body in ((200, {'result': {'name': 'PRIVATE NAME', 'uan': '123456789012', 'employers': []}}),
                                 (403, {'message': 'You cannot consume this service'})):
                response = io.BytesIO(json.dumps(body).encode()); response.code = status
                evidence = []
                with patch('urllib.request.build_opener') as opener:
                    opener.return_value.open.return_value = response
                    summary = Client(Config(token='synthetic')).execute(operation, values,
                        consent_confirmed=True, evidence_sink=evidence.append)
                    request = opener.return_value.open.call_args.args[0]
                    self.assertEqual(request.full_url, 'https://api-preproduction.signzy.app/api/v3' + suffix)
                    self.assertEqual(opener.return_value.open.call_count, 1)
                self.assertEqual(evidence[0]['provider_response']['json'], body)
                self.assertNotIn('PRIVATE', json.dumps(summary))
                self.assertNotIn('123456789012', json.dumps(summary))
                self.assertFalse(summary['automatic_verification'])
                if status == 403:
                    self.assertEqual(summary['error_code'], 'access_denied')

    def test_async_and_unknown_response_not_completed(self):
        self.assertEqual(uan_passbook.summarize(202, {})['outcome'], 'accepted_pending_confirmation')
        self.assertFalse(uan_passbook.summarize(200, {'requestId': 'test'})['passbook_data_present'])
        self.assertFalse(uan_passbook.summarize(200, {'result': []})['passbook_data_present'])
        self.assertEqual(individual_search.summarize(200, [])['court_clearance'], 'not_evaluated')
