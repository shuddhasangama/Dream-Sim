"""HTTPS OTP adapters. MSG91 is the primary SMS provider (owner decision 2026-11-27):
sign-up, sign-in and resend all send through MSG91 SendOTP unless DHASHU_SMS_PROVIDER
is set to 'twilio' (optional fallback; Twilio settings are never required otherwise).

MSG91 settings: MSG91_AUTH_KEY (authkey header) and MSG91_TEMPLATE_ID (the 24-hex
MSG91 OTP template id). The DLT-registered template id and the approved sender id are
attached to that template in the MSG91 dashboard; SendOTP selects them through
MSG91_TEMPLATE_ID, so they are not sent per request.

No local OTP generation or simulation fallback. Never log provider payloads,
Authorization headers, destination addresses or submitted codes.
"""
import resilience
import base64
import json
import http.client
import os
import re
import urllib.error
import urllib.parse
import urllib.request


class DeliveryUnavailable(Exception):
    def __init__(self, message, *, http_status=None, provider_code=None):
        super().__init__(message)
        self.http_status = http_status
        self.provider_code = provider_code



class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _twilio_configured():
    return bool(re.fullmatch(r'AC[0-9a-fA-F]{32}', os.environ.get('TWILIO_ACCOUNT_SID', ''))
                and re.fullmatch(r'VA[0-9a-fA-F]{32}', os.environ.get('TWILIO_VERIFY_SERVICE_SID', ''))
                and os.environ.get('TWILIO_AUTH_TOKEN'))


def _post(resource, body):
    if not _twilio_configured():
        raise DeliveryUnavailable('Verification delivery is not configured.')
    service = os.environ['TWILIO_VERIFY_SERVICE_SID']
    credential = (os.environ['TWILIO_ACCOUNT_SID'] + ':' + os.environ['TWILIO_AUTH_TOKEN']).encode()
    request = urllib.request.Request(
        'https://verify.twilio.com/v2/Services/' + service + '/' + resource,
        data=urllib.parse.urlencode(body).encode(), method='POST',
        headers={'Authorization': 'Basic ' + base64.b64encode(credential).decode(),
                 'Content-Type': 'application/x-www-form-urlencoded'})
    try:
        with resilience.call('twilio', urllib.request.build_opener(NoRedirect()).open, request, timeout=10) as response:
            result = json.loads(response.read(65536))
            if not isinstance(result, dict):
                raise DeliveryUnavailable('Verification service unavailable.')
            return result
    except urllib.error.HTTPError as exc:
        code = exc.code
        provider_code = None
        try:
            payload = json.loads(exc.read(65536))
            value = payload.get('code') if isinstance(payload, dict) else None
            if isinstance(value, int) and not isinstance(value, bool):
                provider_code = value
        except (ValueError, OSError):
            pass
        finally:
            exc.close()
        if resource == 'VerificationCheck' and code in (400, 404):
            return {'status': 'denied'}
        raise DeliveryUnavailable('Verification service unavailable.', http_status=code, provider_code=provider_code) from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, http.client.HTTPException):
        raise DeliveryUnavailable('Verification service unavailable.') from None


def start(channel, destination):
    if channel == "phone" and provider() == "msg91":
        return _msg91_start(destination)
    if provider() not in ("twilio", "msg91"):
        raise DeliveryUnavailable("Unknown OTP provider.")
    result = _post('Verifications', {'To': destination, 'Channel': 'sms' if channel == 'phone' else 'email'})
    sid = result.get('sid', '')
    if result.get('status') != 'pending' or not isinstance(sid, str) or not re.fullmatch(r'VE[0-9a-fA-F]{32}', sid):
        raise DeliveryUnavailable('Verification service unavailable.')
    return sid


def check(sid, code):
    if isinstance(sid, str) and sid.startswith("msg91:"):
        parts = sid.split(":")
        if len(parts) != 3 or not re.fullmatch(r"91[6-9][0-9]{9}", parts[1]) or not re.fullmatch(r"[0-9]{6}", str(code)):
            return False
        result = _msg91_request("/verify", {"mobile": parts[1], "otp": code})
        return result.get("type") == "success" and result.get("message", "").strip().lower() == "otp verified success"
    result = _post('VerificationCheck', {'VerificationSid': sid, 'Code': code})
    return result.get('status') == 'approved' and result.get('sid') == sid


def provider():
    return (os.getenv('DHASHU_SMS_PROVIDER', '').strip().lower() or 'msg91')


def configured():
    if provider() == 'msg91':
        return bool(os.getenv('MSG91_AUTH_KEY', '').strip() and
                    re.fullmatch(r'[a-fA-F0-9]{24}', os.getenv('MSG91_TEMPLATE_ID', '')))
    return provider() == 'twilio' and _twilio_configured()


def _msg91_request(suffix, params):
    key = os.getenv('MSG91_AUTH_KEY', '').strip()
    if not key:
        raise DeliveryUnavailable('MSG91 is not configured.')
    request = urllib.request.Request(
        'https://control.msg91.com/api/v5/otp' + suffix + '?' + urllib.parse.urlencode(params),
        data=b'{}' if not suffix else None,
        method='POST' if not suffix else 'GET',
        headers={'authkey': key, 'Content-Type': 'application/json'})
    try:
        with resilience.call('msg91', urllib.request.build_opener(NoRedirect()).open, request, timeout=10) as response:
            result = json.loads(response.read(65536))
        if not isinstance(result, dict) or result.get('type') not in ('success', 'error'):
            raise DeliveryUnavailable('MSG91 returned an unexpected response.')
        return result
    except urllib.error.HTTPError as exc:
        status = exc.code
        exc.close()
        raise DeliveryUnavailable('MSG91 service unavailable.', http_status=status) from None
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, http.client.HTTPException):
        raise DeliveryUnavailable('MSG91 service unavailable.') from None


def _msg91_start(destination):
    if not configured():
        raise DeliveryUnavailable('MSG91 is not configured.')
    if not re.fullmatch(r'\+91[6-9][0-9]{9}', destination):
        raise DeliveryUnavailable('MSG91 phone delivery requires an Indian mobile number.')
    mobile = destination[1:]
    result = _msg91_request('', {'template_id': os.environ['MSG91_TEMPLATE_ID'],
        'mobile': mobile, 'otp_length': 6, 'otp_expiry': 10})
    request_id = result.get('request_id')
    if result.get('type') != 'success' or not isinstance(request_id, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,128}', request_id):
        raise DeliveryUnavailable('MSG91 did not accept the OTP request.')
    return 'msg91:' + mobile + ':' + request_id
