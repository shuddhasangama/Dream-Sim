"""Generate the OpenAPI request-body schemas from the enforced schemas (cq-pydantic).

    python tools/gen_openapi_schemas.py           rewrite docs/openapi-phase4.json
    python tools/gen_openapi_schemas.py --check   exit 1 if the document is out of date

Finds every route handler that calls api_contract.json_object(...) (static
parse, no app import), builds the SAME pydantic model the server enforces
(request_schemas.model_for) and writes it as the operation's
requestBody application/json schema, under components/schemas. Descriptions and
examples already in the document are kept; only the schema is replaced.
Handlers whose field set depends on the request (e.g. one route for several
actions) are documented as a oneOf of every literal field set they use.
"""
import argparse
import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import request_schemas  # noqa: E402

DOC = ROOT / 'docs' / 'openapi-phase4.json'
METHODS = {'get', 'post', 'put', 'patch', 'delete'}
SKIP_DIRS = {'.venv', 'node_modules', 'mobile', 'migrations', 'tools', 'admin_dashboard', 'docs'}


def _literal_names(node):
    if node is None:
        return frozenset()
    try:
        value = ast.literal_eval(node)
    except ValueError:
        return None
    if isinstance(value, (set, tuple, list, frozenset)) and all(isinstance(v, str) for v in value):
        return frozenset(value)
    if isinstance(value, dict):          # {} literal = empty set in practice
        return frozenset(value) if not value else None
    return None


def _field_sets(call, func):
    """[(required, optional)] for one json_object call; expands simple dynamic forms."""
    kwargs = {k.arg: k.value for k in call.keywords}
    required, optional = kwargs.get('required'), kwargs.get('optional')
    req, opt = _literal_names(required), _literal_names(optional)
    if req is not None and opt is not None:
        return [(req, opt)]
    # IfExp chains: required={'a'} if x else {'b'} if y else set()  -> each branch
    def branches(node):
        if node is None:
            return [frozenset()]
        if isinstance(node, ast.IfExp):
            return branches(node.body) + branches(node.orelse)
        if isinstance(node, ast.Call) and getattr(node.func, 'id', '') == 'set' and not node.args:
            return [frozenset()]
        lit = _literal_names(node)
        if lit is not None:
            return [lit]
        if isinstance(node, ast.Name):     # a local dict of field sets, e.g. fields={...}[action]
            return None
        return None
    reqs, opts = branches(required), branches(optional)
    if reqs is None or opts is None:
        return []
    return [(r, o) for r in reqs for o in opts] if len(opts) > 1 and len(reqs) == 1 else \
        [(r, opts[min(i, len(opts) - 1)]) for i, r in enumerate(reqs)]


def _routes(func):
    found = []
    for dec in func.decorator_list:
        if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute) or not dec.args:
            continue
        try:
            path = ast.literal_eval(dec.args[0])
        except ValueError:
            continue
        if not isinstance(path, str):
            continue
        name = dec.func.attr
        if name in METHODS:
            found.append((path, name))
        elif name == 'route':
            methods = next((k.value for k in dec.keywords if k.arg == 'methods'), None)
            for m in (ast.literal_eval(methods) if methods is not None else ['GET']):
                found.append((path, m.lower()))
    return found


def _openapi_path(path):
    if path.startswith('/api/v1'):
        path = path[len('/api/v1'):] or '/'
    elif not path.startswith('/') or path.startswith('/api/'):
        return None
    return re.sub(r'<(?:[a-z_]+:)?([A-Za-z_][A-Za-z_0-9]*)>', r'{\1}', path)


