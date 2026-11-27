"""The browser test backend must boot with local-only authentication."""

import os
from pathlib import Path
import unittest
from unittest import mock

import local_harness
from tools import e2e_server


class E2EServerEnvironmentTests(unittest.TestCase):
    def test_local_harness_is_ready_before_test_fixture_imports(self):
        with mock.patch.dict(os.environ, {
            'AUTH_ENABLED': '1',
            'DATABASE_URL': 'postgresql://unused.invalid/dhashu_test',
            'TWILIO_AUTH_TOKEN': 'synthetic-test-value',
        }, clear=True):
            self.assertEqual(e2e_server.prepare_environment('/tmp/dhashu-e2e-test'),
                             Path('/tmp/dhashu-e2e-test/e2e.db'))
            self.assertEqual(os.environ['AUTH_ENABLED'], '0')
            self.assertTrue(local_harness.active())
            self.assertNotIn('DATABASE_URL', os.environ)
            self.assertNotIn('TWILIO_AUTH_TOKEN', os.environ)

    def test_production_marker_refuses_startup_without_mutating_environment(self):
        with mock.patch.dict(os.environ, {
            'RAILWAY_ENVIRONMENT': 'production',
            'AUTH_ENABLED': '1',
        }, clear=True):
            with self.assertRaises(SystemExit):
                e2e_server.prepare_environment('/tmp/dhashu-e2e-test')
            self.assertEqual(os.environ['AUTH_ENABLED'], '1')
