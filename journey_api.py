"""Read-only journey projections shared by the new JSON endpoints.

App callbacks supply existing domain rules. This module never renders templates,
generates matches, advances time or resolves outcomes. API availability is distinct
from journey eligibility so clients are never sent to an unimplemented endpoint.
"""
import disclosure
import guru
import guru_dating
import progress
from urllib.parse import quote
from api_contract import allowlist


# Extend when a tested JSON capability ships. Values are real GET routes only.
READ_APIS = {
    'dashboard': '/api/v1/dashboard',
    'reach': '/api/v1/reach',
    'guru': '/api/v1/guidance',
    'week': '/api/v1/week',
    'vision': '/api/v1/profile/vision',
    'stats': '/api/v1/profile/stats',
    'chemistry': '/api/v1/profile/chemistry',
    'expectations': '/api/v1/profile/chemistry',
    'vibes': '/api/v1/profile/chemistry',
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


def guidance(reached, facts, reach_is_locked, *, in_dating=False, partner_greeting=None):
    action = guru.next_action(reached, facts=facts)
    key = disclosure.ENDPOINT_TO_KEY.get(action['endpoint'])
    open_cards = guru.cards(reached, exclude_endpoint=action['endpoint'])
    return {
        **allowlist(action, ('headline', 'body', 'cta')),
        'destination': surface(key, reached, reach_is_locked) if key else None,
        # round3-fixes-spec.md §6.3: "anything I can help you with?" —
        # every door currently open, not just the one next_action already
        # points at. The same list the web's guru_all_view()/"Also open"
        # tiles use (guru.cards()), exposed here so a client that has no
        # template of its own can still offer it.
        'also_open': [
            {**allowlist(c, ('code', 'title', 'subtitle')),
             'destination': surface(c['surface'], reached, reach_is_locked)}
            for c in open_cards
        ],
        # round3-fixes-spec.md §6.1/§6.2: Dating-only, in Guru's own voice
        # — the consent model, the rules of engagement, and what to expect
        # on a date. None outside Dating; guru_dating.py stays the one
        # place this content is defined.
        'dating_context': {
            **guru_dating.dating_context(),
            'date_prep': guru_dating.pre_date_briefing(partner_greeting),
        } if in_dating else None,
    }


def snapshot(user, *, active, plan, couple, reached, contact, clock,
             reach_is_locked, facts, display_name, simulated, partner_greeting=None):
    """Only pair summaries; never partner identity, private responses or contacts."""
    # Defence in depth if a future adapter supplies a row from another pair.
    uid = user['user_id']
    if active is not None and uid not in (active['user_a'], active['user_b']):
        raise ValueError('Journey projection received an unrelated lock-in')
    if couple is not None and uid not in (couple['partner_a_id'], couple['partner_b_id']):
        raise ValueError('Journey projection received an unrelated couple')
    if plan is not None and (active is None or plan['lockin_id'] != active['id']):
        raise ValueError('Journey projection received an unrelated plan')
    result = {
        'user': {**allowlist(user, ('user_id', 'journey_state', 'bgv_status')),
                 'display_name': display_name},
        'stage_indicator': progress.stage_view(user['journey_state'], reached),
        'milestones': [key for key in disclosure.ORDER if key in reached],
        'contact_verification': allowlist(contact, ('required', 'satisfied',
                                                   'verified_email', 'verified_phone')),
        # road-fixes-clock-spec.md §7: the client reads day/hour from here,
        # never computes it — and only shows stepping controls when
        # simulated_clock is true, never inferred from a build flag alone.
        'clock': {'mode': 'simulation' if simulated else 'real_time', 'week': clock.week,
                  'day': clock.day, 'hour': clock.hour},
        'simulated_clock': simulated,
        'current_lock_in': allowlist(active, ('id', 'status', 'week', 'dates_completed')),
        'current_date_plan': allowlist(plan, ('id', 'status', 'datetime')),
        'current_couple': allowlist(couple, ('id', 'stage', 'stage_week_index')),
        'surfaces': [surface(key, reached, reach_is_locked)
                     for key in disclosure.BY_KEY],
        'next_action': guidance(reached, facts, reach_is_locked,
                                 in_dating=(user['journey_state'] == 'dating'),
                                 partner_greeting=partner_greeting),
    }
    routes = {}
    if active and active['status'] == 'active' and user['journey_state'] == 'dating' and user['bgv_status'] == 'verified':
        calendar = '/api/v1/lock-ins/'+quote(active['id'], safe='')+'/calendar'
        routes.update(calendar=calendar, align=calendar)
        if plan and plan['status'] in ('pending_signatures', 'confirmed'):
            routes['plan'] = '/api/v1/date-plans/'+quote(plan['id'], safe='')
            routes['boundaries'] = routes['plan']
            routes['debrief'] = routes['plan']+'/debrief'
        if 'first_date' in reached:
            base = '/api/v1/lock-ins/'+quote(active['id'], safe='')
            routes.update(after_date=base+'/after-date', escalations=base+'/after-date',
                          next_level=base+'/after-date', gate=base+'/gate')
    if couple and user['journey_state'] in disclosure.RELATIONSHIP_STATES and user['bgv_status'] == 'verified':
        base = '/api/v1/couples/'+quote(couple['id'], safe='')
        routes.update(relationship=base, journey=base)
        if user['journey_state'] == 'married':
            routes['married'] = base
    for item in [*result['surfaces'], result['next_action'].get('destination')]:
        if item and item['key'] in routes:
            item['api_available'] = True
            item['request'] = {'method': 'GET', 'path': routes[item['key']]} if item['eligible'] else None
    return result
