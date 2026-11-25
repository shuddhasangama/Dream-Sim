"""sec-cf: forwarded client IPs are trusted only behind the configured proxy."""
import os
import re
import subprocess

import client_ip as client_ip_module
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
        # sec-ip (approved redesign): the header is trusted only from a Cloudflare hop
        # (X-Forwarded-For counted from the right), and IPv6 is keyed by its /64.
        cf = {'X-Forwarded-For': '172.70.1.20'}
        with mock.patch.dict(os.environ, {'DHASHU_TRUSTED_PROXY': 'cloudflare'}):
            self.assertEqual(client_ip(req(**cf, **{'CF-Connecting-IP': '203.0.113.9'})), '203.0.113.9')
            self.assertEqual(client_ip(req(**cf, **{'CF-Connecting-IP': ' 2001:db8::1 '})), '2001:db8::/64')
            for bad in ('not-an-ip', '203.0.113.9, 10.0.0.1', '', '999.1.1.1'):
                self.assertEqual(client_ip(req(**cf, **{'CF-Connecting-IP': bad})), '172.70.1.20', bad)
            self.assertEqual(client_ip(req(**{'CF-Connecting-IP': '203.0.113.9'})).split(':')[0], 'unresolved')
            self.assertNotEqual(client_ip(req(peer=None)), 'unknown')       # never one shared 'unknown' bucket

    def test_x_forwarded_for_is_never_trusted(self):
        # sec-ip (approved redesign): the client-supplied (left) part of X-Forwarded-For is
        # never trusted; the entry the trusted proxy appended (right-most) is the visitor.
        with mock.patch.dict(os.environ, {'DHASHU_TRUSTED_PROXY': 'cloudflare'}):
            self.assertEqual(client_ip(req(**{'X-Forwarded-For': '6.6.6.6, 203.0.113.9'})), '203.0.113.9')
        with mock.patch.dict(os.environ, {'DHASHU_TRUSTED_PROXY': ''}):
            self.assertEqual(client_ip(req(**{'X-Forwarded-For': '203.0.113.9'})), '10.0.0.7')

    def test_rate_limit_keys_use_the_helper(self):
        from pathlib import Path
        for name in ('auth.py', 'member_password.py', 'waitlist_api.py', 'admin_dashboard/app.py'):
            text = Path(name).read_text(encoding='utf-8')
            self.assertNotIn("request.remote_addr or 'unknown'", text, name)
            self.assertIn('client_ip.client_ip(request)', text, name)

RAILWAY_PROXY = '100.64.0.7'          # Railway's internal proxy address (private / CGNAT)
CF_EDGE = '172.70.1.20'               # inside 172.64.0.0/13 (Cloudflare)
NOT_CF = '203.0.113.50'


def mreq(peer=RAILWAY_PROXY, **headers):
    return SimpleNamespace(remote_addr=peer, headers={k.replace('_', '-'): v for k, v in headers.items()})


def mode(name, **extra):
    return mock.patch.dict(os.environ, {'DHASHU_TRUSTED_PROXY': name, **extra})


key = client_ip


