"""One-shot preproduction current-employer probe; no app/database writes."""
import getpass
import json
import re
import secrets
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ENDPOINT = 'https://api-preproduction.signzy.app/api/v3/employment-verification/current-employer'


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Do not forward credentials or personal data to another URL.


def summary(status, body):
    """Allowlist only non-identifying status fields; never persist provider errors."""
    body = body if isinstance(body, dict) else {}
    employment = body.get('employmentSummary')
    employment = employment if isinstance(employment, dict) else {}
    code = body.get('resultCode')
    success = status == 200 and type(code) is int and code == 200
    return {
        'http_status': status,
        'result_code': code if type(code) is int else None,
        'outcome': 'response_received_review_required' if success else 'request_failed_or_unexpected_response',
        'is_employed': employment.get('is_employed') if success and type(employment.get('is_employed')) is bool else None,
        'date_of_exit_marked': employment.get('date_of_exit_marked') if success and type(employment.get('date_of_exit_marked')) is bool else None,
        'employment_summary_present': bool(employment),
        'automatic_verification': False,
    }


def call(token, mobile, pan):
    # Compatibility entry point; shared wrapper owns all network access.
    from signzy.client import Client, Config
    return Client(Config(token=token)).execute(
        'current_employer', {'mobile': mobile, 'panNumber': pan}, consent_confirmed=True)


def main():
    print('Signzy PREPRODUCTION: current-employer check only. May consume API credits.')
    print('No raw response, PAN, mobile, name, UAN or credential will be saved.')
    mobile = getpass.getpass('Consented test mobile (10 digits; hidden): ').strip()
    pan = getpass.getpass('Consented test PAN (hidden): ').strip().upper()
    if not re.fullmatch(r'[6-9][0-9]{9}', mobile) or not re.fullmatch(r'[A-Z]{5}[0-9]{4}[A-Z]', pan):
        print('Invalid mobile or PAN format; nothing sent.')
        return
    token = getpass.getpass('Replacement preproduction token (hidden): ').strip()
    if not token or '\r' in token or '\n' in token:
        print('Invalid token; nothing sent.')
        return
    if input('Confirm consent to send these details to Signzy. Type SEND for one call: ').strip() != 'SEND':
        print('Cancelled; nothing sent.')
        return
    receipt = {'tested_at_utc': datetime.now(timezone.utc).isoformat(), 'environment': 'preproduction',
               'endpoint': ENDPOINT, 'client_reference': 'partners@dhashu.com'}
    try:
        receipt.update(call(token, mobile, pan))
    except (urllib.error.URLError, TimeoutError, OSError):
        receipt.update(outcome='transport_error_outcome_unknown', automatic_verification=False)
        print('Transport error: do not retry automatically; check Signzy API Logs first.')
    filename = Path('signzy-probe-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + secrets.token_hex(3) + '.json')
    with filename.open('x', encoding='utf-8') as handle:
        json.dump(receipt, handle, indent=2)
    print(json.dumps(receipt, indent=2))
    print('Sanitised receipt saved:', filename.resolve())
    print('No automatic retry. Use Signzy API Logs for the trace ID and full response.')


if __name__ == '__main__':
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print('\nStopped. If interrupted after SEND, check provider logs before retrying.')
