"""Retrieve FIR candidates; pending/empty results never imply clearance."""
from .fir_search import identifier

PATH = '/fir/result'


def payload(values):
    if not isinstance(values, dict) or set(values) != {'verifyId'}:
        raise ValueError('FIR result requires verifyId')
    return {'verifyId': identifier(values['verifyId'])}


def summarize(status, body):
    body = body if isinstance(body, dict) else {}
    cases = body.get('cases')
    done = (status == 200 and type(body.get('status')) is int and body['status'] == 1
            and body.get('message') == 'Processing done'
            and isinstance(cases, list) and all(isinstance(row, dict) for row in cases))
    pending = status == 202 or (status == 200 and isinstance(body.get('message'), str)
                               and body['message'].strip().casefold() in ('processing', 'processing pending', 'in progress'))
    total = body.get('numresults')
    return {'outcome': ('response_received_review_required' if done else
                        'accepted_pending_confirmation' if pending else
                        'response_received_contract_review_required' if status == 200 else
                        'request_failed_or_unexpected_response'),
            'processing_complete': done,
            'candidates_returned': len(cases) if done else None,
            'numresults_reported': total if done and type(total) is int and total >= 0 else None,
            'fir_clearance': 'not_evaluated', 'automatic_verification': False}
