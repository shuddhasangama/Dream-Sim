"""Date-scoped booking orchestration, simulation only. No real money is moved.

Serializable aggregate updates use the same lock ordering as date planning.
External/network adapters are intentionally not enabled inside these transactions.
Phase 5 must supply durable jobs and reconciliation for remote side effects.
"""
import json
import os
import time
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import db
import planning_service as planning
from api_contract import ApiError
from restaurant_provider import distance_km
import restaurant_registry


def enabled():
    return os.environ.get('DHASHU_RESTAURANT_MODE', 'disabled') == 'simulation'


def now():
    return int(time.time())


def provider():
    return restaurant_registry.Router()


def owned(conn, uid, pid):
    plan = db.fetch_one(conn, 'DatePlan', id=pid)
    if not plan:
        raise ApiError('not_found', 'Date not found.', 404)
    pair = db.fetch_one(conn, 'LockIn', id=plan['lockin_id'])
    if not pair or uid not in (pair['user_a'], pair['user_b']):
        raise ApiError('not_found', 'Date not found.', 404)
    return pair, plan


def load(conn, pid):
    row = db.fetch_one(conn, 'RestaurantBooking', id=pid)
    return json.loads(row['payload_json']) if row else {
        'revision': 0, 'state': 'not_started', 'options': [], 'approvals': {},
        'payment': 'unpaid', 'refund': 'none', 'reference': None}


MESSAGES = {
    'not_started': 'Find restaurant options for your agreed date.',
    'shortlist': 'Choose a restaurant. Your match needs to approve the same option.',
    'ready_to_pay': 'Both approved. One partner can simulate the deposit for the table.',
    'confirmed': 'Simulation confirmed. No real table has been reserved.',
    'unknown': 'Confirmation is uncertain. Check status before trying anything else.',
    'cancelled': 'Simulated reservation cancelled.',
    'unavailable': 'This option is no longer available. Search again.',
    'changed': 'The quote changed. Search again and both approve a new quote.',
    'expired': 'These quotes expired. Search again for current options.',
    'empty': 'No suitable options within 3 km. Review your date preferences.',
    'budget_limit_required': 'Choose a budget with an upper limit before searching.',
    'payment_failed': 'Simulated payment failed. No reservation was submitted.',
}


def view(conn, uid, pid):
    pair, plan = owned(conn, uid, pid)
    if not enabled():
        return None
    row = load(conn, pid)
    saved = db.fetch_one(conn, 'BookingSnapshot', dateplan_id=pid)
    snapshot = json.loads(saved['payload_json']) if saved else {}
    date_open = plan['status'] in ('pending_signatures','confirmed') and pair['status'] == 'active' and not db.fetch_one(conn,'DateResolution',dateplan_id=pid)
    other = pair['user_b'] if uid == pair['user_a'] else pair['user_a']
    mode=row.get('mode','simulation' if row['revision'] else os.environ.get('DHASHU_RESTAURANT_MODE','simulation'))
    mismatch=mode!=os.environ.get('DHASHU_RESTAURANT_MODE','disabled')
    return {k: row.get(k) for k in ('revision','state','options','payment','refund','reference','expires_at','selected','date_time','provider_failures','selection_policy')} | {
        'mode': mode, 'message': MESSAGES[row['state']],
        'environment_mismatch':mismatch,
        'my_approval': row['approvals'].get(uid), 'partner_approval': row['approvals'].get(other),
        'date_open': bool(date_open) and not mismatch,
        'can_pay': plan['status'] == 'confirmed' and bool(date_open) and not mismatch,
        'needs_budget_cap': snapshot.get('budget_per_person_minor',{}).get('max') is None,
        'currency': snapshot.get('currency','INR'), 'currency_exponent':snapshot.get('currency_exponent',2),
        'payer_is_me': row.get('payer') == uid,
    }


def search(snapshot, plan, adapter):
    request = {**snapshot, 'date_time': plan['datetime'], 'simulation': adapter.name=='simulation'}
    # Preserve valid real timestamps with the market timezone; old simulator
    # week/day strings remain explicitly marked simulation-only.
    try:
        stamp = datetime.fromisoformat(plan['datetime'])
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=ZoneInfo(snapshot['timezone']))
        request['date_time'] = stamp.isoformat()
    except ValueError:
        pass
    found = {}
    for radius in (1, 2, 3):
        for option in adapter.search(request, radius):
            distance = min(distance_km(p, option) for p in snapshot['neighbourhoods'])
            bounds = snapshot['budget_per_person_minor']
            if (not option['available'] or distance > radius or option['currency'] != snapshot['currency']
                or not set(snapshot['cuisines']) & set(option['cuisines'])
                or not set(snapshot['dietary_requirements']) <= set(option['diets'])
                or not bounds['min'] <= option['estimate_per_person_minor'] <= bounds['max']):
                continue
            found[option['id']] = {**option, 'distance_km': round(distance, 2),
                'quote_id': uuid.uuid4().hex, 'date_time': request['date_time'],
                'party_size': 2, 'mode': 'simulation'}
        if len(adapter.shortlist(list(found.values()))) >= 3:
            break
    return adapter.shortlist(list(found.values()))


