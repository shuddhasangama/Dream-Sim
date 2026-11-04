"""Standalone preproduction Liveness Secure tester. No app/database writes."""
import argparse
from dataclasses import replace
import getpass
import json
from pathlib import Path
from signzy.client import Client, Config, BASES, OPERATIONS
from signzy.receipts import ReceiptStore, read_private
from signzy.liveness_secure_create import session

DIRECTORY = Path(__file__).resolve().parent / 'data' / 'signzy-liveness-test'


def sanitized(value, name=''):
    if name.lower() in {'token', 'consumerid', 'id', 'authorization', 'body_base64'}:
        return '[private]'
    if isinstance(value, dict):
        return {k: sanitized(v, k) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitized(v, name) for v in value]
    if isinstance(value, str) and value.startswith(('https://', 'http://', 'data:image/')):
        return '[private URL/image]'
    return value


def previous(path):
    evidence = read_private(path)
    if evidence.get('operation') != 'liveness_secure_create' or evidence.get('environment') != 'preproduction':
        raise ValueError('Use the encrypted receipt from this sandbox createUrl call')
    response = evidence.get('provider_response') or {}
    if response.get('http_status') not in (200, 201):
        raise ValueError('Create URL did not succeed; inspect its private receipt first')
    return session(response.get('json'))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('step', choices=('create', 'get'))
    parser.add_argument('--prompt-key', action='store_true', help='Always prompt for the sandbox key without echo')
    parser.add_argument('--match-image', help='Consented Aadhaar portrait HTTPS URL; omit to enter privately')
    parser.add_argument('--aadhaar-receipt', help='Encrypted eAadhaar receipt containing a vendor-hosted photo URL')
    parser.add_argument('--callback-url', help='Optional HTTPS callback receiver; not deployed by this tester')
    parser.add_argument('--redirect-url', help='Optional HTTPS page to return to after capture')
    parser.add_argument('--threshold', type=float, default=.6)
    parser.add_argument('--retention', default='6 months', help='Vendor piiDeletionTTL value; default follows supplied example')
    parser.add_argument('--receipt', help='Create receipt to use for get; otherwise uses the last local attempt')
    parser.add_argument('--new-session', action='store_true', help='Explicitly permit another potentially billable create call')
    parser.add_argument('--show-private', action='store_true', help='Print full request/response, except Authorization; do not share output')
    args = parser.parse_args(argv)
    config = Config.from_env()
    if config.environment != 'preproduction':
        raise ValueError('This tester only permits SIGNZY_ENV=preproduction')
    store = ReceiptStore(DIRECTORY)
    pointer = DIRECTORY / 'latest-create.txt'
    if args.step == 'create':
        if pointer.exists() and not args.new_session:
            raise ValueError('A create request was already attempted. Use get, or inspect its receipt before using --new-session.')
        image = args.match_image
        if args.aadhaar_receipt:
            from signzy.document_photo import reference
            prior = read_private(args.aadhaar_receipt)
            if prior.get('operation') != 'digilocker_eaadhaar' or prior.get('environment') != 'preproduction':
                raise ValueError('Use your own sandbox eAadhaar receipt')
            photo = reference((prior.get('provider_response') or {}).get('json'))
            if not photo:
                raise ValueError('No vendor-hosted photo URL in that receipt. Enter a currently accessible Aadhaar portrait HTTPS URL instead.')
            image = photo['url']
        if not image:
            image = getpass.getpass('Your consented Aadhaar portrait HTTPS URL (hidden): ').strip()
        values = {'matchImage': [image], 'faceMatchThreshold': args.threshold, 'piiDeletionTTL': args.retention}
        for name, value in [('callbackUrl', args.callback_url), ('redirectUrl', args.redirect_url)]:
            if value:
                values[name] = value
        print('Manual test: callback/redirect fields are omitted unless supplied. Provider requirements are not yet confirmed.')
        operation = 'liveness_secure_create'
    else:
        path = args.receipt or (pointer.read_text(encoding='utf-8').strip() if pointer.exists() else None)
        if not path:
            raise ValueError('Run create first or provide --receipt with its encrypted receipt path')
        token, _, consumer = previous(path)
        values = {'token': token}
        operation = 'liveness_secure_data'
        print('Use the SAME capture link first. You may also fetch deliberately before completion to inspect the pending response.')
    request_body = OPERATIONS[operation].payload(values)
    print('POST ' + BASES['preproduction'] + OPERATIONS[operation].PATH)
    print('Authorization: [not displayed]')
    print(json.dumps(request_body if args.show_private else sanitized(request_body), indent=2))
    if args.prompt_key or not config.token:
        config = replace(config, token=getpass.getpass('Signzy sandbox API key (hidden): ').strip())
    client = Client(config)
    print('This sends one sandbox API request and may consume credits. No automatic retry. No app data will change.')
    if input('Use your own consented image/session. Type YES to send: ').strip() != 'YES':
        print('Cancelled. No request sent.')
        return 0
    saved = []
    def save(evidence):
        path = store.save(evidence)
        saved.append((path, evidence))
        if args.step == 'create':
            pointer.write_text(str(path.resolve()), encoding='utf-8')
    summary = client.execute(operation, values, consent_confirmed=True, evidence_sink=save)
    path, evidence = saved[0]
    response = evidence.get('provider_response') or {}
    body = response.get('json')
    mismatch = False
    if args.step == 'get' and isinstance(body, dict) and isinstance(body.get('result'), dict):
        result = body['result']
        mismatch = result.get('token') != token or consumer is not None and result.get('consumerId') != consumer
        if mismatch:
            summary = {**summary, 'combined_passed': None, 'outcome': 'session_identifiers_missing_or_mismatched'}
    print('HTTP:', summary.get('http_status'))
    print('Response:')
    print(json.dumps(body if args.show_private else sanitized(body), indent=2, ensure_ascii=False))
    print('Summary: ' + json.dumps(summary, indent=2))
    print('Encrypted receipt: ' + str(path))
    if args.step == 'create' and summary.get('capture_link_received'):
        _, url, _ = session(body)
        print('\nPRIVATE capture URL (do not share):\n' + url)
        print('\nOpen it, complete Signzy capture, then run:\npython signzy_liveness_test.py get')
    elif mismatch:
        print('SESSION MISMATCH OR MISSING IDENTIFIERS: do not rely on this result; inspect the receipt.')
        return 2
    if not summary.get('http_status') or not 200 <= summary['http_status'] < 300:
        print('Request did not succeed. Inspect the receipt; nothing is retried automatically.')
        return 2
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError) as exc:
        raise SystemExit(str(exc)) from None
    except (KeyboardInterrupt, EOFError):
        raise SystemExit('Stopped. If a request had started, inspect its receipt before creating another session.') from None
