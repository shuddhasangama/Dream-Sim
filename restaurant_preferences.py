"""Stable booking identifiers; existing profile labels remain backwards compatible.

Provider adapters must translate documented vendor values to these identifiers.
Diet tags mean confirmed suitable food options, not a dedicated/exclusive venue.
Unknown restrictions must never silently become unrestricted.
"""
CUISINES = {v.replace('_', ' ').title(): v for v in (
    'south_indian', 'north_indian', 'italian', 'japanese', 'thai',
    'levantine', 'mexican', 'korean', 'chinese', 'continental')}
DIETS = {'Vegetarian': 'vegetarian', 'Vegan': 'vegan', 'Eggetarian': 'eggetarian',
         'Halal': 'halal', 'Jain': 'jain', 'No red meat': 'no_red_meat', 'Everything': 'unrestricted'}


def identifiers(values, vocabulary):
    if isinstance(values, str):
        values = [values]
    lookup = {k.casefold(): v for k, v in vocabulary.items()}
    lookup.update({v: v for v in vocabulary.values()})
    result = set()
    for value in values or []:
        key = value.strip().casefold() if isinstance(value, str) else ''
        if key not in lookup:
            raise ValueError('Unknown restaurant preference')
        result.add(lookup[key])
    return result


def matches(cuisines, requirements, offered_cuisines, offered_diets):
    wanted = identifiers(requirements, DIETS) - {'unrestricted'}
    offered = identifiers(offered_diets, DIETS) - {'unrestricted'}
    return bool(identifiers(cuisines, CUISINES) & identifiers(offered_cuisines, CUISINES)) and wanted <= offered


def provider_values(values, vocabulary, mapping):
    """Explicit canonical-ID to documented provider-value mapping; fail closed."""
    keys = identifiers(values, vocabulary) - {'unrestricted'}
    if not keys <= mapping.keys():
        raise ValueError('Provider does not map every requested preference')
    return [mapping[key] for key in sorted(keys)]


def per_person_minor(amount_minor, basis, party_size=2):
    """Normalize documented estimates; round up to avoid understating cost."""
    if type(amount_minor) is not int or amount_minor < 0 or type(party_size) is not int or party_size < 1:
        raise ValueError('Invalid food estimate')
    if basis == 'per_person':
        return amount_minor
    if basis == 'party_total':
        return (amount_minor + party_size - 1) // party_size
    raise ValueError('Unknown food estimate basis')