def act(conn, uid, pid, body):
    if not enabled():
        raise ApiError('not_found', 'Restaurant simulation is not enabled.', 404)
    with planning.transition(conn):
        pair, plan = owned(conn, uid, pid)
        row = load(conn, pid)
        if row.get('mode','simulation')!='simulation':
            raise ApiError('environment_mismatch','Use the environment that created this restaurant request.',409)
        row['mode']='simulation'
        if type(body.get('revision')) is not int or body['revision'] != row['revision']:
            raise ApiError('state_conflict', 'Refresh the date plan before continuing.', 409)
        action = body.get('action')
        if not isinstance(action, str) or action not in {'search','approve','pay','reconcile','cancel','retry_refund'}:
            raise ApiError('validation_error', 'Unknown booking action.')
        if action in {'search','approve','pay'}:
            planning.owned_plan(conn, uid, pid)
            if db.fetch_one(conn,'DateResolution',dateplan_id=pid):
                raise ApiError('state_conflict','This date has already finished.',409)
        adapter = provider()
        if action == 'search':
            if row['state'] in {'confirmed','unknown','ready_to_pay','payment_failed'} or row['refund'] == 'failed':
                raise ApiError('state_conflict', 'Resolve the current reservation before searching again.', 409)
            saved = db.fetch_one(conn, 'BookingSnapshot', dateplan_id=pid)
            if not saved:
                raise ApiError('preferences_required', 'Arrange a date with shared neighbourhoods first.', 409)
            snapshot = json.loads(saved['payload_json'])
            if snapshot['budget_per_person_minor']['max'] is None and body.get('max_per_person_minor') is not None:
                cap = body['max_per_person_minor']
                if type(cap) is not int or not snapshot['budget_per_person_minor']['min'] < cap <= 1000000000:
                    raise ApiError('validation_error','Enter a spending ceiling above the minimum of your budget band.')
                snapshot['budget_per_person_minor']['max'] = cap
            row.update(options=[], approvals={}, selected=None, reference=None, payment='unpaid', refund='none', payer=None)
            if snapshot['budget_per_person_minor']['max'] is None:
                row['state'] = 'budget_limit_required'
            else:
                row['options'] = search(snapshot, plan, adapter)
                row['provider_failures']=adapter.failures
                row['selection_policy']=adapter.settings['selection_policy']
                row['state'] = 'shortlist' if row['options'] else 'empty'
                row['expires_at'] = now() + 900
                row['date_time'] = row['options'][0]['date_time'] if row['options'] else plan['datetime']
        elif action == 'approve':
            if row['state'] != 'shortlist':
                raise ApiError('state_conflict', 'Search for current restaurant options first.', 409)
            quote = next((q for q in row['options'] if q['quote_id'] == body.get('quote_id')), None)
            if not quote:
                raise ApiError('validation_error', 'Choose a current restaurant option.')
            if now() >= row['expires_at']:
                row.update(state='expired', approvals={})
            else:
                row['approvals'][uid] = quote['quote_id']
                if all(row['approvals'].get(u) == quote['quote_id'] for u in (pair['user_a'],pair['user_b'])):
                    row.update(state='ready_to_pay', selected=quote)
        elif action == 'pay':
            if plan['status'] != 'confirmed':
                raise ApiError('agreement_required', 'Both partners need to sign the date playbook before the deposit step.', 409)
            if row['state'] not in {'ready_to_pay','payment_failed'}:
                raise ApiError('state_conflict', 'Both partners must approve the same option first.', 409)
            check = adapter.recheck(row['selected'])
            if now() >= row['expires_at']:
                row.update(state='expired', approvals={})
            elif not check['available']:
                row.update(state='unavailable', approvals={})
            elif check.get('changed'):
                row.update(state='changed', approvals={})
            elif adapter.scenario == 'payment_failed':
                row.update(state='payment_failed', payment='failed')
            else:
                # Simulator ledger only. Never create a BillingEntitlement or
                # claim a Razorpay capture from a user-supplied success value.
                attempt = uuid.uuid4().hex
                outcome = adapter.reserve(row['selected'], attempt)
                row.update(attempt_id=attempt, provider=row['selected'].get('provider_id','simulation'), payment='captured_simulation',
                           payer=uid, state=outcome['status'], reference=outcome['reference'])
        elif action == 'reconcile':
            if row['state'] != 'unknown':
                raise ApiError('state_conflict', 'Only uncertain reservations need a status check.', 409)
            outcome = adapter.status(row['attempt_id'], row['selected'])
            row.update(state=outcome['status'], reference=outcome['reference'])
        elif action == 'cancel':
            if row['state'] == 'unknown':
                raise ApiError('state_conflict', 'Check reservation status before cancelling.', 409)
            if row['state'] == 'confirmed':
                outcome = adapter.cancel(row['reference'],row['selected'])
                row.update(state=outcome['status'], refund=outcome['refund'])
            elif row['state'] in {'ready_to_pay','payment_failed','shortlist'}:
                row.update(state='cancelled', approvals={})
            else:
                raise ApiError('state_conflict', 'There is no active reservation to cancel.', 409)
        elif action == 'retry_refund':
            if row['state'] != 'cancelled' or row['refund'] != 'failed':
                raise ApiError('state_conflict', 'There is no failed refund to retry.', 409)
            row['refund'] = adapter.cancel(row['reference'],row['selected'])['refund']
        row['revision'] += 1
        planning.save(conn, 'RestaurantBooking', {'id':pid, 'payload_json':json.dumps(row)})
        planning.save(conn, 'RestaurantEvent', {'id':uuid.uuid4().hex, 'dateplan_id':pid, 'actor_id':uid,
            'created_at':now(), 'payload_json':json.dumps({'action':action, **row})})
    return view(conn, uid, pid)
