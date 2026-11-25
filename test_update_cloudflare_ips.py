"""tools/update_cloudflare_ips.py with a fake fetcher (no network)."""
import io
import unittest
from unittest import mock

from tools import update_cloudflare_ips as tool


def opener(pages):
    class Response(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False
    return lambda request, timeout: Response(pages[request.full_url].encode('ascii'))


V4 = '\n'.join(['173.245.48.0/20', '103.21.244.0/22', '104.16.0.0/13', '172.64.0.0/13', '162.158.0.0/15', '198.41.128.0/17'])
V6 = '\n'.join(['2400:cb00::/32', '2606:4700::/32', '2a06:98c0::/29', '2c0f:f248::/32'])


class UpdateTests(unittest.TestCase):
    def test_dry_run_reports_and_writes_nothing(self):
        lines = []
        with mock.patch.object(tool.TARGET.__class__, 'write_text') as write:
            code = tool.main([], opener=opener({tool.SOURCES[0]: V4, tool.SOURCES[1]: V6}), out=lines.append)
        self.assertEqual(code, 0)
        write.assert_not_called()
        self.assertTrue(lines[0].startswith('Added:'))

    def test_refuses_a_short_or_invalid_list(self):
        lines = []
        self.assertEqual(tool.main(['--apply'], opener=opener({tool.SOURCES[0]: '1.2.3.0/24', tool.SOURCES[1]: ''}), out=lines.append), 2)
        with self.assertRaises(ValueError):
            tool.main([], opener=opener({tool.SOURCES[0]: 'not-a-network', tool.SOURCES[1]: V6}), out=lines.append)

    def test_the_bundled_file_parses(self):
        import client_ip
        client_ip.reset()
        self.assertGreaterEqual(len(client_ip.cloudflare_networks()), 20)
        self.assertEqual(set(tool.current()), {str(n) for n in client_ip.cloudflare_networks()})


if __name__ == '__main__':
    unittest.main()
