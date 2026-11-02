"""DigiLocker consent-link creation using the supplied preproduction contract."""
import re
from urllib.parse import urlsplit

PATH = '/digilocker-v2/createUrl'

def https_url(value):
    if not isinstance(value,str) or len(value)>2048 or any(ord(c)<32 for c in value):
        raise ValueError('A valid HTTPS callback URL is required')
    parsed=urlsplit(value)
    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment or '<' in value or '>' in value:
        raise ValueError('Use an actual HTTPS callback URL, not the example placeholder')
    return value

def identifier(value):
    if not isinstance(value,str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,120}',value):
        raise ValueError('Invalid DigiLocker request identifier')
    return value

def payload(values):
    if not isinstance(values,dict) or set(values)!={'callbackUrl','internalId','serviceName'}:
        raise ValueError('callbackUrl, internalId and serviceName are required')
    service=values['serviceName']
    if not isinstance(service,str) or not service.strip() or len(service)>120 or any(ord(c)<32 for c in service):
        raise ValueError('Use the service name registered with Signzy')
    return {'signup':True,'callbackUrl':https_url(values['callbackUrl']),
            'successRedirectUrl':'https://dhashu.com/','successRedirectTime':'5',
            'failureRedirectUrl':'https://dhashu.com/','failureRedirectTime':'5',
            'logoVisible':'true','logo':'https://dhashu.com/media/dhashu-logo.png','docType':['ADHAR'],'purpose':'kyc',
            'serviceName':service.strip(),'getScope':True,'internalId':identifier(values['internalId']),
            'getBase64Files':False,'getEAadhaarPdf':False,'getEAadhaarJpeg':False}

def session(body):
    result=body.get('result') if isinstance(body,dict) else None
    if not isinstance(result,dict):raise ValueError('DigiLocker session response requires review')
    request_id=identifier(result.get('requestId'))
    url=https_url(result.get('url'))
    if urlsplit(url).hostname not in {'api.digitallocker.gov.in','digilocker.meripehchaan.gov.in','digilocker.signzy.tech'}:
        raise ValueError('Unexpected consent-link host; review before opening')
    return request_id,url

def summarize(status,body):
    try:session(body);valid=True
    except ValueError:valid=False
    return {'outcome':'consent_link_created' if status==200 and valid else 'response_received_contract_review_required' if status==200 else 'request_failed_or_unexpected_response',
            'consent_link_received':status==200 and valid,'automatic_verification':False}
