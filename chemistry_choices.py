"""Own activity answers and independent partner indifference; no inferred consent."""
import unicodedata
import onboarding
from api_contract import ApiError


def validate(activities, custom, partner_any):
    def fail(message):
        raise ApiError('validation_error', message)
    if type(custom) is not list or len(custom)>4:
        fail('Add up to four custom activities.')
    names=[]
    known={x.casefold() for x in onboarding.ACTIVITIES}
    for name in custom:
        if type(name) is not str or not 1<=len(name)<=60 or name!=name.strip() or any(unicodedata.category(c).startswith('C') for c in name):
            fail('Activity names must be 1–60 characters, without surrounding spaces or control characters.')
        canonical=' '.join(unicodedata.normalize('NFKC',name).casefold().split())
        if canonical in known:
            fail('Choose distinct custom activities not already listed.')
        known.add(canonical)
        names.append(name)
    if type(activities) is not dict or set(activities)-set(onboarding.ACTIVITIES)-set(names) or any(type(v) is not str or v not in onboarding.BUCKET_IDS for v in activities.values()):
        fail('Choose a listed answer for each selected activity.')
    if any(name not in activities for name in names):
        fail('Choose your own answer for each custom activity.')
    if len(activities)<onboarding.MIN_SORTED:
        fail(f'Sort at least {onboarding.MIN_SORTED} activities ({len(activities)}/{onboarding.MIN_SORTED} so far).')
    if type(partner_any) is not list or any(type(x) is not str or x not in activities for x in partner_any) or len(partner_any)!=len(set(partner_any)):
        fail('Set partner indifference only for activities you have answered.')
    return {'activities':activities,'custom_activities':names,'partner_any':partner_any}
