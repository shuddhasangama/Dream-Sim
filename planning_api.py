"""Owned date-planning JSON resources; GET never creates ceremony rows."""
import os
import uuid
from flask import g, jsonify
import calendar_dating
import ceremony
import date_alignment
import dateplan
import db
import payments
import planning_service as service
import async_rehearsal
from api_contract import ApiError, allowlist, json_object


def register(api, get_db, get_clock, slot_datetime, agreement_context):
    def uid():
        return g.api_user['user_id']

    @api.post('/rehearsal/start')
    def rehearsal_start():
        json_object()
        async_rehearsal.start_intro(get_db(), uid())
        return jsonify(async_rehearsal.snapshot(get_db(), uid())[1])

    @api.put('/rehearsal/availability')
    def rehearsal_availability():
        body = json_object(required={'slots'})
        async_rehearsal.save_draft(get_db(), uid(), body['slots'])
        return jsonify(async_rehearsal.snapshot(get_db(), uid())[1])

    @api.post('/rehearsal/date-plans/<pid>/ready')
    def rehearsal_ready(pid):
        body = json_object(required={'step'})
        async_rehearsal.mark_ready(get_db(), uid(), pid, body['step'])
        return jsonify(async_rehearsal.snapshot(get_db(), uid())[1])

    def simulation_enabled():
        account = db.fetch_one(get_db(), 'Account', user_id=uid())
        return os.environ.get('BETA_DATE_SIMULATION_ENABLED', '0') == '1' and bool(account and account.get('auth_enabled'))

    def entitlement(purpose, scope):
        return {'purpose': purpose, 'scope_id': scope, 'satisfied': service.paid(get_db(), uid(), purpose, scope),
                'enforced': payments.is_enabled(), 'amount_inr': payments.fee(purpose)['amount_inr'],
                'provider_mode': 'simulation', 'api_payment_available': False}

    def slot_view(items):
        return [{'day': d, 'meal_slot': m} for d, m in items]

    def calendar(lid):
        active = service.pair(get_db(), uid(), lid)
        other = active['user_b'] if uid() == active['user_a'] else active['user_a']
        mine, theirs = service.slots(get_db(), lid, uid()), service.slots(get_db(), lid, other)
        stats = db.load_json_field(db.fetch_one(get_db(), 'User', id=uid())['stats_json'], {})
        partner_stats = db.load_json_field(db.fetch_one(get_db(), 'User', id=other)['stats_json'], {})
        plan = service.current_plan(get_db(), lid)
        return {'lock_in_id': lid, 'clock_mode': 'simulation', 'valid_slots': slot_view(calendar_dating.valid_slots()),
                'my_slots': slot_view(calendar_dating.compute_overlap(mine, mine)), 'partner_submitted': bool(theirs),
                'overlap': slot_view(calendar_dating.compute_overlap(mine, theirs)),
                'alignment': {'mine': {k: stats.get(k) for k in date_alignment.FIELDS},
                    'my_missing': date_alignment.missing(stats), 'partner_missing': date_alignment.missing(partner_stats),
                    'options': {k: date_alignment.options_for(k, stats.get('city')) for k in date_alignment.FIELDS}},
                'current_plan_id': plan['id'] if plan else None, 'editable': plan is None,
                'cycle': len(db.fetch_all(get_db(), 'DatePlan', lockin_id=lid))+(0 if plan else 1),
                'payment': entitlement(payments.AVAILABILITY, service.availability_scope(get_db(),lid))}

    def plan_view(pid):
        active, plan = service.owned_plan(get_db(), uid(), pid)
        role = 'a' if uid() == active['user_a'] else 'b'
        sigs = db.fetch_all(get_db(), 'Signature', dateplan_id=pid)
        return {**allowlist(plan, ('id', 'lockin_id', 'datetime', 'meal', 'venue', 'cuisine', 'budget_estimate', 'bill_split', 'status', 'cancel_notice_hrs', 'cancel_fee')),
                'my_selections': db.load_json_field(plan['selections_'+role+'_json'], {}),
                'my_signed': any(s['user_id'] == uid() and dateplan.is_fully_acknowledged(s) for s in sigs),
                'partner_signed': any(s['user_id'] != uid() and dateplan.is_fully_acknowledged(s) for s in sigs),
                'payment': entitlement(payments.AGREEMENT, pid), 'face_mode': 'simulation',
                'face_simulation_available': simulation_enabled()}

    def agreement_view(pid):
        service.owned_plan(get_db(), uid(), pid)
        state = service.agreement_state(get_db(), uid(), pid, str(get_clock()))
        return {'plan_id': pid, 'step': ceremony.next_step(state), 'complete': ceremony.is_complete(state),
                'my_signed_name': state.get('signed_name'), 'my_signed_at': state.get('signed_at'),
                'acknowledgements': ceremony.acks_for(ceremony.DATE_AGREEMENT),
                'clauses': ceremony.clauses_for(ceremony.DATE_AGREEMENT, agreement_context(pid)),
                'face_mode': 'simulation', 'face_simulation_available': simulation_enabled(),
                'payment': entitlement(payments.AGREEMENT, pid)}

    @api.get('/lock-ins/<lid>/calendar')
    def get_calendar(lid):
        return jsonify(calendar(lid))

    @api.put('/lock-ins/<lid>/alignment')
    def set_alignment(lid):
        body = json_object(required={'budget', 'diet', 'cuisine'})
        if not isinstance(body['diet'], str) or any(not isinstance(body[k], list) or not body[k] or any(not isinstance(v, str) for v in body[k]) for k in ('budget', 'cuisine')):
            raise ApiError('validation_error', 'Budget and cuisine require arrays; diet requires text.')
        # Reject unsupported choices instead of silently dropping them.
        choices = calendar(lid)['alignment']['options']
        if body['diet'] not in choices['diet'] or any(len(body[k]) != len(set(body[k])) or any(v not in choices[k] for v in body[k]) for k in ('budget', 'cuisine')):
            raise ApiError('validation_error', 'Choose only the advertised alignment options.')
        service.alignment(get_db(), uid(), lid, body)
        return jsonify(calendar(lid))

    @api.put('/lock-ins/<lid>/availability')
    def set_availability(lid):
        body = json_object(required={'slots'})
        service.availability(get_db(), uid(), lid, body['slots'])
        return jsonify(calendar(lid))

    @api.post('/lock-ins/<lid>/date-plan')
    def confirm(lid):
        body = json_object(required={'day', 'meal_slot'}, optional={'cycle'})
        plan = service.confirm(get_db(), uid(), lid, body['day'], body['meal_slot'], slot_datetime, body.get('cycle'))
        return jsonify(plan_view(plan['id']))

    @api.get('/date-plans/<pid>')
    def get_plan(pid):
        return jsonify(plan_view(pid))

    @api.put('/date-plans/<pid>/selections')
    def set_selections(pid):
        body = json_object(required={'dietary', 'dress'})
        service.selections(get_db(), uid(), pid, body)
        return jsonify(plan_view(pid))

    @api.get('/date-plans/<pid>/agreement')
    def get_agreement(pid):
        return jsonify(agreement_view(pid))

    @api.post('/date-plans/<pid>/agreement/steps')
    def agreement_step(pid):
        body = json_object(required={'step'}, optional={'signed_name', 'acks'})
        if body['step'] != 'sign' and set(body) != {'step'}:
            raise ApiError('validation_error', 'Only the sign step accepts name and acknowledgements.')
        service.owned_plan(get_db(), uid(), pid)
        if body['step'] == 'face' and not simulation_enabled():
            raise ApiError('simulation_disabled', 'A real face provider is not configured; the beta simulation is disabled.', 403)
        service.agreement(get_db(), uid(), pid, body, str(get_clock()), lambda who: dateplan.verify_face(who, seed=uuid.uuid4().hex))
        return jsonify(agreement_view(pid))
