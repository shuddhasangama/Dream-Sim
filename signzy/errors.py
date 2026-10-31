"""Stable classifications; provider text stays in encrypted evidence only."""
def classify(status, body):
    body = body if isinstance(body, dict) else {}
    error = body.get('error')
    error = error if isinstance(error, dict) else {}
    message = str(error.get('message', body.get('message', ''))).lower()
    code = error.get('statusCode', status)
    kind = None
    if 'no api key' in message or 'authentication credentials' in message or status == 401:
        kind = 'authentication_failed'
    elif 'credit' in message and any(x in message for x in ('exhaust', 'insufficient', 'balance')):
        kind = 'credits_unavailable'
    elif status == 403:
        kind = 'access_denied'
    elif status == 429:
        kind = 'rate_limited'
    elif code == 409 and ('upstream' in message):
        kind = 'provider_unavailable'
    elif code == 400:
        kind = 'invalid_input'
    elif status and status >= 500:
        kind = 'provider_unavailable'
    elif error or (status and status >= 400):
        kind = 'provider_error'
    if not kind:
        return {}
    return {'error_code': kind, 'outcome': 'request_failed',
            'retry_automatically': False, 'automatic_verification': False}
