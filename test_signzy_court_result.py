import io
import json
import unittest
from unittest.mock import patch
from signzy import individual_result
from signzy.client import Client, Config, OPERATIONS

SAMPLE = {'status': 1, 'total': 2, 'cases': [
    {'caseId': 'C1', 'name': 'PRIVATE NAME', 'caseCategory': 'criminal', 'algoRisk': 'high risk'},
    {'caseId': 'C2', 'name': 'PRIVATE NAME', 'caseCategory': 'civil'}]}


class CourtResultTests(unittest.TestCase):
    def test_registered(self):
        self.assertIs(OPERATIONS['individual_result'], individual_result)

    def test_payload_validation(self):
        self.assertEqual(individual_result.payload({'caseId': ' 6ae1be210dd4adf046f4efd1 '}),
                         {'caseId': '6ae1be210dd4adf046f4efd1'})
        self.assertEqual(individual_result.payload({'caseId': '65fc3be96eb4b7ba395e0d10__risk__exact'}),
                         {'caseId': '65fc3be96eb4b7ba395e0d10__risk__exact'})
        for bad in ({}, {'caseId': None}, {'caseId': ''}, {'caseId': 'short'}, {'caseId': 'has space here'},
                    {'caseId': 'x' * 121}, {'caseId': 'abcdefgh1', 'name': 'extra'}, {'caseId': 12345678}):
            with self.assertRaises(ValueError):
                individual_result.payload(bad)

    def test_summary_never_clears_or_leaks(self):
        s = individual_result.summarize(200, SAMPLE)
        self.assertEqual((s['cases_returned'], s['total_reported']), (2, 2))
        self.assertEqual(s['court_clearance'], 'not_evaluated')
        self.assertFalse(s['automatic_verification'])
        self.assertNotIn('PRIVATE', json.dumps(s))
        self.assertNotIn('criminal', json.dumps(s))
        empty = individual_result.summarize(200, {'status': 1, 'total': 0, 'cases': []})
        self.assertEqual(empty['cases_returned'], 0)
        self.assertEqual(empty['court_clearance'], 'not_evaluated')   # zero cases is still not a clearance

    def test_unexpected_shapes_and_404(self):
        self.assertEqual(individual_result.summarize(200, {'status': 1})['outcome'],
                         'response_received_contract_review_required')
        self.assertEqual(individual_result.summarize(200, [])['outcome'],
                         'response_received_contract_review_required')
        nf = individual_result.summarize(404, {'message': 'Record Not Found'})
        self.assertEqual(nf['outcome'], 'request_failed_or_unexpected_response')
        self.assertIn('not_a_clearance', nf['diagnostic'])

    def test_transport_single_request_and_private_evidence(self):
        for status, body in ((200, SAMPLE), (404, {'message': 'Record Not Found'}), (403, {'message': 'You cannot consume this service'})):
            response = io.BytesIO(json.dumps(body).encode()); response.code = status
            evidence = []
            with patch('urllib.request.build_opener') as opener:
                opener.return_value.open.return_value = response
                summary = Client(Config(token='synthetic')).execute(
                    'individual_result', {'caseId': '6ae1be210dd4adf046f4efd1'},
                    consent_confirmed=True, evidence_sink=evidence.append)
                request = opener.return_value.open.call_args.args[0]
                self.assertEqual(request.full_url, 'https://api-preproduction.signzy.app/api/v3/individual/result')
                self.assertEqual(json.loads(request.data), {'caseId': '6ae1be210dd4adf046f4efd1'})
                self.assertEqual(opener.return_value.open.call_count, 1)      # no retries
            self.assertEqual(evidence[0]['provider_response']['json'], body)
            self.assertNotIn('PRIVATE', json.dumps(summary))
            self.assertNotIn('6ae1be21', json.dumps(summary))
            self.assertEqual(summary['court_clearance'], 'not_evaluated')
            if status == 403:
                self.assertEqual(summary['error_code'], 'access_denied')


if __name__ == '__main__':
    unittest.main()
