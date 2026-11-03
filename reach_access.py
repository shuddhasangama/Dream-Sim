"""Read-only REACH availability during a persisted matching/date cycle."""
import cadence
import clock as clock_module
import db
import async_rehearsal

LOCKED_STATES={'relationship','engaged','married'}
LOCK_REASON='REACH is paused while matches are being reviewed or a date/debrief is in progress. It reopens when no candidates remain or you return to the pool.'

def state(conn,user,clock):
    uid=user['user_id']
    if user['journey_state'] in LOCKED_STATES:
        return {'locked':True,'reason':'REACH is closed after Dating.'}
    pairs=[r for r in db.fetch_all(conn,'LockIn') if uid in (r['user_a'],r['user_b'])]
    if any(r['status']=='active' for r in pairs):
        return {'locked':True,'reason':LOCK_REASON}
    matches=db.fetch_all(conn,'Match',user_id=uid,week=clock.week)
    if not matches:
        return {'locked':False,'reason':None}
    first=min(clock_module.SimulationClock.parse(r['week'],r['revealed_at']) for r in matches)
    if clock<first:
        return {'locked':False,'reason':None}
    all_active=db.fetch_all(conn,'LockIn',status='active')
    unavailable={member for pair in all_active for member in (pair['user_a'],pair['user_b'])}
    for row in matches:
        reveal=clock_module.SimulationClock.parse(row['week'],row['revealed_at'])
        # Do not unlock between the first and subsequent daily reveals.
        if clock<reveal:
            return {'locked':True,'reason':LOCK_REASON}
        candidate=row['candidate_id']
        closed_pair=any(r['week']==row['week'] and candidate in (r['user_a'],r['user_b']) and r['status'] in ('released','completed') for r in pairs)
        if closed_pair or row['action']=='pass' or candidate in unavailable:
            continue
        person=db.fetch_one(conn,'User',id=candidate)
        if not person or person['bgv_status']!='verified' or person['journey_state']!='dating':
            continue
        their=db.fetch_one(conn,'Match',user_id=candidate,candidate_id=uid,week=row['week'])
        if their and their['action']=='pass':
            continue
        closes=clock_module.SimulationClock.parse(row['week'],row['window_closes_at'])
        status=cadence.match_status({'revealed_at':reveal,'window_closes_at':closes,'action':row['action']},clock)
        if status=='open' or (row['action']=='interest' and (clock<closes or async_rehearsal.enabled())):
            return {'locked':True,'reason':LOCK_REASON}
    return {'locked':False,'reason':None}
