"""Atomic weekly generation and decisions shared by web and JSON adapters."""
from contextlib import contextmanager

import auth_sessions
import async_rehearsal
import cadence
import clock as clock_module
import db
import lockin
import signup_verification
from api_contract import ApiError
from generate_users import from_user_row

sql = auth_sessions.sql


@contextmanager
def transition(conn):
    # Conservative beta serialization: includes both users and all candidate
    # edges. Shared by the HTML and JSON paths; no commit-per-row helpers inside.
    with auth_sessions.transaction(conn):
        if db._is_postgres_connection(conn):
            sql(conn, 'LOCK TABLE "User", "Match", "LockIn", "MatchBatch" IN SHARE ROW EXCLUSIVE MODE')
        yield


def active_for(conn, uid):
    return next((r for r in db.fetch_all(conn, 'LockIn', status='active')
                 if uid in (r['user_a'], r['user_b'])), None)


def status(row, clock):
    return cadence.match_status({
        'revealed_at': clock_module.SimulationClock.parse(row['week'], row['revealed_at']),
        'window_closes_at': clock_module.SimulationClock.parse(row['week'], row['window_closes_at']),
        'action': row['action']}, clock)


def eligible_user(conn, uid):
    row = db.fetch_one(conn, 'User', id=uid)
    if not row or row['journey_state'] != 'dating' or row['bgv_status'] != 'verified':
        raise ApiError('matching_unavailable', 'Matching requires verified Dating profiles.', 403)
    return from_user_row(row)


def prepare(conn, uid, clock):
    with transition(conn):
        user = eligible_user(conn, uid)
        if active_for(conn, uid):
            raise ApiError('reach_locked', 'You are already locked in.', 409)
        existing = db.fetch_all(conn, 'Match', user_id=uid, week=clock.week)
        batch = db.fetch_one(conn, 'MatchBatch', user_id=uid, week=clock.week)
        if batch:
            return sorted(existing, key=lambda r: r['slot'])
        if clock_module.phase(clock) == 'before_week_start' and not async_rehearsal.enabled():
            raise ApiError('week_not_started', 'The matching week has not opened.', 409)
        if not existing:
            pool = [from_user_row(r) for r in db.fetch_all(conn, 'User', journey_state='dating')]
            active = db.fetch_all(conn, 'LockIn', status='active')
            locked = {uid for r in active for uid in (r['user_a'], r['user_b'])}
            recent = {r['candidate_id'] for r in db.fetch_all(conn, 'Match', user_id=uid)
                      if max(1, clock.week - 8) <= r['week'] < clock.week}
            for m in cadence.generate_week_matches(user, pool, clock.week, locked, recent):
                sql(conn, '''INSERT INTO "Match"
                    (id,user_id,candidate_id,week,slot,revealed_at,window_closes_at)
                    VALUES (?,?,?,?,?,?,?)''',
                    (f'{uid}:{clock.week}:{m["slot"]}', uid, m['candidate_id'], clock.week,
                     m['slot'], str(m['revealed_at']), str(m['window_closes_at'])))
        # Persist even an empty result, so polling/pool changes cannot reshuffle a
        # user's week. Adopt existing legacy rows without changing their choices.
        sql(conn, 'INSERT INTO "MatchBatch" (id,user_id,week,generated_at) VALUES (?,?,?,?)',
            (f'{uid}:{clock.week}', uid, clock.week, str(clock)))
        return sorted(db.fetch_all(conn, 'Match', user_id=uid, week=clock.week), key=lambda r: r['slot'])


def decide(conn, uid, match_id, action, pass_reason, clock):
    if action not in ('interest', 'pass'):
        raise ApiError('validation_error', 'Action must be interest or pass.')
    if pass_reason is not None and (not isinstance(pass_reason, str) or len(pass_reason) > 1000):
        raise ApiError('validation_error', 'Pass reason must be text of at most 1000 characters.')
    if action == 'interest' and pass_reason:
        raise ApiError('validation_error', 'Pass reason applies only to pass.')
    reason = (pass_reason or '').strip() or None if action == 'pass' else None
    with transition(conn):
        row = db.fetch_one(conn, 'Match', id=match_id)
        if row is None or row['user_id'] != uid:
            raise ApiError('not_found', 'Match not found.', 404)
        eligible_user(conn, uid)
        if row['action'] != 'none':
            if row['action'] == action and row['pass_reason'] == reason:
                return {'match_id': row['id'], 'action': action, 'replayed': True}
            raise ApiError('state_conflict', 'A decision has already been recorded.', 409)
        if row['week'] != clock.week or status(row, clock) != 'open':
            raise ApiError('match_window_closed', 'This match is not open for a decision.', 409)
        if active_for(conn, uid):
            raise ApiError('reach_locked', 'You are already locked in.', 409)
        if action == 'interest':
            if not signup_verification.is_satisfied(db.fetch_one(conn, 'Account', user_id=uid)):
                raise ApiError('contact_verification_required', 'Verify your email or phone first.', 403)
            eligible_user(conn, row['candidate_id'])
            if active_for(conn, row['candidate_id']):
                raise ApiError('match_unavailable', 'This match is no longer available.', 409)
        sql(conn, 'UPDATE "Match" SET action = ?, pass_reason = ? WHERE id = ?',
            (action, reason, row['id']))
        their = db.fetch_one(conn, 'Match', user_id=row['candidate_id'], candidate_id=uid, week=row['week'])
        if action == 'interest' and their and their['action'] == 'interest':
            # Both approvals were checked when submitted; also check the other
            # side now in case their contact approval has since been revoked.
            if not signup_verification.is_satisfied(db.fetch_one(conn, 'Account', user_id=row['candidate_id'])):
                raise ApiError('match_unavailable', 'This match is no longer available.', 409)
            pair = lockin.on_mutual_interest(uid, row['candidate_id'], row['week'], clock)
            lid = f'lockin:{"|".join(sorted([uid, row["candidate_id"]]))}:{row["week"]}'
            if db.fetch_one(conn, 'LockIn', id=lid):
                raise ApiError('state_conflict', 'This pairing has already completed its matching cycle.', 409)
            sql(conn, '''INSERT INTO "LockIn" (id,user_a,user_b,week,created_at,status)
                        VALUES (?,?,?,?,?,?)''',
                (lid, pair['user_a'], pair['user_b'], pair['week'], pair['created_at'], pair['status']))
            if async_rehearsal.enabled():
                async_rehearsal.transfer_drafts(conn, lid, (uid, row['candidate_id']), row['week'])
            for owner, partner in ((uid, row['candidate_id']), (row['candidate_id'], uid)):
                sql(conn, 'DELETE FROM "Match" WHERE user_id = ? AND week = ? AND candidate_id <> ?',
                    (owner, clock.week, partner))
        return {'match_id': row['id'], 'action': action, 'replayed': False}
