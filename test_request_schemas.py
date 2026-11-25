"""cq-pydantic: every JSON body is checked against a strict schema built from its
declared fields; wrong types and unknown fields are rejected; the OpenAPI request
schemas are generated from the same models."""
import os
import unittest
from unittest import mock

from flask import Flask

import request_schemas
from api_contract import ApiError, json_object
from test_segment_efg_routes import RouteTestCase
from tools import gen_openapi_schemas

APP = Flask('schema-test')


def call(body, required=(), optional=(), content_type='application/json'):
    import json
    data = body if isinstance(body, str) else json.dumps(body)
    with APP.test_request_context('/x', method='POST', data=data, content_type=content_type):
        return json_object(required=required, optional=optional)


class JsonObjectSchemaTests(unittest.TestCase):
    def assertRejected(self, body, required=(), optional=(), status=400, contains=''):
        with self.assertRaises(ApiError) as ctx:
            call(body, required, optional)
        self.assertEqual((ctx.exception.code, ctx.exception.status), ('validation_error', status))
        self.assertIn(contains, ctx.exception.message)
        return ctx.exception

    def test_valid_bodies_pass_unchanged(self):
        body = {'request_id': 'r1', 'consent': True, 'consent_version': 'v2', 'revision': 3, 'slots': [1, 2],
                'fields': {'a': 1}, 'whatever_untyped': {'x': [1]}}
        self.assertEqual(call(body, required=set(body)), body)
        self.assertEqual(call({'consent': True}, required={'consent'}, optional={'text'}), {'consent': True})
        self.assertEqual(call({'consent': True, 'text': None}, required={'consent'}, optional={'text'}),
                         {'consent': True, 'text': None})

    def test_wrong_types_are_rejected_without_coercion_and_values_are_not_echoed(self):
        cases = [({'consent': 'true'}, 'consent'), ({'consent': 1}, 'consent'), ({'revision': '3'}, 'revision'),
                 ({'revision': True}, 'revision'), ({'request_id': 5}, 'request_id'), ({'request_id': ''}, 'request_id'),
                 ({'slots': 'mon'}, 'slots'), ({'fields': []}, 'fields'), ({'text': 'x' * 10_001}, 'text')]
        for body, field in cases:
            error = self.assertRejected(body, required=set(body), contains=field)
            self.assertNotIn(repr(next(iter(body.values())))[:20], error.message.replace(field, ''))

    def test_unknown_and_missing_fields(self):
        self.assertRejected({'consent': True, 'admin': True}, required={'consent'}, contains='Expected required fields')
        self.assertRejected({}, required={'consent'}, contains='Expected required fields')

    def test_status_is_400_by_default_and_422_when_switched(self):
        self.assertRejected({'consent': 'yes'}, required={'consent'}, status=400)
        with mock.patch.dict(os.environ, {'DHASHU_VALIDATION_STATUS': '422'}):
            self.assertRejected({'consent': 'yes'}, required={'consent'}, status=422)
            self.assertRejected({'consent': True, 'x': 1}, required={'consent'}, status=422)

    def test_non_json_and_non_object_bodies(self):
        with self.assertRaises(ApiError) as ctx:
            call('a=b', content_type='application/x-www-form-urlencoded')
        self.assertEqual(ctx.exception.status, 415)
        self.assertRejected([1, 2], contains='JSON object')

    def test_models_are_cached_per_field_set(self):
        a = request_schemas.model_for(frozenset({'consent'}), frozenset())
        self.assertIs(a, request_schemas.model_for(frozenset({'consent'}), frozenset()))


class HttpSchemaTests(RouteTestCase):
    def test_route_rejects_a_wrong_type_through_the_api_envelope(self):
        self.make_user('owner'); self.client.post('/login/owner')
        response = self.client.post('/api/v1/simulated-clock', json={'advance_hours': '2'})
        self.assertEqual(response.status_code, 400, response.get_json())
        self.assertEqual(response.get_json()['error']['code'], 'validation_error')
        self.assertIn('advance_hours', response.get_json()['error']['message'])
        with mock.patch.dict(os.environ, {'DHASHU_VALIDATION_STATUS': '422'}):
            self.assertEqual(self.client.post('/api/v1/simulated-clock', json={'advance_hours': '2'}).status_code, 422)


class OpenApiTests(unittest.TestCase):
    def test_document_is_generated_from_the_enforced_schemas(self):
        self.assertEqual(gen_openapi_schemas.main(['--check']), 0,
                         'run: python tools/gen_openapi_schemas.py')

    def test_every_route_with_literal_fields_is_documented(self):
        import json
        from pathlib import Path
        doc = json.loads(Path('docs/openapi-phase4.json').read_text(encoding='utf-8'))
        found = gen_openapi_schemas.collect()
        self.assertGreaterEqual(len(found), 75)
        for (path, method), sets in found.items():
            schema = doc['paths'][path][method]['requestBody']['content']['application/json']['schema']
            self.assertFalse(schema.get('additionalProperties', False) is not False and 'oneOf' not in schema, path)
            if len(sets) == 1:
                self.assertEqual(set(schema['properties']), set(sets[0][0] | sets[0][1]), (path, method))


if __name__ == '__main__':
    unittest.main()
