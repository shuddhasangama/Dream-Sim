"""Current employer is evidence for review, never proof of unemployment."""
import re
from .pan_extensive import pan

PATH = '/employment-verification/current-employer'


def payload(values):
    if not isinstance(values, dict) or set(values) != {'mobile', 'panNumber'}:
        raise ValueError('Mobile and PAN are required')
    mobile = values['mobile']
    if not isinstance(mobile, str) or not re.fullmatch(r'[6-9][0-9]{9}', mobile):
        raise ValueError('Invalid mobile format')
    return {'mobile': mobile, 'panNumber': pan(values['panNumber'])}


def summarize(status, body):
    body = body if isinstance(body, dict) else {}
    data = body.get('employmentSummary')
    data = data if isinstance(data, dict) else {}
    code = body.get('resultCode')
    success = status == 200 and type(code) is int and code == 200
    return {'result_code': code if type(code) is int else None,
            'outcome': 'response_received_review_required' if success else 'request_failed_or_unexpected_response',
            'is_employed': data.get('is_employed') if success and type(data.get('is_employed')) is bool else None,
            'date_of_exit_marked': data.get('date_of_exit_marked') if success and type(data.get('date_of_exit_marked')) is bool else None,
            'employment_summary_present': bool(data), 'automatic_verification': False}
