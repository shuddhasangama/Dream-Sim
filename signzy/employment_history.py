"""Supplied employment-history contract; historical records require review."""
import re
from .pan_extensive import pan

PATH = '/underwriting/fetch-employment-history'
FIELDS = ('pan', 'mobile', 'uan', 'dob', 'employeeName')


def payload(values):
    if not isinstance(values, dict) or set(values) - set(FIELDS):
        raise ValueError('Unsupported employment-history fields')
    result = {}
    for key in FIELDS:
        value = values.get(key, '')
        if not isinstance(value, str):
            raise ValueError('Employment-history inputs must be strings')
        result[key] = value.strip()
    if not any(result[k] for k in ('pan', 'mobile', 'uan')):
        raise ValueError('Provide a consented PAN, mobile or UAN')
    if result['pan']:
        result['pan'] = pan(result['pan'])
    if result['mobile'] and not re.fullmatch(r'[6-9][0-9]{9}', result['mobile']):
        raise ValueError('Invalid mobile format')
    if result['uan'] and not re.fullmatch(r'[0-9]{12}', result['uan']):
        raise ValueError('UAN must contain exactly 12 digits')
    # Request DOB format and required field combinations are not supplied.
    # Preserve optional DOB verbatim; do not infer its format from response DOB.
    return result


def summarize(status, body):
    body = body if isinstance(body, dict) else {}
    records = body.get('result')
    shaped = isinstance(records, list) and all(
        isinstance(row, dict) and
        isinstance(row.get('establishmentName'), str) and bool(row['establishmentName'].strip())
        for row in records)
    details = body.get('additionalDetails')
    details = details if isinstance(details, dict) else {}
    limited = details.get('limitedOutput')
    return {
        'outcome': ('accepted_pending_confirmation' if status == 202 else
                    'response_received_review_required' if status == 200 and shaped else
                    'response_received_contract_review_required' if status == 200 else
                    'request_failed_or_unexpected_response'),
        'employment_records_returned': len(records) if status == 200 and shaped else None,
        'limited_output': limited if type(limited) is bool else None,
        'employment_history_verification': 'not_evaluated',
        'automatic_verification': False,
    }
