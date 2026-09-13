"""Read-only journey projections shared by the new JSON endpoints.

App callbacks supply existing domain rules. This module never renders templates,
generates matches, advances time or resolves outcomes. API availability is distinct
from journey eligibility so clients are never sent to an unimplemented endpoint.
"""
import disclosure
import guru
import progress
from api_contract import allowlist


# Extend when a tested JSON capability ships. Values are real GET routes only.
READ_APIS = {
    'dashboard': '/api/v1/dashboard',
    'reach': '/api/v1/reach',
    'guru': '/api/v1/guidance',
}


def surface(key, reached, reach_is_locked):
    eligible = key in disclosure.BY_KEY and disclosure.is_open(key, reached)
    reason = disclosure.locked_reason(key, reached) if not eligible else None
    if key == 'reach' and reach_is_locked:
        eligible, reason = False, 'REACH is closed while you are locked in or past Dating.'
    href = READ_APIS.get(key)
    return {
        'key': key, 'eligible': eligible, 'blocked_reason': reason,
        'api_available': href is not None,
        'request': {'method': 'GET', 'path': href} if eligible and href else None,
    }


def guidance(reached, facts, reach_is_locked):
    action = guru.next_action(reached, facts=facts)
    key = disclosure.ENDPOINT_TO_KEY.get(action['endpoint'])
    return {
        **allowlist(action, ('headline', 'body', 'cta')),
        'destination': surface(key, reached, reach_is_locked) if key else None,
    }


def snapshot(user, *, active, plan, couple, reached, contact, clock,
             reach_is_locked, facts, display_name):
    """Only pair summaries; never partner identity, private responses or contacts."""
    # Defence in depth if a future adapter supplies a row from another pair.
    uid = user['user_id']
    if active is not None and uid not in (active['user_a'], active['user_b']):
        raise ValueError('Journey projection received an unrelated lock-in')
    if couple is not None and uid not in (couple['partner_a_id'], couple['partner_b_id']):
        raise ValueError('Journey projection received an unrelated couple')
    if plan is not None and (active is None or plan['lockin_id'] != active['id']):
        raise ValueError('Journey projection received an unrelated plan')
    return {
        'user': {**allowlist(user, ('user_id', 'journey_state', 'bgv_status')),
                 'display_name': display_name},
        'stage_indicator': progress.stage_view(user['journey_state'], reached),
        'milestones': [key for key in disclosure.ORDER if key in reached],
        'contact_verification': allowlist(contact, ('required', 'satisfied',
                                                   'verified_email', 'verified_phone')),
        'clock': {'mode': 'simulation', 'week': clock.week, 'day': clock.day,
                  'hour': clock.hour},
        'current_lock_in': allowlist(active, ('id', 'status', 'week', 'dates_completed')),
        'current_date_plan': allowlist(plan, ('id', 'status', 'datetime')),
        'current_couple': allowlist(couple, ('id', 'stage', 'stage_week_index')),
        'surfaces': [surface(key, reached, reach_is_locked)
                     for key in disclosure.BY_KEY],
        'next_action': guidance(reached, facts, reach_is_locked),
    }
