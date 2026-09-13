"""Date planning transactions shared by HTML and JSON adapters.

No provider calls. Payment entitlements are read, never fabricated here.
"""
from contextlib import contextmanager
import json
import uuid

import auth_sessions
import calendar_dating
import ceremony
import date_alignment
import dateplan
import db
import payments
import lockin
from api_contract import ApiError

sql = auth_sessions.sql


@contextmanager
def transition(conn):
    with auth_sessions.transaction(conn):
        if db._is_postgres_connection(conn):
            sql(conn, 'LOCK TABLE "User", "LockIn", "Availability", "DatePlan", "Ceremony", "Signature", "Payment", "DateOutcome", "DateFeedback", "DateResolution", "ComplianceEvent", "StageGate", "DateCharge" IN SHARE ROW EXCLUSIVE MODE')
        yield


def save(conn, table, row):
    # Internal callers only; identifiers never originate in a request.
    columns = list(row)
    names = ','.join('"'+k+'"' for k in columns)
    updates = ','.join('"'+k+'"=excluded."'+k+'"' for k in columns if k != 'id')
    sql(conn, f'INSERT INTO "{table}" ({names}) VALUES ({",".join("?" for _ in columns)}) ON CONFLICT(id) DO UPDATE SET {updates}',
        tuple(int(row[k]) if isinstance(row[k], bool) else row[k] for k in columns))


def pair(conn, uid, lid):
    row = db.fetch_one(conn, 'LockIn', id=lid)
    if not row or uid not in (row['user_a'], row['user_b']):
        raise ApiError('not_found', 'Pair not found.', 404)
    actor = db.fetch_one(conn, 'User', id=uid)
    if not actor or actor['bgv_status'] != 'verified' or actor['journey_state'] != 'dating':
        raise ApiError('planning_unavailable', 'Date planning requires a verified Dating profile.', 403)
    if row['status'] != 'active':
        raise ApiError('state_conflict', 'This pair is no longer active.', 409)
    return row


def current_plan(conn, lid):
    rows = db.fetch_all(conn, 'DatePlan', lockin_id=lid)
    return next((r for r in rows if r['status'] in ('pending_signatures', 'confirmed')), None)


def owned_plan(conn, uid, pid):
    row = db.fetch_one(conn, 'DatePlan', id=pid)
    if not row:
        raise ApiError('not_found', 'Date plan not found.', 404)
    active = pair(conn, uid, row['lockin_id'])
    if row['status'] not in ('pending_signatures', 'confirmed'):
        raise ApiError('state_conflict', 'This date is closed.', 409)
    return active, row


def paid(conn, uid, purpose, scope):
    return payments.has_paid(db.fetch_all(conn, 'Payment', user_id=uid), uid, purpose, scope)


def availability_scope(conn, lid):
    rows=db.fetch_all(conn,'DatePlan',lockin_id=lid)
    cycle=len(rows)+(0 if current_plan(conn,lid) else 1)
    return lid if cycle<=1 else lid+':cycle:'+str(cycle)


def require_paid(conn, uid, purpose, scope):
    if not paid(conn, uid, purpose, scope):
        raise ApiError('payment_required', 'The '+purpose+' entitlement is required.', 403)


def slots(conn, lid, uid):
    return [(r['day'], r['meal_slot']) for r in db.fetch_all(conn, 'Availability', lockin_id=lid, user_id=uid)]


def alignment(conn, uid, lid, body):
    with transition(conn):
        pair(conn, uid, lid)
        if current_plan(conn, lid):
            raise ApiError('state_conflict', 'Alignment is frozen for the current date.', 409)
        row = db.fetch_one(conn, 'User', id=uid)
        stats = db.load_json_field(row['stats_json'], {})
        result = date_alignment.validate(body, stats.get('city'))
        if not result['ok']:
            raise ApiError('validation_error', result['error'])
        stats.update(result['stats'])
        sql(conn, 'UPDATE "User" SET stats_json=? WHERE id=?', (json.dumps(stats, ensure_ascii=False), uid))


