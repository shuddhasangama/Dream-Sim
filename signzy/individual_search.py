"""Court search request contract; response contract remains to be confirmed."""
PATH = '/individual/search'

def payload(values):
    allowed = {'name', 'address', 'fatherName', 'dob', 'caseCategory', 'type', 'matchType'}
    if not isinstance(values, dict) or set(values) - allowed:
        raise ValueError('Unsupported court-search fields')
    result = {}
    for key in allowed:
        value = values.get(key, '')
        if not isinstance(value, str):
            raise ValueError('Court-search inputs must be strings')
        value = value.strip()
        if key in ('name', 'address', 'matchType') and not value:
            raise ValueError('Name, address and matchType are required')
        if value:
            result[key] = value
    for key, options in (('matchType', ('exact', 'possible')),
                         ('caseCategory', ('civil', 'criminal')),
                         ('type', ('petitioner', 'respondent'))):
        if key in result:
            result[key] = result[key].lower()
            if result[key] not in options:
                raise ValueError('Invalid court-search filter: ' + key)
    # DOB wire format has not been supplied; do not guess or transform it.
    if 'dob' in result:
        raise ValueError('Court-search DOB format needs provider confirmation; omit it for now')
    return result

def summarize(status, body):
    return {'outcome': 'response_received_review_required' if status == 200 and isinstance(body, (dict, list))
            else 'request_failed_or_unexpected_response', 'automatic_verification': False,
            'court_clearance': 'not_evaluated'}
