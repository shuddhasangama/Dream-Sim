"""sec-logs: no emails or phone numbers in error logs, stored incidents or any log line."""
import json
import logging
import os
import re
from pathlib import Path
from unittest import mock

import errors
import observability
from test_segment_efg_routes import RouteTestCase, app_module

PII = ('+919876543210', '9876543210', 'owner@private.test')


class ErrorLogTests(RouteTestCase):
    def raise_with_pii(self):
        def probe():
            raise RuntimeError('failed for member +919876543210 owner@private.test')
        return mock.patch.dict(app_module.app.view_functions, {'api_v1.prepare_week': probe})

    def test_error_log_and_stored_report_are_masked_and_fingerprinted(self):
        import io, contextlib
        self.make_user('owner'); self.client.post('/login/owner')
        app_module.app.config['PROPAGATE_EXCEPTIONS'] = False
        stderr = io.StringIO()
        try:
            with self.raise_with_pii(), contextlib.redirect_stderr(stderr):
                for _ in range(2):
                    self.assertEqual(self.client.post('/api/v1/week/prepare', json={},
                                     headers={'Referer': 'https://x.example/p?email=owner@private.test'}).status_code, 500)
        finally:
            app_module.app.config['PROPAGATE_EXCEPTIONS'] = None
        out = stderr.getvalue()
        self.assertIn('DREAM-ERROR', out)
        for leak in PII:
            self.assertNotIn(leak, out)
        lines = [json.loads(l.split('DREAM-ERROR ', 1)[1]) for l in out.splitlines() if l.startswith('DREAM-ERROR ')]
        self.assertEqual(len({l['fingerprint'] for l in lines}), 1)        # same bug, same fingerprint
        self.assertRegex(lines[0]['fingerprint'], r'^[0-9a-f]{12}$')
        self.assertEqual(lines[0]['referrer'], 'https://x.example/p')
        stored = self.conn.execute('SELECT * FROM ErrorReport').fetchall()
        self.assertTrue(stored)
        for leak in PII:
            self.assertNotIn(leak, json.dumps([dict(r) for r in stored], default=str))

    def test_every_logger_is_masked(self):
        observability.install_log_masking()
        with self.assertLogs('some.module', level='INFO') as logs:
            logging.getLogger('some.module').info('member %s at %s', 'owner@private.test', '+91 98765 43210')
        self.assertEqual(logs.records[0].getMessage(), 'member [email] at [phone]')


class MobileLoggingTests(RouteTestCase):
    def test_app_source_never_logs_profile_values(self):
        for path in Path('mobile/src').rglob('*.js'):
            text = path.read_text(encoding='utf-8')
            for call in re.findall(r'console\.(?:info|error|log|warn|debug)\(([^;]*)\);', text):
                for bad in ('{ fields }', 'submitted:', 'read_back', ', confirmed)', ', req)', ', err)'):
                    self.assertNotIn(bad, call, f'{path}: console call logs data: {call[:80]}')

    def test_vite_only_exposes_vite_variables_and_drops_console_in_release(self):
        config = Path('mobile/vite.config.js').read_text(encoding='utf-8')
        self.assertIn("const ENV_PREFIXES = ['VITE_'];", config)
        self.assertIn('dropConsole: true', config)
        self.assertIn('dropDebugger: true', config)
