import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import signzy_test
from signzy.client import Client, Config


class CourtCliTests(unittest.TestCase):
    def test_explicit_categories_reach_wire_and_summary(self):
        for category in ('criminal', 'civil'):
            with self.subTest(category=category), tempfile.TemporaryDirectory() as tmp:
                original = os.getcwd()
                try:
                    os.chdir(tmp)
                    response = io.BytesIO(b'{"status":1,"caseId":"synthetic123"}')
                    response.code = 200
                    with patch('sys.argv', ['signzy_test.py', 'individual_search',
                               '--match-type', 'possible', '--case-category', category]), \
                         patch.object(signzy_test.Config, 'from_env', return_value=Config(token='synthetic')), \
                         patch.object(signzy_test, 'ReceiptStore'), \
                         patch.object(signzy_test.getpass, 'getpass', side_effect=['Test Name', 'Test Address']), \
                         patch('urllib.request.build_opener') as opener, \
                         contextlib.redirect_stdout(io.StringIO()):
                        opener.return_value.open.return_value = response
                        signzy_test.main()
                        sent = json.loads(opener.return_value.open.call_args.args[0].data)
                        self.assertEqual(sent, {'name': 'Test Name', 'address': 'Test Address',
                                               'matchType': 'possible', 'caseCategory': category})
                        self.assertEqual(opener.return_value.open.call_count, 1)
                    summary = json.loads(next(Path('data/signzy-test-receipts').glob('*.summary.json')).read_text())
                    self.assertEqual(summary['match_type'], 'possible')
                    self.assertEqual(summary['case_category'], category)
                    self.assertNotIn('Test Name', json.dumps(summary))
                finally:
                    os.chdir(original)

    def test_category_rejected_for_other_operations_before_config(self):
        with patch('sys.argv', ['signzy_test.py', 'pan_simple', '--case-category', 'civil']), \
             patch.object(signzy_test.Config, 'from_env') as config, \
             contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                signzy_test.main()
            config.assert_not_called()
