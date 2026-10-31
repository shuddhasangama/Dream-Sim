import io
import json
import unittest
from unittest.mock import patch
from signzy import employment_history
from signzy.client import Client, Config, OPERATIONS


class EmploymentHistoryTests(unittest.TestCase):
    def test_input_contract(self):
        self.assertIs(OPERATIONS['employment_history'], employment_history)
        self.assertEqual(employment_history.payload({'pan': ' aaapa0000a '}),
                         dict(pan='AAAPA0000A', mobile='', uan='', dob='', employeeName=''))
        for values in ({}, {'uan': '123'}, {'mobile': 'bad'}, {'pan': 'bad'},
                       {'uan': '123456789012', 'unknown': ''}, {'uan': 123456789012}):
            with self.assertRaises(ValueError):
                employment_history.payload(values)

    def test_response_privacy_and_limitations(self):
        body = {'result': [{'establishmentName': 'PRIVATE EMPLOYER', 'name': 'PRIVATE NAME',
                            'uan': '123456789012', 'dateOfExit': '30-SEP-2021'}],
                'additionalDetails': {'limitedOutput': True, 'uanDetails': [{'private': 'data'}]}}
        summary = employment_history.summarize(200, body)
        self.assertEqual(summary['employment_records_returned'], 1)
        self.assertTrue(summary['limited_output'])
        self.assertFalse(summary['automatic_verification'])
        self.assertNotIn('PRIVATE', json.dumps(summary))
        self.assertNotIn('123456789012', json.dumps(summary))
        self.assertEqual(summary['employment_history_verification'], 'not_evaluated')
        self.assertEqual(employment_history.summarize(200, {'result': []})['employment_records_returned'], 0)

    def test_unknown_and_pending(self):
        for body in ({}, {'result': {}}, {'result': [None]}, {'result': [{}]}):
            self.assertEqual(employment_history.summarize(200, body)['outcome'],
                             'response_received_contract_review_required')
        self.assertEqual(employment_history.summarize(202, {})['outcome'], 'accepted_pending_confirmation')
        self.assertIsNone(employment_history.summarize(403, {'result': []})['employment_records_returned'])

    def test_transport_preserves_evidence_and_denial(self):
        for status, body in [(200, {'result': [{'establishmentName': 'PRIVATE EMPLOYER'}]}),
                             (403, {'message': 'You cannot consume this service'})]:
            response = io.BytesIO(json.dumps(body).encode()); response.code = status
            evidence = []
            with patch('urllib.request.build_opener') as opener:
                opener.return_value.open.return_value = response
                summary = Client(Config(token='synthetic')).execute('employment_history',
                    {'uan': '123456789012'}, consent_confirmed=True, evidence_sink=evidence.append)
                request = opener.return_value.open.call_args.args[0]
                self.assertEqual(request.full_url,
                    'https://api-preproduction.signzy.app/api/v3/underwriting/fetch-employment-history')
                self.assertEqual(json.loads(request.data)['uan'], '123456789012')
                self.assertEqual(opener.return_value.open.call_count, 1)
            self.assertEqual(evidence[0]['provider_response']['json'], body)
            self.assertNotIn('PRIVATE', json.dumps(summary))
            if status == 403:
                self.assertEqual(summary['error_code'], 'access_denied')


if __name__ == '__main__':
    unittest.main()
