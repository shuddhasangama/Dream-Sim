"""Catch dangling contract references and routes advertised before implementation."""
import json
from pathlib import Path
import re
import unittest

from test_segment_efg_routes import app_module


class Phase4ContractTests(unittest.TestCase):
    def test_openapi_references_resolve_and_operations_are_registered(self):
        document=json.loads(Path('docs/openapi-phase4.json').read_text(encoding='utf-8'))
        self.assertEqual(document['openapi'],'3.1.0')
        operations=[]
        def check(value):
            if isinstance(value,dict):
                if '$ref' in value:
                    self.assertTrue(value['$ref'].startswith('#/'))
                    resolved=document
                    for part in value['$ref'][2:].split('/'):
                        resolved=resolved[part]
                for child in value.values():
                    check(child)
            elif isinstance(value,list):
                for child in value:
                    check(child)
        check(document)
        adapter=app_module.app.url_map.bind('localhost')
        for path,methods in document['paths'].items():
            example=re.sub(r'\{[^}]+\}','example-id',path)
            for method,operation in methods.items():
                endpoint,_=adapter.match('/api/v1'+example,method=method.upper())
                self.assertTrue(endpoint.startswith('api_v1.'))
                self.assertIn('200',operation['responses'])
                self.assertIn('401',operation['responses'])
                operations.append(operation['operationId'])
        self.assertEqual(len(operations),len(set(operations)))
