"""Response trimming safety net (c-security-suite).

Handlers already build responses from allow-lists (api_contract.allowlist). This
is the second layer: any API JSON response that still carries a secret-bearing
key (password or token hashes, encrypted blobs, blind indexes, authenticator
secrets, provider session ids, an admin's lock reason) has that key removed
before it leaves, and a structured 'response_trimmed' event names the route and
key so the handler can be fixed. Cheap: the body is only parsed when a marker
substring is present.
"""
import json
import logging
import re

from flask import request

log = logging.getLogger('dhashu.abuse')

EXACT = {'password_hash', 'access_hash', 'csrf_hash', 'refresh_hash', 'protected_totp', 'totp_secret',
         'phone_index', 'lock_reason', 'provider_sid', 'image_ciphertext', 'secret', 'api_key'}
PATTERN = re.compile(r'^(protected_\w+|\w+_ciphertext|\w+_password_hash|\w+_token_hash)$')
MARKERS = tuple(m.encode() for m in ('_hash"', 'protected_', 'phone_index', 'lock_reason', 'provider_sid',
                                     'ciphertext', '"secret"', 'totp', 'api_key'))


def sensitive(key):
    return key in EXACT or bool(PATTERN.match(key))


def trim(value, removed, path=''):
    if isinstance(value, dict):
        out = {}
        for key, item in value.items():
            if isinstance(key, str) and sensitive(key):
                removed.append((path + '.' + key).lstrip('.'))
                continue
            out[key] = trim(item, removed, path + '.' + str(key))
        return out
    if isinstance(value, list):
        return [trim(item, removed, path + '[]') for item in value]
    return value


def register(app):
    @app.after_request
    def trim_response(response):
        if not request.path.startswith('/api/') or response.mimetype != 'application/json' or response.direct_passthrough:
            return response
        body = response.get_data()
        if not any(marker in body for marker in MARKERS):
            return response
        try:
            data = json.loads(body)
        except ValueError:
            return response
        removed = []
        cleaned = trim(data, removed)
        if removed:
            response.set_data(json.dumps(cleaned))
            log.warning(json.dumps({'event': 'response_trimmed', 'route': request.url_rule.rule if request.url_rule else 'unmatched',
                                    'keys': sorted(set(removed))[:20]}, sort_keys=True))
        return response
