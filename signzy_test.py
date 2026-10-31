"""Interactive sandbox runner. Production intentionally unavailable here."""
import argparse
import getpass
import json
from datetime import datetime, timezone
from pathlib import Path
import secrets
from signzy.client import Client, Config, OPERATIONS
from signzy.receipts import ReceiptStore


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=sorted(OPERATIONS))
    parser.add_argument('--user-id', help='Explicit test user to store field evidence against')
    parser.add_argument('--search-receipt', help='Private receipt of the corresponding court/FIR search')
    parser.add_argument('--match-type', choices=('exact', 'possible'), default=None,
                        help='Court search matching mode (default: exact)')
    parser.add_argument('--case-category', choices=('criminal', 'civil'), default=None,
                        help='Optional court search category; omission uses the provider default')
    args = parser.parse_args()
    if args.match_type is not None and args.operation not in ('individual_search', 'fir_search'):
        parser.error('--match-type is only available for individual_search or fir_search')
    if args.case_category is not None and args.operation != 'individual_search':
        parser.error('--case-category is only available for individual_search')
    config = Config.from_env()
    if config.environment != 'preproduction':
        raise ValueError('This runner only permits preproduction')
    if not config.token:
        raise ValueError('Set SIGNZY_TEST_API_KEY once in this environment before running the tester')
    client = Client(config)
    store = ReceiptStore()
    user_binding = None
    if args.user_id:
        import db
        from signzy.verification import binding
        if args.operation not in ('pan_simple', 'current_employer'):
            raise ValueError('User-bound field comparison is available only for PAN Simple and current employer')
        conn = db.get_connection()
        try:
            db.init_db(conn)
            if not db.fetch_one(conn, 'User', id=args.user_id):
                raise ValueError('Unknown user; no API request sent')
        finally:
            conn.close()
        print('Use only this user\'s consented details. Sandbox evidence does not approve live BGV.')
        declared = ({'name': getpass.getpass('User-declared legal name (hidden): ').strip(),
                     'dob': getpass.getpass('User-declared DOB YYYY-MM-DD (hidden): ').strip()}
                    if args.operation == 'pan_simple' else
                    {'employer': getpass.getpass('User-declared current employer (hidden): ').strip()})
        user_binding = binding(args.user_id, declared)
    print('Submitting the final input sends one consented preproduction check; may consume credits. Ctrl+C to stop.')
    if args.operation == 'individual_search':
        print('Court search matchType=' + (args.match_type or 'exact'))
        print('Court search caseCategory=' + (args.case_category or 'omitted (provider default)'))
        values = {'name': getpass.getpass('Consented full name (hidden): ').strip(),
                  'address': getpass.getpass('Consented address (hidden): ').strip(),
                  'matchType': args.match_type or 'exact'}
        if args.case_category:
            values['caseCategory'] = args.case_category
    elif args.operation == 'fir_search':
        print('FIR search matchType=' + (args.match_type or 'exact'))
        values = {'name': getpass.getpass('Consented full name (hidden): ').strip(),
                  'address': getpass.getpass('Consented address (hidden): ').strip(),
                  'fatherName': getpass.getpass('Consented father name (hidden; blank if unavailable): ').strip(),
                  'matchType': args.match_type or 'exact'}
    elif args.operation == 'fir_result':
        if not args.search_receipt:
            raise ValueError('fir_result needs --search-receipt <private receipt of the FIR search>')
        from signzy.receipts import read_private
        prior = read_private(args.search_receipt)
        if prior.get('operation') != 'fir_search' or prior.get('environment') != 'preproduction':
            raise ValueError('That receipt is not a preproduction FIR search')
        provider = prior.get('provider_response') or {}
        if provider.get('http_status') not in (200, 202):
            raise ValueError('Prior FIR search failed; no result request sent')
        found = provider.get('json') or {}
        values = {'verifyId': found.get('searchId') if isinstance(found, dict) else None}
        print('Using prior FIR searchId as result verifyId. One result call; no automatic polling.')
    elif args.operation == 'individual_result':
        if not args.search_receipt:
            raise ValueError('individual_result needs --search-receipt <private receipt of the earlier court search>')
        from signzy.receipts import read_private
        prior = read_private(args.search_receipt)
        if prior.get('operation') != 'individual_search' or prior.get('environment') != 'preproduction':
            raise ValueError('That receipt is not a preproduction court search')
        found = ((prior.get('provider_response') or {}).get('json') or {})
        values = {'caseId': found.get('caseId') if isinstance(found, dict) else None}
        print('Using the caseId stored in that private receipt. Fetches the result of one earlier search.')
    elif args.operation == 'employment_history':
        print('Use consented employment-history details; blank optional fields are sent as empty strings.')
        print('Provide at least PAN, mobile or UAN. Required combinations and DOB wire format need Signzy confirmation.')
        values = {
            'pan': getpass.getpass('Consented PAN (hidden; blank to omit): ').strip(),
            'mobile': getpass.getpass('Consented mobile (hidden; blank to omit): ').strip(),
            'uan': getpass.getpass('Consented UAN (hidden; blank to omit): ').strip(),
            'dob': getpass.getpass('DOB in Signzy-confirmed request format (hidden; blank if unknown): ').strip(),
            'employeeName': getpass.getpass('Consented employee name (hidden; blank to omit): ').strip(),
        }
    elif args.operation == 'uan_passbook':
        print('Only proceed with consent to retrieve this person\'s EPF passbook. ttl=0; no callback configured.')
        values = {'uan': getpass.getpass('Consented UAN, 12 digits (hidden): ').strip(),
                  'consentFlag': 'Y', 'ttl': 0}
    else:
        values = {'panNumber': getpass.getpass('Consented PAN (hidden): ').strip()}
    if args.operation == 'current_employer':
        values['mobile'] = getpass.getpass('Consented mobile (hidden): ').strip()
    elif args.operation == 'pan_extensive':
        values['getStatusInfo'] = True
    OPERATIONS[args.operation].payload(values)
    print('One preproduction request; may consume credits. ' +
          ('Test field evidence will be stored.' if user_binding else 'No app/database writes.'))
    private_paths = []
    def save_evidence(evidence):
        if user_binding:
            evidence['binding'] = user_binding
        private_paths.append(store.save(evidence))
        if user_binding:
            from signzy.verification import ingest
            conn = db.get_connection()
            try:
                ingest(conn, evidence, store)
            finally:
                conn.close()
    receipt = client.execute(args.operation, values, consent_confirmed=True, evidence_sink=save_evidence)
    receipt['tested_at_utc'] = datetime.now(timezone.utc).isoformat()
    if args.operation in ('individual_search', 'fir_search'):
        receipt['match_type'] = values['matchType']
        if args.operation == 'individual_search':
            receipt['case_category'] = values.get('caseCategory')
    if args.operation == 'fir_result':
        receipt['source_search_receipt_id'] = prior.get('receipt_id')
    directory = Path('data/signzy-test-receipts')
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (receipt.get('receipt_id', secrets.token_hex(12)) + '.summary.json')
    with path.open('x', encoding='utf-8') as handle:
        json.dump(receipt, handle, indent=2)
    print(json.dumps(receipt, indent=2))
    print('Sanitised receipt:', path.resolve())
    for private_path in private_paths:
        print('Private encrypted receipt (do not share):', private_path.resolve())
    print('View privately: python signzy_receipt.py <private-receipt-path>')
    print('No automatic retries. Summary is not the full provider response.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyboardInterrupt, EOFError) as exc:
        print('Stopped:', str(exc) if isinstance(exc, ValueError) else 'Input cancelled')