def availability(conn, uid, lid, chosen):
    valid = calendar_dating.valid_slots()
    if not isinstance(chosen, list) or len(chosen) > len(valid):
        raise ApiError('validation_error', 'Slots must be an array of valid weekend slots.')
    parsed = []
    for item in chosen:
        if not isinstance(item, dict) or set(item) != {'day', 'meal_slot'} or not all(isinstance(v, str) for v in item.values()):
            raise ApiError('validation_error', 'Each slot requires day and meal_slot.')
        slot = (item['day'], item['meal_slot'])
        if slot not in valid or slot in parsed:
            raise ApiError('validation_error', 'Invalid or duplicate slot.')
        parsed.append(slot)
    with transition(conn):
        pair(conn, uid, lid)
        if current_plan(conn, lid):
            raise ApiError('state_conflict', 'Availability is frozen for the current date.', 409)
        require_paid(conn, uid, payments.AVAILABILITY, availability_scope(conn,lid))
        if set(slots(conn, lid, uid)) == set(parsed):
            return
        sql(conn, 'DELETE FROM "Availability" WHERE lockin_id=? AND user_id=?', (lid, uid))
        for day, meal in parsed:
            save(conn, 'Availability', {'id': uuid.uuid4().hex, 'lockin_id': lid, 'user_id': uid, 'day': day, 'meal_slot': meal})


def confirm(conn, uid, lid, day, meal, slot_datetime, cycle=None):
    if not isinstance(day, str) or not isinstance(meal, str) or (day, meal) not in calendar_dating.valid_slots():
        raise ApiError('validation_error', 'Select a valid weekend slot.')
    with transition(conn):
        active = pair(conn, uid, lid)
        existing = current_plan(conn, lid)
        plans = db.fetch_all(conn, 'DatePlan', lockin_id=lid)
        expected = len(plans) if existing else len(plans)+1
        if (cycle is not None and (type(cycle) is not int or cycle != expected)) or (expected>1 and cycle is None):
            raise ApiError('state_conflict', 'Use the current calendar cycle number.', 409)
        stamp = slot_datetime(active['week'], day, meal)
        if existing:
            if existing['datetime'] == stamp and existing['meal'] == meal:
                return existing
            raise ApiError('state_conflict', 'A different date has already been selected.', 409)
        a, b = [db.load_json_field(db.fetch_one(conn, 'User', id=who)['stats_json'], {}) for who in (active['user_a'], active['user_b'])]
        if not date_alignment.ready_for_pair(a, b):
            raise ApiError('alignment_required', 'Both partners must complete date alignment.', 409)
        overlap = calendar_dating.compute_overlap(slots(conn, lid, active['user_a']), slots(conn, lid, active['user_b']))
        if (day, meal) not in overlap:
            raise ApiError('overlap_required', 'Both partners must select this slot.', 409)
        for who in (active['user_a'], active['user_b']):
            require_paid(conn, who, payments.AVAILABILITY, availability_scope(conn,lid))
        venue = calendar_dating.suggest_venue(day, meal, a.get('diet'), b.get('diet'))
        shared = date_alignment.shared_cuisines(a.get('cuisine'), b.get('cuisine'))
        plan = dateplan.generate_plan(lid, {'day': day, 'meal_slot': meal},
            {**venue, 'cuisine': shared[0] if shared else venue.get('cuisine')}, stamp,
            'pay-your-own', {}, {}, {'budget_estimate': date_alignment.lower_budget(a.get('budget'), b.get('budget'), a.get('city'))})
        # Every cycle has its own identifier; old signatures/history remain scoped.
        pid = 'plan:'+lid
        if db.fetch_one(conn, 'DatePlan', id=pid):
            prior = db.fetch_one(conn, 'DateResolution', dateplan_id=pid)
            if not prior:
                raise ApiError('state_conflict', 'The previous date cycle must be resolved first.', 409)
            pid += ':'+uuid.uuid4().hex
        plan = {'id': pid, **plan}
        for key in ('selections_a_json', 'selections_b_json'):
            plan[key] = json.dumps(plan[key])
        save(conn, 'DatePlan', plan)
        return plan


def no_overlap(conn, uid, lid, choice):
    """Existing web recovery, serialized with confirmation; API follows in block 4."""
    if choice not in ('return_to_pool', 'next_weekend'):
        raise ApiError('validation_error', 'Choose a calendar recovery action.')
    with transition(conn):
        active = pair(conn, uid, lid)
        if current_plan(conn, lid):
            raise ApiError('state_conflict', 'A date plan already exists.', 409)
        if calendar_dating.compute_overlap(slots(conn, lid, active['user_a']), slots(conn, lid, active['user_b'])):
            raise ApiError('state_conflict', 'The pair already has shared availability.', 409)
        if choice == 'return_to_pool':
            save(conn, 'LockIn', {**active, **lockin.release(active, 'no calendar overlap')})
        else:
            sql(conn, 'DELETE FROM "Availability" WHERE lockin_id=?', (lid,))


