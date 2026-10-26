"""Provider-neutral biometric contract and isolated rehearsal.

Signzy field names follow the supplied Face Smart example. No undocumented
endpoint, authentication scheme, image hosting or live transport is assumed.
"""
from dataclasses import dataclass, field
from typing import Protocol
from urllib.parse import urlsplit
import math


@dataclass(frozen=True)
class Request:
    selfie_url: str = field(repr=False)
    reference_url: str = field(repr=False)
    threshold: float = 0.7
    strict: bool = True

    def validate(self):
        if type(self.threshold) not in (int, float) or not math.isfinite(self.threshold) or not 0 < self.threshold < 1:
            raise ValueError('Invalid face-match threshold')
        if type(self.strict) is not bool:
            raise ValueError('Strict mode must be boolean')
        for url in (self.selfie_url, self.reference_url):
            parts = urlsplit(url)
            if parts.scheme != 'https' or not parts.hostname or parts.username or parts.password or parts.fragment:
                raise ValueError('Private HTTPS evidence URLs are required')


@dataclass(frozen=True)
class Result:
    state: str
    liveness_passed: bool | None = None
    match_passed: bool | None = None
    reason: str = ''


class Provider(Protocol):
    def verify(self, request: Request) -> Result: ...


class SignzySmart:
    """Pure request/response adapter; deliberately no callable live transport."""
    @staticmethod
    def payload(request):
        request.validate()
        return {'livenessImage': request.selfie_url, 'faceMatchImage': request.reference_url,
                'livenessStrictMode': request.strict, 'faceMatchThreshold': request.threshold}

    @staticmethod
    def parse(body, http_status=200):
        # Never persist the provider's echoed image URLs or free-form messages.
        if http_status != 200 or not isinstance(body, dict):
            return Result('review_required', reason='provider_error')
        if body.get('code') != 'S001' or body.get('reason') != 'REQUEST_SUCCESSFUL':
            return Result('review_required', reason='provider_error')
        result = body.get('result')
        if not isinstance(result, dict):
            return Result('review_required', reason='invalid_response')
        live, match = result.get('liveness'), result.get('match')
        if not isinstance(live, dict) or not isinstance(match, dict):
            return Result('review_required', reason='invalid_response')
        a, b = live.get('liveness'), match.get('verified')
        if type(a) is not bool or type(b) is not bool:
            return Result('review_required', reason='invalid_response')
        # Additional score/quality thresholds await the provider contract.
        if not a:
            return Result('retry_required', a, b, 'liveness_failed')
        if not b:
            return Result('review_required', a, b, 'face_mismatch')
        return Result('passed', a, b, 'both_checks_passed')


class Simulator:
    def __init__(self, scenario='pass'):
        if scenario not in ('pass','liveness_failed','face_mismatch','malformed','timeout'):
            raise ValueError('Unknown simulator scenario')
        self.scenario = scenario

    def verify(self, request):
        request.validate()
        if self.scenario == 'timeout':
            return Result('pending', reason='outcome_unknown')
        if self.scenario == 'malformed':
            return SignzySmart.parse({})
        return SignzySmart.parse({'code':'S001','reason':'REQUEST_SUCCESSFUL','result':{
            'liveness':{'liveness':self.scenario != 'liveness_failed'},
            'match':{'verified':self.scenario != 'face_mismatch'}}})


if __name__ == '__main__':
    import argparse
    import json
    from dataclasses import asdict
    parser=argparse.ArgumentParser(description='Offline biometric contract rehearsal; no network or database writes.')
    parser.add_argument('--scenario',default='pass',choices=['pass','liveness_failed','face_mismatch','malformed','timeout'])
    args=parser.parse_args()
    print(json.dumps({'mode':'simulation','real_identity_verified':False,**asdict(
        Simulator(args.scenario).verify(Request('https://example.invalid/a','https://example.invalid/b')))},indent=2))
