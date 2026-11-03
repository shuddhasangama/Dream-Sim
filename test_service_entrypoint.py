import unittest
from unittest.mock import patch
import service_entrypoint

class EntrypointTests(unittest.TestCase):
    def test_roles_and_no_implicit_bootstrap(self):
        self.assertEqual(service_entrypoint.command('web'),['gunicorn','app:app'])
        self.assertEqual(service_entrypoint.command('bgv-worker')[-1],'bgv_worker.py')
        with self.assertRaises(ValueError): service_entrypoint.command('unknown')
        with patch.dict('os.environ',{'DHASHU_BGV_BOOTSTRAP_USER_ID':''}):
            self.assertIsNone(service_entrypoint.prepare_pilot())
    def test_bootstrap_never_runs_in_production(self):
        with patch.dict('os.environ',{'DHASHU_BGV_BOOTSTRAP_USER_ID':'synthetic','SIGNZY_ENV':'production'}):
            with self.assertRaises(ValueError): service_entrypoint.prepare_pilot()
