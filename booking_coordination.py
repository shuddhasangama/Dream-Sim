"""Phase 3: owned pair/date preferences and immutable phase-4 handoffs."""
import hashlib
import json

import booking_markets
import calendar_dating
import date_alignment
import db
import planning_service as planning
from api_contract import ApiError


def plan_summary(conn, pid):
    """Call only after checking plan ownership. Excludes internal routing fields."""
    row = db.fetch_one(conn, 'BookingSnapshot', dateplan_id=pid)
    if not row:
        return None
    payload = json.loads(row['payload_json'])
    return {k: payload[k] for k in ('city', 'currency', 'timezone', 'neighbourhoods', 'cuisines',
                                    'budget_bands', 'budget_basis', 'reservation_status')}


def scope(conn, active):
    plans = db.fetch_all(conn, 'DatePlan', lockin_id=active['id'])
    cycle = len(plans) + (0 if planning.current_plan(conn, active['id']) else 1)
    return f"{active['id']}|week:{active['week']}|cycle:{cycle}"


def _id(scope_id, uid):
    return hashlib.sha256(json.dumps([scope_id, uid]).encode()).hexdigest()


def view(conn, uid, lid):
    active = planning.pair(conn, uid, lid)
    if not booking_markets.enabled():
        return None
    plan = planning.current_plan(conn, lid)
    frozen = db.fetch_one(conn, 'BookingSnapshot', dateplan_id=plan['id']) if plan else None
    if frozen:
        snapshot = json.loads(frozen['payload_json'])
        return {'editable': False, 'state': 'frozen', 'message': 'Preferences agreed. Restaurant booking is pending.',
                'snapshot': snapshot, 'ready': True, 'mine': [], 'neighbourhoods': [], 'scope': frozen['scope_id']}
    if plan:
        return {'editable': False, 'state': 'legacy_plan', 'message': 'This date was arranged before neighbourhood planning was enabled.',
                'ready': False, 'mine': [], 'neighbourhoods': []}
    users = [active['user_a'], active['user_b']]
    stats = [db.load_json_field(db.fetch_one(conn, 'User', id=u)['stats_json'], {}) for u in users]
    markets = [booking_markets.for_city(s.get('city')) for s in stats]
    scope_id = scope(conn, active)
    base = {'scope': scope_id, 'editable': True, 'ready': False, 'mine': [], 'neighbourhoods': [], 'revision': 0}
    if any(m is None for m in markets):
        return {**base, 'state': 'unsupported_market', 'message': 'Neighbourhood planning is not available in this city yet.'}
    if markets[0]['id'] != markets[1]['id']:
        return {**base, 'state': 'different_cities', 'message': 'You need a shared dating city before choosing a neighbourhood.'}
    market = markets[0]
    rows = [db.fetch_one(conn, 'BookingPreference', id=_id(scope_id, u)) for u in users]
    # A market change invalidates earlier choices; do not reinterpret old IDs.
    choices = [json.loads(r['places_json']) if r and r['market_id'] == market['id'] else [] for r in rows]
    index = users.index(uid)
    mine = rows[index]
    shared_places = sorted(set(choices[0]) & set(choices[1]))
    cuisines = date_alignment.shared_cuisines(stats[0].get('cuisine'), stats[1].get('cuisine'))
    def array(v):
        return v if isinstance(v, list) else [v] if v else []
    budgets = [b for b in date_alignment.options_for('budget', market['city'])
               if b in array(stats[0].get('budget')) and b in array(stats[1].get('budget'))]
    slots = calendar_dating.compute_overlap(*(planning.slots(conn, lid, u) for u in users))
    if not choices[index]:
        state, message = 'your_preferences', 'Choose neighbourhoods you are comfortable meeting in.'
    elif not choices[1-index]:
        state, message = 'waiting_partner', 'Your neighbourhoods are saved. Waiting for your match.'
    elif not date_alignment.ready_for_pair(*stats):
        state, message = 'preferences_needed', 'Both partners need to save diet, cuisine and budget.'
    elif not shared_places:
        state, message = 'no_neighbourhood_overlap', 'No shared neighbourhood yet. Review your choices together.'
    elif not cuisines:
        state, message = 'no_cuisine_overlap', 'Choose at least one cuisine you both enjoy.'
    elif not budgets:
        state, message = 'no_budget_overlap', 'Choose a budget band that works for both of you.'
    elif not slots:
        state, message = 'no_slot_overlap', 'Select a time that works for both of you.'
    else:
        state, message = 'ready', 'Shared preferences are ready. Choose a time below.'
    return {**base, 'market': {k: market[k] for k in ('id', 'country', 'city', 'currency', 'timezone')},
            'neighbourhoods': [{'id': p['id'], 'name': p['name']} for p in market['neighbourhoods']],
            'mine': choices[index], 'revision': mine['revision'] if mine else 0,
            'shared_neighbourhoods': shared_places, 'shared_cuisines': cuisines, 'shared_budgets': budgets,
            'state': state, 'message': message, 'ready': state == 'ready'}