class ModeTests(unittest.TestCase):
    def setUp(self):
        client_ip_module.reset(); self.addCleanup(client_ip_module.reset)

    def test_none_uses_the_socket_peer_and_ignores_every_header(self):
        with mode(''):
            self.assertEqual(key(mreq('198.51.100.9', X_Forwarded_For='1.2.3.4', CF_Connecting_IP='5.6.7.8')), '198.51.100.9')
        with mode('nonsense'):
            self.assertEqual(key(mreq('198.51.100.9', X_Forwarded_For='1.2.3.4')), '198.51.100.9')

    def test_railway_counts_hops_from_the_right_never_the_spoofable_left(self):
        with mode('railway'):
            self.assertEqual(key(mreq(X_Forwarded_For='198.51.100.9')), '198.51.100.9')
            # a client that sends its own X-Forwarded-For: Railway appends the real address on the right
            self.assertEqual(key(mreq(X_Forwarded_For='1.1.1.1, 9.9.9.9, 198.51.100.9')), '198.51.100.9')
        with mode('railway', DHASHU_TRUSTED_HOPS='2'):             # e.g. another trusted proxy in front
            self.assertEqual(key(mreq(X_Forwarded_For='6.6.6.6, 198.51.100.9, 10.0.0.2')), '198.51.100.9')

    def test_cloudflare_header_only_from_a_cloudflare_hop_or_with_the_origin_secret(self):
        with mode('cloudflare'):
            self.assertEqual(key(mreq(X_Forwarded_For=CF_EDGE, CF_Connecting_IP='198.51.100.9')), '198.51.100.9')
            # the hop is not Cloudflare: the header is ignored, the hop itself is the visitor
            self.assertEqual(key(mreq(X_Forwarded_For=NOT_CF, CF_Connecting_IP='198.51.100.9')), NOT_CF)
            self.assertEqual(key(mreq(X_Forwarded_For=CF_EDGE, CF_Connecting_IP='not-an-ip')), CF_EDGE)
        secret = 's' * 32
        with mode('cloudflare', DHASHU_CF_ORIGIN_SECRET=secret):
            self.assertEqual(key(mreq(X_Forwarded_For=NOT_CF, CF_Connecting_IP='198.51.100.9', X_CF_Origin_Secret=secret)), '198.51.100.9')
            self.assertEqual(key(mreq(X_Forwarded_For=NOT_CF, CF_Connecting_IP='198.51.100.9', X_CF_Origin_Secret='wrong')), NOT_CF)
        with mode('cloudflare', DHASHU_CF_ORIGIN_SECRET='short'):     # a weak secret is never accepted
            self.assertEqual(key(mreq(X_Forwarded_For=NOT_CF, CF_Connecting_IP='198.51.100.9', X_CF_Origin_Secret='short')), NOT_CF)

    def test_ipv4_and_ipv6_slash_64(self):
        with mode('railway'):
            a = key(mreq(X_Forwarded_For='2001:db8:1:2:aaaa::1'))
            b = key(mreq(X_Forwarded_For='2001:db8:1:2:bbbb::9'))
            c = key(mreq(X_Forwarded_For='2001:db8:1:3::1'))
            self.assertEqual(a, '2001:db8:1:2::/64'); self.assertEqual(a, b); self.assertNotEqual(a, c)
            self.assertEqual(key(mreq(X_Forwarded_For='::ffff:198.51.100.9')), '198.51.100.9')
            self.assertEqual(key(mreq(X_Forwarded_For='[2001:db8::1]')), '2001:db8::/64')

    def test_invalid_or_missing_never_falls_back_to_one_shared_bucket(self):
        with mode('railway'), self.assertLogs(level='WARNING'):
            k1 = key(mreq(User_Agent='phone-A'))
            k2 = key(mreq(User_Agent='phone-B', X_Forwarded_For='garbage'))
            self.assertTrue(k1.startswith('unresolved:')); self.assertTrue(k2.startswith('unresolved:'))
            self.assertNotEqual(k1, k2)
            self.assertNotEqual(k1, RAILWAY_PROXY)                     # never the proxy's address
        with mode('railway'):                                           # a direct (global) peer is used as-is
            self.assertEqual(key(mreq('81.2.69.160')), '81.2.69.160')

    def test_only_client_ip_reads_remote_addr_or_forwarding_headers(self):
        files = subprocess.run(['git', 'ls-files', '*.py'], capture_output=True, text=True).stdout.split()
        offenders = []
        for name in files:
            if name in ('client_ip.py',) or name.startswith('test_') or '/test_' in name:
                continue
            text = open(name, encoding='utf-8').read()
            if re.search(r'\bremote_addr\b', text) or re.search(r"headers\.get\(['\"](X-Forwarded-For|CF-Connecting-IP|X-Real-IP)", text):
                offenders.append(name)
        self.assertEqual(offenders, [])

    def test_startup_warning_on_railway_without_a_mode(self):
        self.assertIsNotNone(client_ip_module.startup_check({'RAILWAY_ENVIRONMENT': 'production'}))
        self.assertIsNone(client_ip_module.startup_check({'RAILWAY_ENVIRONMENT': 'production', 'DHASHU_TRUSTED_PROXY': 'railway'}))
        self.assertIsNone(client_ip_module.startup_check({}))

    def test_bundled_cloudflare_ranges(self):
        nets = client_ip_module.cloudflare_networks()
        self.assertGreaterEqual(len(nets), 20)
        self.assertTrue(client_ip_module.from_cloudflare(client_ip_module.parse(CF_EDGE)))
        self.assertTrue(client_ip_module.from_cloudflare(client_ip_module.parse('2606:4700::1111')))
        self.assertFalse(client_ip_module.from_cloudflare(client_ip_module.parse(NOT_CF)))

    def test_shared_ip_bucket_alert(self):
        with mock.patch.dict(os.environ, {'DHASHU_SHARED_IP_ALERT': '5'}), mock.patch('alerts.emit') as emit:
            for n in range(5):
                client_ip_module.note_identity('198.51.100.9', f'+91987654321{n}')
            emit.assert_not_called()
            client_ip_module.note_identity('198.51.100.9', '+919876543299')
            client_ip_module.note_identity('198.51.100.9', '+919876543298')      # once per window
            self.assertEqual([c.args[0] for c in emit.call_args_list], ['shared_ip_bucket'])
            self.assertNotIn('198.51.100.9', str(emit.call_args))          # the address is never in the alert


if __name__ == '__main__':
    unittest.main()
