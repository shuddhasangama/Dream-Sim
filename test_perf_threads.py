"""perf-threads: the web gunicorn command is configurable, and with no settings it
starts exactly like the old `gunicorn app:app` (gunicorn's own defaults)."""
import importlib.util
import unittest

import service_entrypoint as entry


def _gunicorn_config_importable():
    try:
        return importlib.util.find_spec('grp') is not None and importlib.util.find_spec('gunicorn.config') is not None
    except ModuleNotFoundError:
        return False


class WebCommandTests(unittest.TestCase):
    def test_defaults_are_the_old_start_up(self):
        self.assertEqual(entry.web_command({}), [
            'gunicorn', 'app:app', '--workers', '1', '--worker-class', 'sync',
            '--timeout', '30', '--graceful-timeout', '30', '--keep-alive', '2'])

    def test_scaling_settings(self):
        args = entry.web_command({'WEB_CONCURRENCY': '3', 'GUNICORN_THREADS': '4', 'GUNICORN_TIMEOUT': '20',
                                  'GUNICORN_GRACEFUL_TIMEOUT': '25', 'GUNICORN_KEEPALIVE': '5',
                                  'GUNICORN_MAX_REQUESTS': '2000', 'GUNICORN_MAX_REQUESTS_JITTER': '200'})
        flags = dict(zip(args[2::2], args[3::2]))
        self.assertEqual(flags, {'--workers': '3', '--worker-class': 'gthread', '--timeout': '20',
                                 '--graceful-timeout': '25', '--keep-alive': '5', '--threads': '4',
                                 '--max-requests': '2000', '--max-requests-jitter': '200'})

    def test_jitter_defaults_to_ten_percent_and_values_are_clamped(self):
        flags = dict(zip(*[iter(entry.web_command({'GUNICORN_MAX_REQUESTS': '1000'})[2:])] * 2))
        self.assertEqual(flags['--max-requests-jitter'], '100')
        flags = dict(zip(*[iter(entry.web_command({'WEB_CONCURRENCY': '999', 'GUNICORN_THREADS': '0',
                                                   'GUNICORN_TIMEOUT': 'abc'})[2:])] * 2))
        self.assertEqual((flags['--workers'], flags['--worker-class'], flags['--timeout']), ('32', 'sync', '30'))

    @unittest.skipUnless(_gunicorn_config_importable(), 'gunicorn.config needs a POSIX system (runs on Linux CI)')
    def test_defaults_match_gunicorn_and_parse_with_its_own_parser(self):
        from gunicorn.config import Config
        defaults = Config()
        args = entry.web_command({})
        flags = dict(zip(args[2::2], args[3::2]))
        self.assertEqual(int(flags['--workers']), defaults.workers)
        self.assertEqual(flags['--worker-class'], defaults.worker_class_str)
        self.assertEqual(int(flags['--timeout']), defaults.timeout)
        self.assertEqual(int(flags['--graceful-timeout']), defaults.graceful_timeout)
        self.assertEqual(int(flags['--keep-alive']), defaults.keepalive)
        self.assertEqual(defaults.max_requests, 0)
        parsed = Config().parser().parse_args(entry.web_command({'GUNICORN_THREADS': '4', 'GUNICORN_MAX_REQUESTS': '50'})[1:])
        self.assertEqual((parsed.threads, parsed.max_requests, parsed.args), (4, 50, ['app:app']))


if __name__ == '__main__':
    unittest.main()
