"""FIR candidate search; supplied contract, no identity/adverse decision."""
import re

PATH = '/fir/search'


def identifier(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{8,120}', value.strip()):
        raise ValueError('Invalid FIR search identifier')
    return value.strip()


def payload(values):
    if not isinstance(values, dict) or set(values) - {'name', 'address', 'fatherName', 'matchType'}:
        raise ValueError('Unsupported FIR search fields')
    result = {}
    for key in ('name', 'address', 'fatherName', 'matchType'):
        value = values.get(key, '')
        if not isinstance(value, str):
            raise ValueError('FIR inputs must be strings')
        value = value.strip()
        if key in ('name', 'address', 'matchType') and not value:
            raise ValueError('FIR name, address and matchType are required')
        if value:
            result[key] = value
    if result['matchType'] not in ('exact', 'possible'):
        raise ValueError('FIR matchType must be exact or possible')
    return result


def result_identifier(body):
    """Observed sandbox envelope plus the originally supplied flat contract.

    Reject contradictory identifiers rather than guessing which paid search to fetch.
    """
    if not isinstance(body, dict):
        raise ValueError('Unexpected FIR search response')
    nested = body.get('result')
    values = [body.get('searchId')]
    if isinstance(nested, dict):
        if type(nested.get('status')) is not int or nested['status'] != 1:
            raise ValueError('Unconfirmed FIR search status')
        values.append(nested.get('verifyId'))
    found = [identifier(value) for value in values if value is not None]
    if not found or len(set(found)) != 1:
        raise ValueError('Missing or ambiguous FIR result identifier')
    return found[0]


def summarize(status, body):
    present = False
    if isinstance(body, dict):
        try:
            result_identifier(body)
            present = True
        except ValueError:
            pass
    return {'outcome': ('accepted_pending_confirmation' if status in (200, 202) and present else
                        'response_received_contract_review_required' if status == 200 else
                        'request_failed_or_unexpected_response'),
            'search_id_received': present, 'fir_clearance': 'not_evaluated',
            'automatic_verification': False}