def selections(conn, uid, pid, body):
    if any(value is not None and (not isinstance(value, str) or len(value) > 1000) for value in body.values()):
        raise ApiError('validation_error', 'Selections must be text of at most 1000 characters.')
    with transition(conn):
        active, plan = owned_plan(conn, uid, pid)
        if plan['status'] != 'pending_signatures' or db.fetch_all(conn, 'Signature', dateplan_id=pid) or any(r.get('signed_name') for r in db.fetch_all(conn, 'Ceremony', kind=ceremony.DATE_AGREEMENT, scope_id=pid)):
            raise ApiError('state_conflict', 'Selections cannot change after signing begins.', 409)
        role = 'a' if active['user_a'] == uid else 'b'
        sql(conn, f'UPDATE "DatePlan" SET selections_{role}_json=? WHERE id=?', (json.dumps(body), pid))


def agreement_state(conn, uid, pid, now):
    return db.fetch_one(conn, 'Ceremony', user_id=uid, kind=ceremony.DATE_AGREEMENT, scope_id=pid) or ceremony.new_state(uid, ceremony.DATE_AGREEMENT, pid, now)


def persist_signature(conn, active, pid, uid, flags, now, verified):
    sig = dateplan.sign(pid, uid, flags, now, verified)
    save(conn, 'Signature', {'id': pid+':'+uid, **sig})
    if dateplan.is_confirmed(db.fetch_all(conn, 'Signature', dateplan_id=pid), active['user_a'], active['user_b']):
        sql(conn, 'UPDATE "DatePlan" SET status=? WHERE id=?', ('confirmed', pid))


def legacy_sign(conn, uid, pid, flags, now, verify_face):
    """Preserve the older HTML checkbox flow, with the same atomic mirror."""
    with transition(conn):
        active, plan = owned_plan(conn, uid, pid)
        require_paid(conn, uid, payments.AGREEMENT, pid)
        existing = db.fetch_one(conn, 'Signature', dateplan_id=pid, user_id=uid)
        if existing and dateplan.is_fully_acknowledged(existing):
            return
        persist_signature(conn, active, pid, uid, flags, now, verify_face(uid, bool(existing)))


def agreement(conn, uid, pid, body, now, verify_face):
    with transition(conn):
        active, plan = owned_plan(conn, uid, pid)
        require_paid(conn, uid, payments.AGREEMENT, pid)
        state = agreement_state(conn, uid, pid, now)
        step = body['step']
        current = ceremony.next_step(state)
        if step not in (ceremony.PLAYBOOK, ceremony.SIGN, ceremony.FACE):
            raise ApiError('validation_error', 'Unknown agreement step.')
        if step == ceremony.SIGN:
            name, acks = body.get('signed_name'), body.get('acks')
            if not isinstance(name, str) or not name.strip() or len(name) > 200 or not isinstance(acks, list) or any(not isinstance(k, str) for k in acks) or set(acks) != set(ceremony.ack_keys(ceremony.DATE_AGREEMENT)) or len(acks) != len(set(acks)):
                raise ApiError('validation_error', 'Supply your name and every required acknowledgement.')
        if ceremony.STEP_KEYS.index(step) < ceremony.STEP_KEYS.index(current):
            if step == ceremony.SIGN and state['signed_name'] != body['signed_name'].strip():
                raise ApiError('state_conflict', 'The recorded signature cannot be replaced.', 409)
            return state
        if step != current:
            raise ApiError('state_conflict', 'Complete the preceding agreement step first.', 409)
        if step == ceremony.PLAYBOOK:
            state = ceremony.ack_playbook(state)
        elif step == ceremony.SIGN:
            state = ceremony.sign(state, body['signed_name'], body['acks'], now)
        else:
            if not verify_face(uid):
                raise ApiError('face_simulation_failed', 'The simulated face step failed; you may retry.', 409)
            state = ceremony.capture_face(state)
        if ceremony.is_complete(state):
            state = ceremony.complete(state, now)
        save(conn, 'Ceremony', state)
        if ceremony.is_complete(state):
            persist_signature(conn, active, pid, uid, {k: k in ceremony.signed_acks(state) for k in dateplan.ACK_FIELDS}, now, True)
        return state
