"""Supplied DigiLocker 2.0 Get Details contract; issued record IDs are not PAN verification."""
import re
from .digilocker_create_url import identifier
PATH = '/digilocker-v2/getDetails'
def payload(values):
    if not isinstance(values,dict) or set(values)!={'requestId'}:
        raise ValueError('A completed consent requestId is required')
    return {'requestId':identifier(values['requestId'])}
def documents(body):
    result=body.get('result') if isinstance(body,dict) else None
    if not isinstance(result,dict) or not isinstance(result.get('userDetails'),dict) or not isinstance(result.get('files'),list):
        raise ValueError('Unexpected DigiLocker details response')
    user=result['userDetails']; files=result['files']
    # Accept only the supplied issuer + document type + exact identifier structure.
    pans={f['id'].removeprefix('in.gov.pan-PANCR-') for f in files if isinstance(f,dict)
          and f.get('doctype')=='PANCR' and f.get('issuerid')=='in.gov.pan'
          and isinstance(f.get('id'),str) and re.fullmatch(r'in.gov.pan-PANCR-[A-Z]{5}[0-9]{4}[A-Z]',f['id']) and 'XXX' not in f['id']}
    mobile=user.get('mobile','')
    return {'pan':next(iter(pans)) if len(pans)==1 else None,
            'pan_state':'received' if len(pans)==1 else 'needs_review' if any(isinstance(f,dict) and f.get('doctype')=='PANCR' for f in files) else 'not_shared',
            'mobile':mobile if isinstance(mobile,str) and re.fullmatch(r'[6-9][0-9]{9}',mobile) else None,
            'name':user.get('name') if isinstance(user.get('name'),str) else None}
def summarize(status,body):
    try: data=documents(body) if status==200 else None
    except ValueError: data=None
    return {'outcome':'document_listing_received' if data else 'accepted_pending_confirmation' if status==202 else 'response_requires_review',
            'pan_state':data['pan_state'] if data else 'unavailable','automatic_verification':False}
