"""PAN request contract supplied by Signzy customer portal; response pending."""
import re

PATH = '/panextensive'


def pan(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Z]{5}[0-9]{4}[A-Z]', value.strip().upper()):
        raise ValueError('Invalid PAN format')
    return value.strip().upper()


def payload(values):
    if not isinstance(values, dict) or set(values) - {'panNumber', 'getStatusInfo'}:
        raise ValueError('Unsupported PAN request fields')
    result = {'panNumber': pan(values.get('panNumber'))}
    if 'getStatusInfo' in values:
        if type(values['getStatusInfo']) is not bool:
            raise ValueError('getStatusInfo must be boolean')
        result['getStatusInfo'] = values['getStatusInfo']
    return result


def summarize(status, body):
    return {'outcome': 'response_received_contract_review_required' if status == 200 and isinstance(body, dict) else 'request_failed_or_unexpected_response',
            'name_match': 'not_evaluated', 'dob_match': 'not_evaluated',
            'automatic_verification': False}
