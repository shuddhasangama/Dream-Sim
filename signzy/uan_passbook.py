"""Passbook pilot: no callback, no automatic retries or employment conclusions."""
import re
PATH = '/underwriting/uan-passbook-without-otp'

def payload(values):
    if not isinstance(values, dict) or set(values) - {'uan', 'consentFlag', 'ttl', 'cutOffTime', 'callBackUrl'}:
        raise ValueError('Unsupported passbook fields')
    uan = values.get('uan')
    if not isinstance(uan, str) or not re.fullmatch(r'[0-9]{12}', uan.strip()):
        raise ValueError('UAN must contain exactly 12 digits')
    if values.get('consentFlag') != 'Y':
        raise ValueError('Explicit consentFlag Y is required to fetch a passbook')
    result = {'uan': uan.strip(), 'consentFlag': 'Y'}
    ttl = values.get('ttl', 0)
    if type(ttl) is not int or not 0 <= ttl <= 30:
        raise ValueError('ttl must be an integer from 0 to 30 days')
    result['ttl'] = ttl
    if values.get('callBackUrl'):
        raise ValueError('Callback integration is not enabled in this local tester')
    cutoff = values.get('cutOffTime')
    if cutoff not in (None, ''):
        if not isinstance(cutoff, str) or not re.fullmatch(r'[0-9]+', cutoff) or int(cutoff) < 1:
            raise ValueError('cutOffTime must be a positive integer string in minutes')
        result['cutOffTime'] = cutoff
    return result

def summarize(status, body):
    result = body.get('result') if isinstance(body, dict) else None
    complete_shape = (isinstance(result, dict) and isinstance(result.get('uan'), str)
                      and isinstance(result.get('employers'), list)
                      and isinstance(result.get('name'), str))
    outcome = ('response_received_review_required' if status == 200 and complete_shape else
               'accepted_pending_confirmation' if status == 202 else
               'response_received_contract_review_required' if status == 200 else
               'request_failed_or_unexpected_response')
    return {'outcome': outcome, 'passbook_data_present': bool(complete_shape and status == 200),
            'automatic_verification': False}
