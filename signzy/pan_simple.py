"""PAN Simple contract supplied by the user; exact individual matching only."""
from datetime import date
from .pan_extensive import pan

PATH = '/pan/simple'

def payload(values):
    if not isinstance(values, dict) or set(values) != {'panNumber'}:
        raise ValueError('PAN Simple requires only panNumber')
    return {'panNumber': pan(values['panNumber'])}

def valid_result(body):
    result = body.get('result') if isinstance(body, dict) else None
    if not isinstance(result, dict) or result.get('panStatus') != 'VALID':
        return False
    if not isinstance(result.get('name'), str) or not result['name'].strip():
        return False
    try:
        date.fromisoformat(result['dob'])
    except (KeyError, TypeError, ValueError):
        return False
    return True

def summarize(status, body):
    result = body.get('result', {}) if isinstance(body, dict) else {}
    result = result if isinstance(result, dict) else {}
    state = result.get('panStatus')
    return {'outcome': ('response_received_review_required' if status == 200 and valid_result(body)
                       else 'invalid_pan' if status == 200 and state == 'INVALID'
                       else 'request_failed_or_unexpected_response'),
            'pan_status': state if state in ('VALID', 'INVALID') else None,
            'automatic_verification': False}
