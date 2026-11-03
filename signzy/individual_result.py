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
    from .legal_result import normalized,pending
    data,envelope=normalized(body)
    waiting=pending(status,data)
    cases=data.get('cases')
    # Preserve the legacy documented cases-list response without a status field.
    shaped=(status==200 and envelope and not waiting and isinstance(cases,list)
            and all(isinstance(row,dict) for row in cases)
            and ('status' not in data or type(data['status']) is int and data['status']==1))
    total=data.get('total')
    result={'outcome':'accepted_pending_confirmation' if waiting else
            'response_received_review_required' if shaped else
            'response_received_contract_review_required' if status==200 else 'request_failed_or_unexpected_response',
            'processing_complete':shaped,'cases_returned':len(cases) if shaped else None,
            'total_reported':total if shaped and type(total)is int and total>=0 else None,
            'court_clearance':'not_evaluated','automatic_verification':False}
    if status==404:result['diagnostic']='record_not_found_meaning_unconfirmed_not_a_clearance'
    return result
