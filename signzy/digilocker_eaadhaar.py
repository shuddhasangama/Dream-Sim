"""Fetch only the requested Aadhaar data; no document/image downloads."""
from .digilocker_create_url import identifier

PATH = '/digilocker-v2/geteAadhaar'

def payload(values):
    if not isinstance(values,dict) or set(values)!={'requestId'}:
        raise ValueError('A requestId from the completed consent session is required')
    # Preserve the supplied contract's string type for this switch.
    return {'requestId':identifier(values['requestId']),'extraDigitalCertificateParams':'false',
            'getEAadhaarPdf':False,'getEAadhaarJpeg':False}

def identity_fields(body):
    result=body.get('result') if isinstance(body,dict) else None
    if not isinstance(result,dict):return {}
    return {k:result[k] for k,limit in [('name',200),('dob',40),('address',2000)]
            if isinstance(result.get(k),str) and result[k].strip() and len(result[k])<=limit}

def summarize(status,body):
    fields=identity_fields(body) if status==200 else {}
    return {'outcome':'identity_data_received_review_required' if len(fields)==3 else
            'accepted_pending_confirmation' if status==202 else
            'response_received_contract_review_required' if status==200 else 'request_failed_or_unexpected_response',
            'name_received':'name' in fields,'dob_received':'dob' in fields,'address_received':'address' in fields,
            'automatic_verification':False}
