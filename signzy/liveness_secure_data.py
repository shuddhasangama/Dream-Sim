"""Liveness and face match remain independent; no app approval is granted."""
import re

PATH = '/liveness-secure/getData'


def payload(values):
    if not isinstance(values, dict) or set(values) != {'token'}:
        raise ValueError('Only the token from this createUrl session is required')
    token = values['token']
    if not isinstance(token, str) or not token or len(token) > 512 or any(ord(c) < 33 for c in token):
        raise ValueError('Invalid session token')
    return {'token': token}


def summarize(status, body):
    result = body.get('result') if isinstance(body, dict) else None
    answer = {'outcome': 'response_received_contract_review_required', 'liveness_passed': None,
        'face_match_passed': None, 'match_percentage': None, 'provider_status': None,
        'additional_checks_passed': None, 'combined_passed': None, 'automatic_verification': False}
    if not 200 <= status < 300 or not isinstance(result, dict):
        return answer
    used = result.get('isUsed')
    if type(used) is int and used == 0:
        return {**answer, 'outcome': 'capture_not_completed'}
    live = result.get('passiveLiveliness')
    face = result.get('faceMatch')
    extra = result.get('additionalChecks')
    live = live if isinstance(live, dict) else {}
    face = face if isinstance(face, dict) else {}
    extra = extra if isinstance(extra, dict) else {}
    for name, value in [('liveness_passed', live.get('liveness')), ('face_match_passed', face.get('verified')),
                        ('provider_status', result.get('status')), ('additional_checks_passed', extra.get('status'))]:
        if type(value) is bool:
            answer[name] = value
    score = face.get('matchPercentage')
    if isinstance(score, str) and re.fullmatch(r'\d{1,3}(?:\.\d+)?%', score):
        value = float(score[:-1])
        if 0 <= value <= 100:
            answer['match_percentage'] = value
    checks = [answer[k] for k in ('liveness_passed', 'face_match_passed', 'provider_status', 'additional_checks_passed')]
    if type(used) is int and used == 1 and all(type(x) is bool for x in checks) and answer['match_percentage'] is not None:
        answer['combined_passed'] = all(checks)
        answer['outcome'] = 'liveness_and_face_match_passed' if all(checks) else 'completed_checks_not_passed'
    return answer
