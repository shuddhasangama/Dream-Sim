"""Twilio Verify HTTPS adapter. SendGrid email integration lives in Twilio.

No local OTP generation or simulation fallback. Never log provider payloads,
Authorization headers, destination addresses or submitted codes.
"""
import base64
import json
import http.client
import os
import re
import urllib.error
import urllib.parse
import urllib.request


class DeliveryUnavailable(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def configured():
    return bool(re.fullmatch(r'AC[0-9a-fA-F]{32}', os.environ.get('TWILIO_ACCOUNT_SID', ''))
                and re.fullmatch(r'VA[0-9a-fA-F]{32}', os.environ.get('TWILIO_VERIFY_SERVICE_SID', ''))
                and os.environ.get('TWILIO_AUTH_TOKEN'))


def _post(resource, body):
    if not configured():
        raise DeliveryUnavailable('Verification delivery is not configured.')
    service = os.environ['TWILIO_VERIFY_SERVICE_SID']
    credential = (os.environ['TWILIO_ACCOUNT_SID'] + ':' + os.environ['TWILIO_AUTH_TOKEN']).encode()
    request = urllib.request.Request(
        'https://verify.twilio.com/v2/Services/' + service + '/' + resource,
        data=urllib.parse.urlencode(body).encode(), method='POST',
        headers={'Authorization': 'Basic ' + base64.b64encode(credential).decode(),
                 'Content-Type': 'application/x-www-form-urlencoded'})
    try:
        with urllib.request.build_opener(NoRedirect()).open(request, timeout=10) as response:
            result = json.loads(response.read(65536))
            if not isinstance(result, dict):
                raise DeliveryUnavailable('Verification service unavailable.')
            return result
    except urllib.error.HTTPError as exc:
        code = exc.code
        exc.close()
        if resource == 'VerificationCheck' and code in (400, 404):
            return {'status': 'denied'}
        raise DeliveryUnavailable('Verification service unavailable.') from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, http.client.HTTPException):
        raise DeliveryUnavailable('Verification service unavailable.') from None


def start(channel, destination):
    result = _post('Verifications', {'To': destination, 'Channel': 'sms' if channel == 'phone' else 'email'})
    sid = result.get('sid', '')
    if result.get('status') != 'pending' or not isinstance(sid, str) or not re.fullmatch(r'VE[0-9a-fA-F]{32}', sid):
        raise DeliveryUnavailable('Verification service unavailable.')
    return sid


def check(sid, code):
    result = _post('VerificationCheck', {'VerificationSid': sid, 'Code': code})
    return result.get('status') == 'approved' and result.get('sid') == sid
