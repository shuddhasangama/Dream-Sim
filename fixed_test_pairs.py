"""Opt-in, operator-assigned synthetic pairs; never real matching policy."""
import os

import auth_sessions
import db

PREFIX = 'test_blr_20260921_'


def configured():
    import async_rehearsal
    if not async_rehearsal.enabled():
        return {}
    result = {}
    for value in os.environ.get('DHASHU_FIXED_TEST_PAIRS', '').split(','):
        if not value.strip():
            continue
        if not value.strip().isdigit() or not 1 <= int(value) <= 10:
            raise ValueError('DHASHU_FIXED_TEST_PAIRS must contain pair numbers 01 to 10.')
        n = int(value)
        a, b = f'{PREFIX}f{n:02d}', f'{PREFIX}m{n:02d}'
        result[a], result[b] = b, a
    return result


def mutual_pair(conn, uid):
    partner = configured().get(uid)
    if not partner:
        return False
    return any({p['user_a'], p['user_b']} == {uid, partner}
               for p in db.fetch_all(conn, 'LockIn', status='active'))


def permits(a, b):
    pairs = configured()
    return (a not in pairs or pairs[a] == b) and (b not in pairs or pairs[b] == a)


def validate_accounts(conn, members):
    for uid in members:
        u = db.fetch_one(conn, 'User', id=uid)
        a = db.fetch_one(conn, 'Account', user_id=uid)
        if not u or u['bgv_status'] != 'verified' or u['journey_state'] != 'dating':
            raise ValueError(f'{uid}: requires verified Dating profile')
        if not a or not a['auth_enabled'] or not auth_sessions.tester_allowed(uid):
            raise ValueError(f'{uid}: requires enabled, allowlisted OTP-free tester account')


def assign(conn, a, week):
    """Called inside week_service.transition; preserves all recorded decisions."""
    b = configured().get(a)
    if not b:
        raise ValueError(f'{a}: pair is not configured')
    validate_accounts(conn, (a, b))
    active = [p for p in db.fetch_all(conn, 'LockIn', status='active')
              if a in (p['user_a'], p['user_b']) or b in (p['user_a'], p['user_b'])]
    if active:
        if len(active) == 1 and {active[0]['user_a'], active[0]['user_b']} == {a, b}:
            return 'PRESERVED active pair'
        raise ValueError('Active pairing with another user; preserved')
    for uid in (a, b):
        intro = db.fetch_one(conn, 'RehearsalIntro', id=uid)
        if intro and intro['week'] != week:
            raise ValueError(f'{uid}: intro belongs to another week; preserved')
    rows = db.fetch_all(conn, 'Match', week=week)
    owned = [r for r in rows if r['user_id'] in (a, b)]
    expected = {(a, b), (b, a)}
    if (len(owned) == 2 and {(r['user_id'], r['candidate_id']) for r in owned} == expected
            and all(r['id'].startswith('fixed:') for r in owned)):
        return 'ALREADY assigned (decisions preserved)'
    involved = [r for r in rows if r['user_id'] in (a, b) or r['candidate_id'] in (a, b)]
    if any(r['action'] != 'none' for r in involved):
        raise ValueError('Recorded decision involving this pair; preserved, no reassignment')
    if any({p['user_a'], p['user_b']} == {a, b} and p['week'] == week
           for p in db.fetch_all(conn, 'LockIn')):
        raise ValueError('This pair already completed a cycle this week; preserved')
    sql = auth_sessions.sql
    for r in involved:
        sql(conn, 'DELETE FROM "Match" WHERE id = ?', (r['id'],))
    for owner, partner in ((a, b), (b, a)):
        sql(conn, '''INSERT INTO "Match"
            (id,user_id,candidate_id,week,slot,revealed_at,window_closes_at)
            VALUES (?,?,?,?,1,'Mon:12','Tue:12')''',
            (f'fixed:{owner}:{week}:1', owner, partner, week))
        if not db.fetch_one(conn, 'MatchBatch', user_id=owner, week=week):
            sql(conn, '''INSERT INTO "MatchBatch" (id,user_id,week,generated_at)
                VALUES (?,?,?,'Mon:10')''', (f'{owner}:{week}', owner, week))
    return f'ASSIGNED one reciprocal candidate; replaced {len(involved)} unacted candidate rows'
