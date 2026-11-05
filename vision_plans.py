"""Initial Vision v2: plans describe selected pillars, not reproductive routes."""
from api_contract import ApiError

OPTIONS = {'Intimacy': ['Emotional', 'Physical'], 'Kids': [],
    'Cohabitate': ['Chores split', 'Expenses sharing', 'Extended family', 'Pets'], 'Travel together': []}
SETS = {'grow': set(OPTIONS), 'two': {'Intimacy', 'Cohabitate', 'Travel together'},
    'explore': {'Intimacy', 'Travel together'}}
LABELS = {'grow': 'Family', 'two': 'We Two', 'explore': 'Travel', 'custom': 'Custom'}
PRESETS = [{'key': key, 'label': LABELS[key], 'description': '',
    'choices': {pillar: list(OPTIONS[pillar]) for pillar in OPTIONS if pillar in selected},
    'kids_intent': 'want' if key == 'grow' else 'no' if key == 'two' else 'undecided'} for key, selected in SETS.items()]
PRESETS.append({'key': 'custom', 'label': 'Custom', 'description': '', 'choices': None, 'kids_intent': 'undecided'})


def plan_for(pillars):
    return next((key for key, selected in SETS.items() if set(pillars) == selected), 'custom')


def intent_for(pillars):
    return 'want' if 'Kids' in pillars else 'no' if plan_for(pillars) == 'two' else 'undecided'


def validate(pillars):
    if type(pillars) is not dict or set(pillars) - set(OPTIONS):
        raise ApiError('validation_error', 'Choose the listed Vision pillars.')
    for key, values in pillars.items():
        if type(values) is not list or any(type(v) is not str or v not in OPTIONS[key] for v in values) or len(values) != len(set(values)):
            raise ApiError('validation_error', 'Choose listed options only. Kids and Travel have no sub-options.')
    if not pillars.get('Intimacy'):
        raise ApiError('validation_error', 'Choose Emotional, Physical or both for Intimacy.')
    if len(pillars) < 2:
        raise ApiError('validation_error', 'Choose at least one more pillar alongside Intimacy.')
    if 'Cohabitate' in pillars and not pillars['Cohabitate']:
        raise ApiError('validation_error', 'Choose at least one Cohabitate priority.')
    return pillars
