import io
import json
import os
import tempfile
import unittest
from unittest.mock import patch
from signzy.client import Client, Config
from signzy.receipts import ReceiptStore, read_private


class ReceiptTests(unittest.TestCase):
    def test_provider_payload_preserved_summary_separate(self):
        body = {'resultCode': 200, 'employmentSummary': {'is_employed': False,
                'recent_employer_data': {'establishment_name': 'SYNTHETIC EMPLOYER'}},
                'uanDetails': {'SYNTHETIC': {'unknown_future_field': 'preserved'}}}
        response = io.BytesIO(json.dumps(body).encode())
        response.code = 200
        evidence = []
        with patch('urllib.request.build_opener') as factory:
            factory.return_value.open.return_value = response
            summary = Client(Config(token='synthetic-secret')).execute('current_employer',
                {'panNumber': 'AAAAA0000A', 'mobile': '9000000000'}, consent_confirmed=True, evidence_sink=evidence.append)
        self.assertEqual(evidence[0]['provider_response']['json'], body)
        self.assertNotIn('SYNTHETIC EMPLOYER', json.dumps(summary))
        self.assertNotIn('synthetic-secret', json.dumps(evidence))
        self.assertEqual(evidence[0]['wrapper_summary'], summary)

    def test_error_and_timeout_evidence(self):
        from urllib.error import HTTPError
        error = HTTPError('https://example.com', 403, 'Denied', {}, io.BytesIO(b'{"message":"denied"}'))
        for failure in (error, TimeoutError()):
            evidence = []
            with patch('urllib.request.build_opener') as factory:
                factory.return_value.open.side_effect = failure
                Client(Config(token='synthetic')).execute('current_employer',
                    {'panNumber': 'AAAAA0000A', 'mobile': '9000000000'}, consent_confirmed=True, evidence_sink=evidence.append)
                self.assertEqual(factory.return_value.open.call_count, 1)
            self.assertEqual(len(evidence), 1)
        self.assertIsNone(evidence[0]['provider_response'])

    def test_encrypted_roundtrip_no_overwrite(self):
        from cryptography.fernet import Fernet
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,
                {'SIGNZY_RECEIPT_ENCRYPTION_KEY': Fernet.generate_key().decode()}):
            store = ReceiptStore(directory)
            evidence = {'receipt_id': 'synthetic', 'provider_response': {'name': 'PRIVATE NAME'}}
            path = store.save(evidence)
            self.assertNotIn(b'PRIVATE NAME', path.read_bytes())
            self.assertEqual(read_private(path), evidence)
            with self.assertRaises(FileExistsError):
                store.save(evidence)

    @unittest.skipUnless(os.name == 'nt', 'Windows protection')
    def test_windows_protection_roundtrip(self):
        from signzy.receipts import dpapi
        self.assertEqual(dpapi(dpapi(b'private synthetic evidence'), decrypt=True),
                         b'private synthetic evidence')

    def test_invalid_and_oversized_bodies_are_preserved_and_labelled(self):
        import base64
        for raw, complete in ((b'not JSON', True), (b'x' * 2_000_001, False)):
            response = io.BytesIO(raw)
            response.code = 502
            evidence = []
            with patch('urllib.request.build_opener') as factory:
                factory.return_value.open.return_value = response
                summary = Client(Config(token='synthetic')).execute('current_employer',
                    {'panNumber': 'AAAAA0000A', 'mobile': '9000000000'},
                    consent_confirmed=True, evidence_sink=evidence.append)
            saved = evidence[0]['provider_response']
            self.assertEqual(base64.b64decode(saved['body_base64']), raw)
            self.assertEqual(saved['body_complete'], complete)
            self.assertEqual(summary['outcome'], 'invalid_or_oversized_response')

    def test_storage_failure_warns_against_retry(self):
        response = io.BytesIO(b'{}'); response.code = 200
        with patch('urllib.request.build_opener') as factory:
            factory.return_value.open.return_value = response
            with self.assertRaisesRegex(ValueError, 'Do not rerun'):
                Client(Config(token='synthetic')).execute('current_employer',
                    {'panNumber': 'AAAAA0000A', 'mobile': '9000000000'}, consent_confirmed=True,
                    evidence_sink=lambda _: (_ for _ in ()).throw(OSError()))


if __name__ == '__main__':
    unittest.main()
