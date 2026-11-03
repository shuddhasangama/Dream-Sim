"""Retrieve FIR candidates; pending/empty results never imply clearance."""
from .fir_search import identifier

PATH = '/fir/result'


def payload(values):
    if not isinstance(values, dict) or set(values) != {'verifyId'}:
        raise ValueError('FIR result requires verifyId')
    return {'verifyId': identifier(values['verifyId'])}


def summarize(status, body):
    from .legal_result import normalized,pending
    data,envelope=normalized(body)
    cases=data.get('cases')
    waiting=pending(status,data)
    done=(status==200 and envelope and not waiting and type(data.get('status'))is int and data['status']==1
          and data.get('message')=='Processing done' and isinstance(cases,list)
          and all(isinstance(row,dict) for row in cases))
    # Sandbox has returned numResults; retain compatibility with the earlier contract.
    counts=[data[k] for k in ('numResults','numresults') if k in data]
    total=counts[0] if counts and all(type(v)is int and v>=0 and v==counts[0] for v in counts) else None
    reported=data.get('total')
    discrepancy=done and (any(type(v)is not int or v<0 or v!=len(cases) for v in counts)
                          or type(reported)is int and reported!=len(cases))
    return {'outcome':'accepted_pending_confirmation' if waiting else
            'response_received_review_required' if done else
            'response_received_contract_review_required' if status==200 else 'request_failed_or_unexpected_response',
            'processing_complete':done,'completion_confirmed':done,'candidates_returned':len(cases) if done else None,
            'numresults_reported':total if done else None,'provider_count_discrepancy':bool(discrepancy),
            'fir_clearance':'not_evaluated','automatic_verification':False}
