"""mon-health: liveness stays database-free; readiness checks the database quickly."""
from unittest import mock

import db
from test_segment_efg_routes import RouteTestCase


class HealthTests(RouteTestCase):
    def test_liveness_needs_no_database(self):
        with mock.patch.object(db, 'acquire', side_effect=AssertionError('liveness touched the DB')):
            response = self.client.get('/api/v1/health')
        self.assertEqual((response.status_code, response.get_json()['data']['status']), (200, 'ok'))

    def test_ready_when_the_database_answers_without_sign_in(self):
        response = self.client.get('/api/v1/ready')
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()['data']['status'], 'ready')

    def test_not_ready_is_a_clean_503_with_no_details(self):
        with mock.patch.object(db, 'acquire', side_effect=RuntimeError('connection refused to 10.0.0.5:5432 as postgres')):
            response = self.client.get('/api/v1/ready')
        self.assertEqual(response.status_code, 503)
        body = response.get_data(as_text=True)
        self.assertEqual(response.get_json()['error']['code'], 'not_ready')
        for leak in ('10.0.0.5', 'postgres', 'refused', 'Traceback'):
            self.assertNotIn(leak, body)
        self.assertEqual(response.headers.get('Cache-Control'), 'no-store')

    def test_ready_releases_its_connection(self):
        released = []
        real_release = db.release
        with mock.patch.object(db, 'release', side_effect=lambda c: (released.append(c), real_release(c))):
            self.client.get('/api/v1/ready')
        self.assertTrue(released and released[-1] is not None)