def update(conn, uid, lid, body):
    with planning.transition(conn):
        current = view(conn, uid, lid)
        if current is None:
            raise ApiError('not_found', 'Neighbourhood planning is not enabled.', 404)
        if not current['editable']:
            raise ApiError('state_conflict', 'Preferences are frozen for this date.', 409)
        if not current.get('market'):
            raise ApiError('market_unavailable', current['message'], 409)
        if body.get('scope') != current['scope'] or type(body.get('revision')) is not int or body['revision'] != current['revision']:
            raise ApiError('state_conflict', 'Refresh the calendar before saving.', 409)
        chosen = body.get('neighbourhoods')
        valid = {p['id'] for p in current['neighbourhoods']}
        if not isinstance(chosen, list) or not 1 <= len(chosen) <= len(valid) or any(not isinstance(p, str) or p not in valid for p in chosen) or len(set(chosen)) != len(chosen):
            raise ApiError('validation_error', 'Choose one or more listed neighbourhoods.')
        if sorted(chosen) == sorted(current['mine']):
            return
        planning.save(conn, 'BookingPreference', {'id': _id(current['scope'], uid), 'scope_id': current['scope'],
            'lockin_id': lid, 'user_id': uid, 'market_id': current['market']['id'],
            'places_json': json.dumps(sorted(chosen)), 'revision': current['revision'] + 1})


def freeze(conn, uid, lid, pid, day, meal):
    """Called inside the date-confirmation transaction, BEFORE saving DatePlan."""
    current = view(conn, uid, lid)
    if current is None:
        return None
    if not current['ready']:
        raise ApiError('booking_preferences_required', current['message'], 409)
    market = next(m for m in booking_markets.markets() if m['id'] == current['market']['id'])
    active = planning.pair(conn, uid, lid)
    diets = [db.load_json_field(db.fetch_one(conn, 'User', id=u)['stats_json'], {}).get('diet')
             for u in (active['user_a'], active['user_b'])]
    payload = {**current['market'], 'lockin_id': lid, 'scope': current['scope'],
        'neighbourhoods': [p for p in market['neighbourhoods'] if p['id'] in current['shared_neighbourhoods']],
        'cuisines': current['shared_cuisines'], 'budget_bands': current['shared_budgets'],
        'budget_per_person_minor': market['budget_ranges_minor'][current['shared_budgets'][0]],
        'dietary_requirements': sorted(set(diets)), 'budget_basis': 'per_person',
        'slot': {'day': day, 'meal_slot': meal}, 'provider_routes': market['providers']}
    payload = booking_markets.search_request(payload, pid)
    planning.save(conn, 'BookingSnapshot', {'id': pid, 'dateplan_id': pid, 'lockin_id': lid,
        'scope_id': current['scope'], 'payload_json': json.dumps(payload)})
    return payload