def collect():
    """{(path, method): [(required, optional), ...]}"""
    result = {}
    for file in sorted(ROOT.glob('*.py')):
        if file.name.startswith('test_'):
            continue
        tree = ast.parse(file.read_text(encoding='utf-8'), filename=str(file))
        for func in ast.walk(tree):
            if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            routes = _routes(func)
            if not routes:
                continue
            sets = []
            for node in ast.walk(func):
                if isinstance(node, ast.Call) and (getattr(node.func, 'id', '') == 'json_object'
                                                   or getattr(node.func, 'attr', '') == 'json_object'):
                    for item in _field_sets(node, func):
                        if item not in sets:
                            sets.append(item)
            if not sets:
                continue
            for path, method in routes:
                api_path = _openapi_path(path)
                if api_path is not None:
                    result.setdefault((api_path, method), [])
                    for item in sets:
                        if item not in result[(api_path, method)]:
                            result[(api_path, method)].append(item)
    return result


def _clean(schema):
    """pydantic property schema -> OpenAPI 3.1 property: no titles/defaults; Optional[x] -> x."""
    schema = {k: v for k, v in schema.items() if k not in ('title', 'default')}
    if 'anyOf' in schema:
        options = [o for o in schema['anyOf'] if o != {'type': 'null'}]
        if len(options) == 1:
            rest = {k: v for k, v in schema.items() if k != 'anyOf'}
            schema = {**_clean(options[0]), **rest}
    return schema


def merged(existing, required, optional):
    """The enforced schema, keeping the document's own descriptions/constraints/examples."""
    generated = request_schemas.model_for(required, optional).model_json_schema()
    existing = existing if isinstance(existing, dict) and 'oneOf' not in existing else {}
    old_props = existing.get('properties', {}) if isinstance(existing.get('properties'), dict) else {}
    properties = {}
    for name, prop in generated.get('properties', {}).items():
        enforced = _clean(prop)
        documented = old_props.get(name, {}) if isinstance(old_props.get(name), dict) else {}
        if 'type' in enforced or '$ref' in enforced:
            # enforced type wins; documented wording, enums and bounds are kept
            properties[name] = {**documented, **{k: v for k, v in enforced.items()
                                                 if k == 'type' or k not in documented}}
        else:
            properties[name] = documented
    schema = {k: v for k, v in existing.items() if k not in ('type', 'properties', 'required', 'additionalProperties')}
    result = {'type': 'object', **schema, 'properties': properties, 'additionalProperties': False}
    if required:
        result['required'] = sorted(required)
    return result


def stub(path, method):
    """A new route's operation, with the contract every operation carries (operationId, 200, 400, 401)."""
    words = [w for w in re.split(r'[^A-Za-z0-9]+', path) if w and not w.startswith('{')]
    op_id = method + ''.join(w[:1].upper() + w[1:] for w in words)
    error = {'content': {'application/json': {'schema': {'$ref': '#/components/schemas/Error'}}}}
    return {'x-generated': True, 'operationId': op_id, 'responses': {
        '200': {'description': 'Actor-scoped result in the data/error envelope.'},
        '400': {'description': 'Invalid strict JSON body.', **error},
        '401': {'description': 'Authentication required.', **error}}}


def build(doc):
    doc = json.loads(json.dumps(doc))
    for (path, method), sets in sorted(collect().items()):
        operation = doc.setdefault('paths', {}).setdefault(path, {}).setdefault(method, stub(path, method))
        body = operation.setdefault('requestBody', {})
        body['required'] = True
        content = body.setdefault('content', {}).setdefault('application/json', {})
        current = content.get('schema', {})
        if len(sets) == 1:
            content['schema'] = merged(current, *sets[0])
        else:
            content['schema'] = {'oneOf': [merged({}, r, o) for r, o in sets]}
    return doc


def render(doc):
    return json.dumps(doc, indent=2) + '\n'   # same style as the hand-maintained file (ASCII escapes)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args(argv)
    current = DOC.read_text(encoding='utf-8')
    fresh = render(build(json.loads(current)))
    if args.check:
        if fresh != current:
            print('docs/openapi-phase4.json is out of date: run python tools/gen_openapi_schemas.py')
            return 1
        print('OpenAPI request schemas are up to date.')
        return 0
    DOC.write_text(fresh, encoding='utf-8')
    print(f'Wrote {DOC.relative_to(ROOT)}: {len(collect())} operations with request schemas.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
