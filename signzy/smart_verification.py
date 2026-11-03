"""Supplied Face Smart contract; separate liveness and face-match outcomes.

    This adapter consumes existing vendor-hosted images; it is not an upload SDK.
"""
from urllib.parse import urlsplit

PATH='/face/smart-verification'
HOSTS={'persist.signzy.tech','preproduction-persist.signzy.tech'}

def image_url(value):
    if not isinstance(value,str) or len(value)>4096 or any(ord(c)<33 for c in value):
        raise ValueError('Use a private vendor image URL')
    parsed=urlsplit(value)
    if parsed.scheme!='https' or parsed.hostname not in HOSTS or parsed.username or parsed.password or parsed.fragment or parsed.port not in (None,443):
        raise ValueError('Use the confirmed Signzy HTTPS file host')
    if not parsed.path.startswith('/api/files/') or '/download/' not in parsed.path or 'xxxx' in value or '<' in value or '>' in value:
        raise ValueError('Use a real uploaded image reference, not a placeholder')
    return value

def payload(values):
    if not isinstance(values,dict) or set(values)!={'livenessImage','faceMatchImage','livenessStrictMode','faceMatchThreshold'}:
        raise ValueError('Selfie and reference-image URLs, strict mode and threshold are required')
    if values['livenessStrictMode'] is not True or type(values['faceMatchThreshold']) not in (int,float) or values['faceMatchThreshold'] != 0.7:
        raise ValueError('Only the supplied strict=true, threshold=0.7 contract is configured')
    return {'livenessImage':image_url(values['livenessImage']),'faceMatchImage':image_url(values['faceMatchImage']),
            'livenessStrictMode':True,'faceMatchThreshold':0.7}

def summarize(status,body):
    result=body.get('result') if isinstance(body,dict) else None
    result=result if isinstance(result,dict) else {}
    live=result.get('liveness'); match=result.get('match')
    live=live if isinstance(live,dict) else {}; match=match if isinstance(match,dict) else {}
    shaped=status==200 and isinstance(body,dict) and body.get('code')=='S001' and body.get('reason')=='REQUEST_SUCCESSFUL' and type(live.get('liveness')) is bool and type(match.get('verified')) is bool
    return {'outcome':'response_received_review_required' if shaped else 'accepted_pending_confirmation' if status==202 else 'response_received_contract_review_required' if status==200 else 'request_failed_or_unexpected_response',
            'liveness_passed':live.get('liveness') if shaped else None,
            'face_match_passed':match.get('verified') if shaped else None,
            'automatic_verification':False}
