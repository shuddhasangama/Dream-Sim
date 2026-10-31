"""Court search step 2: fetch the outcome of an earlier search by caseId.
Never concludes clearance. A 404 must not be read as 'no cases'."""
import re

PATH = '/individual/result'


def payload(values):
    if not isinstance(values, dict) or set(values) != {'caseId'}:
        raise ValueError('caseId is required')
    case_id = values['caseId']
    if not isinstance(case_id, str) or not re.fullmatch(r'[A-Za-z0-9_\-]{8,120}', case_id.strip()):
        raise ValueError('Invalid caseId format')
    return {'caseId': case_id.strip()}


def summarize(status, body):
    cases = body.get('cases') if isinstance(body, dict) else None
    shaped = status == 200 and isinstance(cases, list)
    total = body.get('total') if isinstance(body, dict) else None
    result = {'outcome': ('response_received_review_required' if shaped else
                          'response_received_contract_review_required' if status == 200 else
                          'request_failed_or_unexpected_response'),
              'cases_returned': len(cases) if shaped else None,
              'total_reported': total if shaped and type(total) is int else None,
              'court_clearance': 'not_evaluated', 'automatic_verification': False}
    if status == 404:
        result['diagnostic'] = 'record_not_found_meaning_unconfirmed_not_a_clearance'
    return result
