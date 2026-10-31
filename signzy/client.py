"""Explicit operation registry; isolated credentials; single request, no retries."""
from dataclasses import dataclass, field
import json
import os
import base64
import secrets
from datetime import datetime, timezone
import urllib.error
import urllib.request
from . import current_employer, pan_extensive, pan_simple, individual_search, individual_result, uan_passbook, employment_history
from .errors import classify
from . import fir_search, fir_result

BASES = {'preproduction': 'https://api-preproduction.signzy.app/api/v3',
         'production': 'https://api.signzy.app/api/v3'}
OPERATIONS = {'pan_extensive': pan_extensive, 'current_employer': current_employer, 'pan_simple': pan_simple}
OPERATIONS.update(individual_search=individual_search, individual_result=individual_result, uan_passbook=uan_passbook)
OPERATIONS['employment_history'] = employment_history
OPERATIONS.update(fir_search=fir_search, fir_result=fir_result)


@dataclass(frozen=True)
class Config:
    environment: str = 'preproduction'
    token: str = field(default='', repr=False)
    client_id: str = 'partners@dhashu.com'
    production_enabled: bool = False

    @classmethod
    def from_env(cls):
        environment = os.getenv('SIGNZY_ENV', 'preproduction')
        if environment not in BASES:
            raise ValueError('Unknown Signzy environment')
        prefix = 'SIGNZY_TEST_' if environment == 'preproduction' else 'SIGNZY_PRODUCTION_'
        return cls(environment, os.getenv(prefix + 'API_KEY', ''),
                   os.getenv(prefix + 'CLIENT_ID', 'partners@dhashu.com'),
                   os.getenv('SIGNZY_PRODUCTION_ENABLED', '0') == '1')

    def validate(self):
        if self.environment not in BASES:
            raise ValueError('Unknown Signzy environment')
        if self.environment == 'production' and self.production_enabled is not True:
            raise ValueError('Production is disabled')
        for value in (self.token, self.client_id):
            if not value or any(ord(c) < 32 or ord(c) > 126 for c in value):
                raise ValueError('Missing or invalid Signzy configuration')
        if self.token.startswith('<'):
            raise ValueError('Replace the API key placeholder')


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class Client:
    def __init__(self, config):
        config.validate()
        self.config = config

    def execute(self, operation, values, *, consent_confirmed=False, evidence_sink=None):
        if consent_confirmed is not True:
            raise ValueError('Explicit consent confirmation required')
        if operation not in OPERATIONS:
            raise ValueError('Unknown Signzy operation')
        adapter = OPERATIONS[operation]
        body = adapter.payload(values)
        evidence = {'schema_version': 1, 'receipt_id': secrets.token_hex(16),
                    'started_at_utc': datetime.now(timezone.utc).isoformat(),
                    'operation': operation, 'environment': self.config.environment,
                    'request': {'method': 'POST', 'endpoint': BASES[self.config.environment] + adapter.PATH,
                                'input_fields': body},
                    'provider_response': None, 'comparison': {'status': 'not_evaluated'},
                    'consent_confirmed_by_operator': True}
        receipt = {'operation': operation, 'environment': self.config.environment,
                   'http_status': None, 'automatic_verification': False,
                   'endpoint': BASES[self.config.environment] + adapter.PATH}
        receipt['receipt_id'] = evidence['receipt_id']

        def finish():
            evidence['finished_at_utc'] = datetime.now(timezone.utc).isoformat()
            evidence['wrapper_summary'] = dict(receipt)
            if evidence_sink:
                try:
                    evidence_sink(evidence)
                except Exception:
                    raise ValueError('Request already attempted but private receipt save failed. Do not rerun; inspect Signzy logs.') from None
            return receipt
        request = urllib.request.Request(BASES[self.config.environment] + adapter.PATH,
            json.dumps(body).encode(), {'Authorization': self.config.token,
            'x-client-unique-id': self.config.client_id, 'Content-Type': 'application/json',
            'User-Agent': 'DhaShu-Signzy/0.1'}, method='POST')
        try:
            try:
                response = urllib.request.build_opener(NoRedirect()).open(request, timeout=45)
            except urllib.error.HTTPError as exc:
                response = exc
            with response:
                receipt['http_status'] = response.code
                if response.code == 403:
                    receipt['diagnostic'] = 'access_denied_reason_unconfirmed_check_signzy_api_logs'
                elif response.code == 401:
                    receipt['diagnostic'] = 'authentication_rejected_check_environment_credentials'
                raw = response.read(2_000_001)
                headers = getattr(response, 'headers', {})
                evidence['provider_response'] = {
                    'http_status': response.code,
                    'headers': {k: headers.get(k) for k in ('Content-Type', 'Date', 'x-request-id', 'x-trace-id', 'trace-id') if headers.get(k)},
                    'body_base64': base64.b64encode(raw).decode(),
                    'body_complete': len(raw) <= 2_000_000,
                    'json': None}
            if len(raw) > 2_000_000:
                raise ValueError('Oversized response')
            parsed = json.loads(raw)
            evidence['provider_response']['json'] = parsed
        except (urllib.error.URLError, TimeoutError, OSError):
            receipt['outcome'] = 'transport_error_outcome_unknown'
            receipt['error_code'] = 'network_error_outcome_unknown'
            receipt['retry_automatically'] = False
            return finish()
        except (ValueError, UnicodeError):
            receipt['outcome'] = 'invalid_or_oversized_response'
            return finish()
        receipt.update(adapter.summarize(receipt['http_status'], parsed))
        receipt.update(classify(receipt['http_status'], parsed))
        return finish()
