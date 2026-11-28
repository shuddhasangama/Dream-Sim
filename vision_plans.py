"""Initial Vision v2: plans describe selected pillars, not reproductive routes."""
from api_contract import ApiError

OPTIONS = {'Intimacy': ['Emotional', 'Physical'], 'Kids': [],
    'Cohabitate': ['Chores split', 'Expenses sharing', 'Extended family', 'Pets'], 'Travel together': []}
# Owner decision (2026-11-25): only items with detail get "Add detail" and
# "Declare a change". Today that is Intimacy; the others carry no detail.
DETAIL_OPTIONS = {k: (list(v) if k == 'Intimacy' else []) for k, v in OPTIONS.items()}


def has_detail(pillar):
    return bool(DETAIL_OPTIONS.get(pillar))


SETS = {'grow': set(OPTIONS), 'two': {'Intimacy', 'Cohabitate', 'Travel together'},
    'explore': {'Intimacy', 'Travel together'}}
# Client answer 1 (2026-11-27): Family = all 4 pillars; Together = all except Kids;
# Travel together = Emotional intimacy + Travel; Custom = the member defines their own.
LABELS = {'grow': 'Family', 'two': 'Together', 'explore': 'Travel together', 'custom': 'Custom'}
PRESETS = [{'key': key, 'label': LABELS[key], 'description': '',
    'choices': {pillar: (['Emotional'] if pillar=='Intimacy' else []) for pillar in OPTIONS if pillar in selected},
    'kids_intent': 'want' if key == 'grow' else 'no' if key == 'two' else 'undecided'} for key, selected in SETS.items()]
PRESETS.append({'key': 'custom', 'label': 'Custom', 'description': '', 'choices': None, 'kids_intent': 'undecided'})


# Custom: up to four pillars the member names themselves, alongside any of the four above.
# Stored apart from the four (stats_json.vision_custom_pillars), so matching, which reads
# only the four, is unchanged; they are shown on the member's own Vision.
MAX_CUSTOM_PILLARS = 4


def validate_custom_pillars(names):
    if names is None:
        return []
    if type(names) is not list or len(names) > MAX_CUSTOM_PILLARS:
        raise ApiError('validation_error', f'Add up to {MAX_CUSTOM_PILLARS} pillars of your own.')
    clean, seen = [], {k.casefold() for k in OPTIONS} | {'travel', 'intimacy'}
    for name in names:
        if type(name) is not str or not 1 <= len(name.strip()) <= 40 or any(ord(c) < 32 for c in name):
            raise ApiError('validation_error', 'Name each pillar of your own in 1 to 40 characters.')
        key = ' '.join(name.split()).casefold()
        if key in seen:
            raise ApiError('validation_error', 'Name pillars of your own that are distinct and not already listed.')
        seen.add(key)
        clean.append(' '.join(name.split()))
    return clean


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
    if 'Emotional' not in pillars.get('Intimacy',[]):
        raise ApiError('validation_error', 'Emotional intimacy is required. Physical intimacy is optional.')
    if len(pillars) < 2:
        raise ApiError('validation_error', 'Choose at least one more pillar alongside Intimacy.')
    return pillars
