"""Supplied standalone Face Match contract. Does not establish liveness."""
import math
import re
from urllib.parse import urlsplit

PATH='/face/match'

def image_url(value):
    if not isinstance(value,str) or len(value)>4096 or any(ord(c)<33 for c in value):raise ValueError('Use a private HTTPS image URL')
    try:
        parsed=urlsplit(value)
        if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password or parsed.fragment or parsed.port not in (None,443):raise ValueError()
    except ValueError:raise ValueError('Use a valid HTTPS image URL without credentials or fragments') from None
    if '<' in value or '>' in value:raise ValueError('Replace image URL placeholders')
    return value

def payload(values):
    if not isinstance(values,dict) or not {'firstImage','secondImage','threshold'}<=set(values) or set(values)-{'firstImage','secondImage','threshold','detectMask'}:raise ValueError('Provide firstImage, secondImage and threshold')
    threshold=values['threshold']
    if type(threshold) not in (int,float) or not math.isfinite(threshold) or not .05<=threshold<=.95:raise ValueError('Use a numeric threshold between 0.05 and 0.95')
    result={'firstImage':image_url(values['firstImage']),'secondImage':image_url(values['secondImage']),'threshold':threshold}
    if 'detectMask' in values:
        if type(values['detectMask']) is not list or len(values['detectMask'])>2:raise ValueError('Use at most the two source images for mask detection')
        result['detectMask']=[image_url(x) for x in values['detectMask']]
        if any(x not in (result['firstImage'],result['secondImage']) for x in result['detectMask']):raise ValueError('Mask detection must use the supplied source pair')
    return result

def summarize(status,body):
    result=body.get('result') if isinstance(body,dict) else None
    shaped=status==200 and isinstance(body,dict) and body.get('status')==200 and isinstance(result,dict) and type(result.get('verified')) is bool
    score=None
    if shaped:
        value=result.get('matchPercentage')
        if isinstance(value,str) and re.fullmatch(r'\d{1,3}(?:\.\d+)?%',value):
            parsed=float(value[:-1])
            if 0<=parsed<=100:score=parsed
        shaped=score is not None and isinstance(result.get('maskDetections'),list)
    return {'outcome':('face_match_passed' if result['verified'] else 'face_match_failed') if shaped else 'response_received_contract_review_required' if status==200 else 'request_failed_or_unexpected_response',
        'face_match_passed':result['verified'] if shaped else None,'match_percentage':score if shaped else None,
        'liveness_checked':False,'automatic_verification':False}
