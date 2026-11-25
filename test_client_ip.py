"""sec-cf: forwarded client IPs are trusted only behind the configured proxy."""
import os
import unittest
from types import SimpleNamespace
from unittest import mock

from client_ip import client_ip


def req(peer='10.0.0.7', **headers):
    return SimpleNamespace(remote_addr=peer, headers=headers)


class ClientIpTests(unittest.TestCase):
    def test_headers_are_ignored_unless_the_proxy_is_trusted(self):
        with mock.patch.dict(os.environ, {'DHASHU_TRUSTED_PROXY': ''}):
            self.assertEqual(client_ip(req(**{'CF-Connecting-IP': '203.0.113.9'})), '10.0.0.7')
        with mock.patch.dict(os.environ, {'DHASHU_TRUSTED_PROXY': 'something-else'}):
            self.assertEqual(client_ip(req(**{'CF-Connecting-IP': '203.0.113.9'})), '10.0.0.7')

    def test_cloudflare_header_used_only_when_trusted_and_valid(self):
        with mock.patch.dict(os.environ, {'DHASHU_TRUSTED_PROXY': 'cloudflare'}):
            self.assertEqual(client_ip(req(**{'CF-Connecting-IP': '203.0.113.9'})), '203.0.113.9')
            self.assertEqual(client_ip(req(**{'CF-Connecting-IP': ' 2001:db8::1 '})), '2001:db8::1')
            for bad in ('not-an-ip', '203.0.113.9, 10.0.0.1', '', '999.1.1.1'):
                self.assertEqual(client_ip(req(**{'CF-Connecting-IP': bad})), '10.0.0.7', bad)
            self.assertEqual(client_ip(req()), '10.0.0.7')
            self.assertEqual(client_ip(req(peer=None)), 'unknown')

    def test_x_forwarded_for_is_never_trusted(self):
        with mock.patch.dict(os.environ, {'DHASHU_TRUSTED_PROXY': 'cloudflare'}):
            self.assertEqual(client_ip(req(**{'X-Forwarded-For': '203.0.113.9'})), '10.0.0.7')

    def test_rate_limit_keys_use_the_helper(self):
        from pathlib import Path
        for name in ('auth.py', 'member_password.py', 'waitlist_api.py', 'admin_dashboard/app.py'):
            text = Path(name).read_text(encoding='utf-8')
            self.assertNotIn("request.remote_addr or 'unknown'", text, name)
            self.assertIn('client_ip.client_ip(request)', text, name)
