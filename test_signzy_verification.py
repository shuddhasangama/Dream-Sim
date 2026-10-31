import copy
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from cryptography.fernet import Fernet
from signzy import pan_simple
from signzy.errors import classify
from signzy.receipts import ReceiptStore
from signzy.verification import evaluate, ingest, import_receipt

def sample():
    return {'receipt_id': 'test', 'environment': 'preproduction', 'operation': 'pan_simple',
            'finished_at_utc': '2026-10-28T00:00:00+00:00',
            'binding': {'user_id': 'test-user', 'declared_fields': {'name': 'Jane Doe', 'dob': '2000-01-01'}},
            'request': {'input_fields': {'panNumber': 'AAAPA0000A'}},
            'wrapper_summary': {}, 'provider_response': {'http_status': 200,
            'json': {'result': {'name': 'JANE  DOE', 'dob': '2000-01-01', 'panStatus': 'VALID'}}}}

class VerificationTests(unittest.TestCase):
    def test_pan_payload_and_validation(self):
        self.assertEqual(pan_simple.payload({'panNumber': 'aaapa0000a'}), {'panNumber': 'AAAPA0000A'})
        for payload in ({'panNumber': ''}, {'panNumber': 'bad'}, {'panNumber': 'AAAPA0000A', 'mobile': 'x'}):
            with self.assertRaises(ValueError):
                pan_simple.payload(payload)

    def test_field_comparisons(self):
        evidence = sample()
        self.assertEqual(evaluate(evidence)[0], 'verified')
        evidence['binding']['declared_fields']['name'] = 'Other Name'
        self.assertEqual(evaluate(evidence)[0], 'partially_verified')
        evidence['binding']['declared_fields'] = {}
        self.assertEqual(evaluate(evidence)[0], 'unverified')

    def test_business_invalid_and_malformed_not_verified(self):
        for modify in ('business', 'invalid', 'missing', 'error'):
            evidence = sample()
            if modify == 'business':
                evidence['request']['input_fields']['panNumber'] = 'AAACA0000A'
            elif modify == 'invalid':
                evidence['provider_response']['json']['result']['panStatus'] = 'INVALID'
            elif modify == 'missing':
                evidence['provider_response']['json']['result']['dob'] = ''
            else:
                evidence['wrapper_summary']['error_code'] = 'provider_error'
            self.assertEqual(evaluate(evidence)[0], 'failed_to_verify')

    def test_historical_employer_not_current_verification(self):
        evidence = sample()
        evidence['operation'] = 'current_employer'
        evidence['binding']['declared_fields'] = {'employer': 'Example'}
        evidence['wrapper_summary'] = {'result_code': 200}
        evidence['provider_response']['json'] = {'employmentSummary': {'is_employed': False,
            'recent_employer_data': {'establishment_name': 'Example'}}}
        self.assertEqual(evaluate(evidence)[0], 'unverified')

    def test_errors(self):
        cases = [(400, {'error': {'statusCode': 400}}, 'invalid_input'),
                 (401, {'message': 'Invalid authentication credentials'}, 'authentication_failed'),
                 (401, {'message': 'No API key found in request'}, 'authentication_failed'),
                 (409, {'error': {'statusCode': 409, 'message': 'Upstream Down'}}, 'provider_unavailable'),
                 (403, {}, 'access_denied'), (429, {}, 'rate_limited'),
                 (402, {'message': 'Insufficient credits'}, 'credits_unavailable'),
                 (503, {}, 'provider_unavailable')]
        for status, body, expected in cases:
            result = classify(status, body)
            self.assertEqual(result['error_code'], expected)
            self.assertFalse(result['retry_automatically'])

    def test_encrypted_database_import_idempotency_and_binding(self):
        from pathlib import Path
        conn = sqlite3.connect(':memory:')
        conn.row_factory = sqlite3.Row
        conn.executescript('CREATE TABLE "User" (id TEXT PRIMARY KEY); INSERT INTO "User" VALUES (\'test-user\');')
        schema = Path('schema.sql').read_text(encoding='utf-8')
        conn.executescript(schema[schema.index('CREATE TABLE IF NOT EXISTS "BgvEvidence"'):])
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ,
                {'SIGNZY_RECEIPT_ENCRYPTION_KEY': Fernet.generate_key().decode()}):
            store = ReceiptStore(directory)
            evidence = sample()
            path = store.save(evidence)
            self.assertEqual(import_receipt(conn, path, store), 'verified')
            self.assertEqual(import_receipt(conn, path, store), 'verified')
            row = conn.execute('SELECT * FROM "BgvEvidence"').fetchall()
            self.assertEqual(len(row), 1)
            self.assertNotIn('Jane', row[0]['protected_details'])
            unbound = copy.deepcopy(evidence); unbound.pop('binding')
            with self.assertRaises(ValueError):
                ingest(conn, unbound, store)
        conn.close()
