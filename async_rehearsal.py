"""Opt-in, action-driven Dating rehearsal. No timer, reset or provider bypass.

Progress is derived from existing pair records. Only explicit date/debrief
readiness is stored here; it is not attendance, consent or feedback evidence.
Disable DHASHU_ASYNC_TEST to remove this policy from the existing journey.
"""
import os
from datetime import datetime
from urllib.parse import quote

import clock
import db
from api_contract import ApiError


def enabled():
    return clock.simulated() and os.environ.get('DHASHU_ASYNC_TEST', '').lower() == 'true'


def start_week():
    week = int(os.environ.get('DHASHU_TEST_START_WEEK', '39'))
    if week < 1:
        raise ValueError('DHASHU_TEST_START_WEEK must be positive')
    return week


def acknowledgements(conn, pid, step):
    return {r['user_id'] for r in db.fetch_all(conn, 'RehearsalReady', dateplan_id=pid, step=step)}


def snapshot(conn, uid):
    """Read-only and pair-scoped; never expose another pair's state."""
    import planning_service as planning
    import date_alignment
    import calendar_dating
    import dateplan
    active = next((r for r in db.fetch_all(conn, 'LockIn', status='active')
                   if uid in (r['user_a'], r['user_b'])), None)
    metadata = {'enabled': True, 'scope': 'pair', 'stage': 'matching',
                'message': 'Test mode: match choices stay open. Mutual interest is required before planning.',
                'request': None, 'decisions_automated': False}
    if not active:
        return clock.SimulationClock.at(start_week(), 'Mon', 10), metadata
    week, lid = active['week'], active['id']
    members = {active['user_a'], active['user_b']}
    metadata['lock_in_id'] = lid
    plan = planning.current_plan(conn, lid)
    if not plan:
        stats = [db.load_json_field(db.fetch_one(conn, 'User', id=who)['stats_json'], {}) for who in members]
        overlap = calendar_dating.compute_overlap(*[planning.slots(conn, lid, who) for who in members])
        ready = date_alignment.ready_for_pair(*stats) and bool(overlap)
        metadata.update(stage='planning' if ready else 'availability', message=(
            'Both partners have alignment and an overlapping slot. Choose your date.' if ready else
            'Save your alignment and availability. They stay saved while your partner responds; a shared slot is required.'))
        return clock.SimulationClock.at(week, 'Thu' if ready else 'Wed', 12 if ready else 18), metadata
    pid = plan['id']
    metadata['plan_id'] = pid
    if plan['status'] != 'confirmed':
        metadata.update(stage='agreement', message='Complete your agreement. Planning waits until both partners have signed.')
        return clock.SimulationClock.at(week, 'Thu', 18), metadata
    # Existing resolved relationship-gate plans remain confirmed; do not replay them.
    resolved = db.fetch_one(conn, 'DateResolution', dateplan_id=pid)
    start = datetime.fromisoformat(plan['datetime'])
    date_week = (start.date()-clock.WEEK_ONE_MONDAY).days//7+1
    day = start.weekday()
    ready_date = acknowledgements(conn, pid, 'date')
    ready_debrief = acknowledgements(conn, pid, 'debrief')
    if resolved or members <= ready_debrief:
        metadata.update(stage='resolved' if resolved else 'debrief', message=(
            'This date has been resolved. Continue through the available journey steps.' if resolved else
            'Debrief is open and will wait for your response. Your partner’s private answers remain private.'))
        return clock.SimulationClock(date_week, day, dateplan.debrief_opens_hour(plan['meal'])), metadata
    step = 'debrief' if members <= ready_date else 'date'
    mine = uid in (ready_debrief if step == 'debrief' else ready_date)
    metadata.update(stage='date' if step == 'debrief' else 'ready_for_date',
                    my_ready=mine, partner_ready=bool((ready_debrief if step == 'debrief' else ready_date) & (members-{uid})),
                    message=('Your readiness is saved. Waiting for your partner; there is no time limit.' if mine else
                             'Both partners must choose readiness to advance this rehearsal. This does not record attendance or consent.'))
    if not mine:
        metadata['request'] = {'method': 'POST', 'path': '/api/v1/rehearsal/date-plans/'+quote(pid, safe='')+'/ready',
                               'body': {'step': step}, 'label': 'Ready for Debrief' if step == 'debrief' else 'Ready for simulated date'}
    return (clock.SimulationClock(date_week, day, start.hour) if step == 'debrief' else
            clock.SimulationClock.at(week, 'Thu', 18)), metadata


def mark_ready(conn, uid, pid, step):
    import planning_service as planning
    if not enabled():
        raise ApiError('rehearsal_disabled', 'Action-driven rehearsal is disabled.', 403)
    if not isinstance(step, str) or step not in ('date', 'debrief'):
        raise ApiError('validation_error', 'Choose date or debrief readiness.')
    with planning.transition(conn):
        pair, plan = planning.owned_plan(conn, uid, pid)
        if plan['status'] != 'confirmed' or db.fetch_one(conn, 'DateResolution', dateplan_id=pid):
            raise ApiError('state_conflict', 'Both agreements must be complete on an unresolved date.', 409)
        if planning.current_plan(conn, pair['id'])['id'] != pid:
            raise ApiError('state_conflict', 'Use the current date plan.', 409)
        members = {pair['user_a'], pair['user_b']}
        if step == 'debrief' and not members <= acknowledgements(conn, pid, 'date'):
            raise ApiError('state_conflict', 'Both partners must be ready for the simulated date first.', 409)
        if uid not in acknowledgements(conn, pid, step):
            planning.sql(conn, 'INSERT INTO "RehearsalReady" (id,dateplan_id,user_id,step) VALUES (?,?,?,?)',
                         (pid+':'+uid+':'+step, pid, uid, step))
