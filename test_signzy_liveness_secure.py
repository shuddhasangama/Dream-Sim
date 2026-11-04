import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from cryptography.fernet import Fernet
from signzy import liveness_secure_create as create, liveness_secure_data as data
from signzy.client import Client, Config
from signzy.receipts import read_private
import signzy_liveness_test as runner


def created():
    return {'token': 'test-session-123', 'consumerId': 'test-consumer',
        'videoUrl': 'https://liveliness-preproduction.signzy.app/consumer/test/token/test-session-123'}


def completed(live=True, match=True, overall=True, extra=True):
    return {'result': {'token': 'test-session-123', 'consumerId': 'test-consumer', 'isUsed': 1,
        'capturedImage': 'https://images.example/private.jpg', 'passiveLiveliness': {'liveness': live, 'score': 1},
        'faceMatch': {'verified': match, 'matchPercentage': '99.00%'}, 'status': overall,
        'additionalChecks': {'status': extra, 'attemptNumber': 1}}}


class Contracts(unittest.TestCase):
    def values(self):
        return {'matchImage': ['https://images.example/consented.jpg'], 'faceMatchThreshold': .6, 'piiDeletionTTL': '6 months'}

    def test_supplied_create_contract_and_optional_callbacks(self):
        value = create.payload(self.values())
        self.assertEqual(value['reviewImage'], 'true')
        self.assertNotIn('callbackUrl', value)
        self.assertEqual(create.payload({**self.values(), 'callbackUrl': 'https://callback.example/receive'})['callbackUrl'], 'https://callback.example/receive')
        for t in [True, '0.6', float('nan'), .99]:
            with self.assertRaises(ValueError):
                create.payload({**self.values(), 'faceMatchThreshold': t})
        with self.assertRaises(ValueError):
            create.payload({**self.values(), 'matchImage': ['data:image/jpeg;base64,private']})

    def test_create_direct_and_wrapped_responses(self):
        for body in [created(), {'result': created()}]:
            self.assertEqual(create.session(body)[0], 'test-session-123')
            self.assertTrue(create.summarize(200, body)['capture_link_received'])
            self.assertNotIn('test-session-123', str(create.summarize(200, body)))

    def test_liveness_pass_and_face_failure_is_not_combined_success(self):
        value = data.summarize(200, completed(match=False, overall=False))
        self.assertTrue(value['liveness_passed'])
        self.assertFalse(value['face_match_passed'])
        self.assertFalse(value['combined_passed'])
        self.assertFalse(value['automatic_verification'])

    def test_all_four_checks_required_and_incomplete_does_not_pass(self):
        self.assertTrue(data.summarize(200, completed())['combined_passed'])
        for field in ['live', 'match', 'overall', 'extra']:
            self.assertFalse(data.summarize(200, completed(**{field: False}))['combined_passed'])
        for body in [{'result': {}}, {'result': {'isUsed': 0}}, completed(match='true')]:
            self.assertIsNone(data.summarize(200, body)['combined_passed'])
        self.assertIsNone(data.summarize(403, completed())['combined_passed'])

    def test_private_fields_are_not_in_default_output(self):
        output = json.dumps(runner.sanitized(completed()))
        self.assertNotIn('test-session-123', output)
        self.assertNotIn('private.jpg', output)


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.env = patch.dict(os.environ, {'SIGNZY_ENV': 'preproduction', 'SIGNZY_TEST_API_KEY': 'synthetic-api-secret',
            'SIGNZY_RECEIPT_ENCRYPTION_KEY': Fernet.generate_key().decode()})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.dir_patch = patch.object(runner, 'DIRECTORY', self.directory)
        self.dir_patch.start()
        self.addCleanup(self.dir_patch.stop)

    def response(self, body):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.__enter__.return_value = response
        response.code = 200
        response.headers = {}
        response.read.return_value = json.dumps(body).encode()
        return response

    def invoke(self, args, body, answer='YES'):
        out = io.StringIO()
        with patch('signzy.client.urllib.request.build_opener') as opener, patch('builtins.input', return_value=answer), patch('sys.stdout', out):
            opener.return_value.open.return_value = self.response(body)
            result = runner.main(args)
        return result, out.getvalue(), opener.return_value.open.call_count

    def test_two_step_flow_persists_token_only_in_encrypted_receipt(self):
        code, output, calls = self.invoke(['create', '--match-image', 'https://images.example/aadhaar.jpg'], created())
        self.assertEqual((code, calls), (0, 1))
        self.assertNotIn('synthetic-api-secret', output)
        path = (self.directory / 'latest-create.txt').read_text()
        self.assertNotIn(b'test-session-123', Path(path).read_bytes())
        self.assertEqual(read_private(path)['operation'], 'liveness_secure_create')
        code, output, calls = self.invoke(['get'], completed())
        self.assertEqual((code, calls), (0, 1))
        self.assertIn('liveness_and_face_match_passed', output)
        self.assertNotIn('test-session-123', output)
        with self.assertRaisesRegex(ValueError, 'already attempted'):
            runner.main(['create', '--match-image', 'https://images.example/aadhaar.jpg'])

    def test_cancel_before_call_and_get_without_create(self):
        _, _, calls = self.invoke(['create', '--match-image', 'https://images.example/a.jpg'], created(), 'NO')
        self.assertEqual(calls, 0)
        self.assertFalse((self.directory / 'latest-create.txt').exists())
        with self.assertRaisesRegex(ValueError, 'Run create first'):
            runner.main(['get'])

    def test_session_mismatch_is_not_accepted(self):
        self.invoke(['create', '--match-image', 'https://images.example/a.jpg'], created())
        body = completed()
        body['result']['token'] = 'different-session'
        code, output, _ = self.invoke(['get'], body)
        self.assertEqual(code, 2)
        self.assertIn('SESSION MISMATCH', output)

    def test_transport_timeout_is_saved_and_never_retried(self):
        with patch('signzy.client.urllib.request.build_opener') as opener, patch('builtins.input', return_value='YES'), patch('sys.stdout', io.StringIO()):
            opener.return_value.open.side_effect = TimeoutError()
            self.assertEqual(runner.main(['create', '--match-image', 'https://images.example/a.jpg']), 2)
            self.assertEqual(opener.return_value.open.call_count, 1)
        self.assertTrue((self.directory / 'latest-create.txt').exists())

    def test_production_is_rejected_without_call(self):
        with patch.dict(os.environ, {'SIGNZY_ENV': 'production'}):
            with self.assertRaisesRegex(ValueError, 'only permits'):
                runner.main(['create'])
