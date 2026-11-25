"""c-scale-budget: gzip for JSON is opt-in, correct, and runs after the API envelope."""
import gzip
import json
import os
from unittest import mock

import generate_users
from test_segment_efg_routes import RouteTestCase


class CompressionTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        users = generate_users.generate_users(40, seed=3)
        generate_users.seed_db(self.conn, users); self.conn.commit()
        self.uid = users[0]['user_id']
        self.client.post('/login/' + self.uid)

    def reach(self, **headers):
        return self.client.get('/api/v1/reach', headers=headers)

    def test_off_by_default(self):
        with mock.patch.dict(os.environ, {'DHASHU_GZIP': '0'}):
            response = self.reach(**{'Accept-Encoding': 'gzip'})
        self.assertIsNone(response.headers.get('Content-Encoding'))

    def test_large_json_is_gzipped_after_the_envelope(self):
        with mock.patch.dict(os.environ, {'DHASHU_GZIP': '0'}):
            plain = self.reach().get_data()
        with mock.patch.dict(os.environ, {'DHASHU_GZIP': '1'}):
            response = self.reach(**{'Accept-Encoding': 'gzip, br'})
        self.assertEqual(response.headers['Content-Encoding'], 'gzip')
        self.assertIn('Accept-Encoding', response.headers['Vary'])
        body = gzip.decompress(response.get_data())
        self.assertEqual(json.loads(body), json.loads(plain))        # identical v1 envelope
        self.assertEqual(set(json.loads(body)), {'data', 'error'})
        self.assertLess(len(response.get_data()), len(plain))
        self.assertEqual(int(response.headers['Content-Length']), len(response.get_data()))

    def test_not_compressed_without_accept_encoding_or_when_small_or_error(self):
        with mock.patch.dict(os.environ, {'DHASHU_GZIP': '1'}):
            self.assertIsNone(self.reach().headers.get('Content-Encoding'))
            small = self.client.get('/api/v1/health', headers={'Accept-Encoding': 'gzip'})
            self.assertIsNone(small.headers.get('Content-Encoding'))
            missing = self.client.get('/api/v1/nope', headers={'Accept-Encoding': 'gzip'})
            self.assertEqual(missing.status_code, 404)
            self.assertIsNone(missing.headers.get('Content-Encoding'))
