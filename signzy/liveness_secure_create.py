"""Hosted Liveness Secure createUrl contract supplied by Signzy."""
from .face_match import image_url

PATH = '/liveness-secure/createUrl'


def payload(values):
    required = {'matchImage', 'faceMatchThreshold', 'piiDeletionTTL'}
    optional = {'callbackUrl', 'redirectUrl'}
    if not isinstance(values, dict) or not required <= values.keys() or set(values) - required - optional:
        raise ValueError('Provide matchImage, faceMatchThreshold and piiDeletionTTL')
    images = values['matchImage']
    if not isinstance(images, list) or len(images) != 1:
        raise ValueError('Use one consented Aadhaar portrait URL for this test')
    threshold = values['faceMatchThreshold']
    if type(threshold) not in (int, float) or not .05 <= threshold <= .95:
        raise ValueError('Threshold must be a number from 0.05 to 0.95')
    ttl = values['piiDeletionTTL']
    if not isinstance(ttl, str) or not ttl.strip() or len(ttl) > 60 or any(ord(c) < 32 for c in ttl):
        raise ValueError('Provide the Signzy retention value to test')
    result = {'languageCode': 'en', 'hideBottomLogo': 'false', 'accentColor': '#000000',
        'matchImage': [image_url(images[0])], 'reviewImage': 'true', 'additionalChecks': 'true',
        'allowCameraSwitch': 'true', 'faceMatchThreshold': threshold,
        'piiDeletionTTL': ttl, 'backgroundColor': 'transparent'}
    for name in optional:
        if values.get(name):
            result[name] = image_url(values[name])
    return result


def session(body):
    result = body.get('result', body) if isinstance(body, dict) else None
    if not isinstance(result, dict):
        raise ValueError('Session response requires review')
    token = result.get('token')
    if not isinstance(token, str) or not token or len(token) > 512 or any(ord(c) < 33 for c in token):
        raise ValueError('No valid session token returned')
    url = image_url(result.get('videoUrl'))
    return token, url, result.get('consumerId')


def summarize(status, body):
    try:
        session(body)
        valid = 200 <= status < 300
    except (ValueError, TypeError):
        valid = False
    return {'outcome': 'capture_link_created' if valid else 'response_received_contract_review_required',
        'capture_link_received': valid, 'automatic_verification': False}
