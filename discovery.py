"""Opt-in daily discovery. Views and likes never reserve a person.

Two confirmations allocate an exclusive existing LockIn, under the same
database lock used by legacy matching. Default off until the combined mobile
release and founder city-readiness review are complete.
"""
import os
import time
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo
import db
import auth_sessions
import launch_cities
import matching
import match_checks
import onboarding
import week_service
from api_contract import ApiError
from generate_users import from_user_row

QUOTA = 2
INTEREST_SECONDS = 7 * 86400
PROPOSAL_SECONDS = 86400


def enabled():
    return os.getenv('DHASHU_DAILY_DISCOVERY', '0') == '1'


def cycle_for(clock):
    # Wednesday onward: keep discovery open, plan for the following weekend.
    return clock.week + (1 if clock.day_index >= 2 else 0)


def day():
    return datetime.fromtimestamp(time.time(), ZoneInfo('Asia/Kolkata')).date().isoformat()


def event(conn, uid, candidate, action):
    db.insert_row(conn, 'DiscoveryEvent', dict(id=uuid.uuid4().hex, user_id=uid,
        candidate_id=candidate, action=action, created_at=int(time.time())))


def market(conn, city):
    entry = launch_cities.find(city)
    if not entry:
        return dict(discovery=0, ready=False, paused=1)
    result = db.fetch_one(conn, 'DiscoveryMarket', id=entry['code'])
    if not result:
        result = dict(id=entry['code'], discovery=int(entry['enabled']), verification=0,
            payments=0, restaurants=0, support=0, paused=0)
    return {**result, 'ready': bool(result['discovery'] and not result['paused'] and
        all(result[k] for k in ('verification', 'payments', 'restaurants', 'support')))}


def configure_market(conn, code, values):
    fields = {'discovery', 'verification', 'payments', 'restaurants', 'support', 'paused'}
    if code not in {c['code'] for c in launch_cities.CITIES} or type(values) is not dict or set(values)!=fields or any(type(v) is not bool for v in values.values()):
        raise ApiError('validation_error', 'Choose a known city and all readiness switches.')
    with week_service.transition(conn, serialize='discovery-market:'+str(code)):   # admin only
        db.insert_row(conn, 'DiscoveryMarket', dict(id=code, **{k:int(v) for k,v in values.items()}, updated_at=int(time.time())))


def member(conn, uid):
    row = db.fetch_one(conn, 'User', id=uid)
    if not row:
        raise ApiError('not_found', 'Profile not found.', 404)
    result=match_checks.attach(conn, [from_user_row(row)])[0]
    result['skills']=db.load_json_field(row['skills_json'],{})
    return result


def complete(user):
    stats = user.get('stats', {})
    if user['journey_state'] not in ('onboarding', 'dating'):
        return False
    return bool(user.get('gender') and user.get('city') and stats.get('age') and user.get('visions') and
        (stats.get('signup_version') != 3 or (stats.get('signup_stats_saved') and
         len(user.get('skills', {}).get('activities', {})) >= onboarding.MIN_SORTED)))


def decision(conn, uid, candidate):
    return db.fetch_one(conn, 'DiscoveryDecision', user_id=uid, candidate_id=candidate)


def unavailable(conn, uid, cycle):
    return bool(week_service.active_for(conn, uid) or db.fetch_one(conn, 'DiscoveryAllocation', user_id=uid, cycle=cycle))


def excluded(conn, a, b):
    for x, y in ((a,b),(b,a)):
        if db.fetch_one(conn, 'DiscoveryBlock', user_id=x, candidate_id=y):
            return True
        pick = decision(conn, x, y)
        if pick and pick['action'] in ('pass', 'block'):
            return True
        # Adopt legacy pre-date passes as exclusions; only explicit reset can
        # reopen them. Prior date-cycle pairings remain separate and protected.
        legacy = db.fetch_all(conn, 'Match', user_id=x, candidate_id=y, action='pass')
        if legacy and not (pick and pick['action'] == 'reset'):
            return True
    return any({r['user_a'],r['user_b']} == {a,b} for r in db.fetch_all(conn, 'LockIn'))


def compatible(conn, a, b, cycle):
    if a['user_id']==b['user_id'] or not complete(a) or not complete(b):
        return False
    import account_deletion   # feat-delete: never offered once deletion is requested
    if b['user_id'] in account_deletion.hidden_ids(conn):
        return False
    if not market(conn,a['city'])['discovery'] or not market(conn,b['city'])['discovery']:
        return False
    if a['bgv_status']=='verified' and b['bgv_status']!='verified':
        return False
    if unavailable(conn,b['user_id'],cycle) or excluded(conn,a['user_id'],b['user_id']):
        return False
    return matching.mutual_open(a,b)


def require_date_ready(conn, a, b, cycle):
    if not compatible(conn,a,b,cycle) or not compatible(conn,b,a,cycle) or unavailable(conn,a['user_id'],cycle):
        raise ApiError('pair_unavailable', 'This pairing is no longer available. Explore other profiles.', 409)
    import signup_verification, verification_payment
    for user in (a,b):
        if user['bgv_status']!='verified' or user['journey_state']!='dating':
            raise ApiError('verification_required', 'Both profiles must complete verification before a date.', 409)
        if not market(conn,user['city'])['ready']:
            raise ApiError('city_not_ready', 'Discovery is open. Dates will open when local services are ready.', 409)
        if not signup_verification.matching_satisfied(db.fetch_one(conn,'Account',user_id=user['user_id'])):
            raise ApiError('verification_required', 'Contact verification is required.', 409)
        if user['stats'].get('signup_version')==3 and not verification_payment.view(conn,user['user_id'])['can_begin']:
            raise ApiError('payment_required', 'Complete registration and verification before confirming.', 409)


def preview(user):
    # Deliberately no name, photo, phone, exact DOB or BGV evidence here.
    return dict(id=user['user_id'], age=user['stats'].get('age'), city=user.get('city'),
        verification='Verified' if user['bgv_status']=='verified' else 'Unverified',
        pillars=[v['key'] for v in user.get('visions',[])])


def snapshot(conn, uid, cycle):
    user = member(conn,uid)
    status = market(conn,user.get('city'))
    profiles = []
    if complete(user) and status['discovery'] and not unavailable(conn,uid,cycle):
        for row in db.fetch_all(conn,'DiscoveryExposure',user_id=uid,day=day()):
            other=member(conn,row['candidate_id'])
            if compatible(conn,user,other,cycle):
                pick=decision(conn,uid,other['user_id'])
                profiles.append({**preview(other),'action':pick['action'] if pick else 'none'})
    proposals=[]
    for row in db.fetch_all(conn,'DiscoveryProposal',state='proposed'):
        if uid in (row['user_a'],row['user_b']) and row['cycle']==cycle and row['expires_at']>time.time():
            other=row['user_b'] if uid==row['user_a'] else row['user_a']
            if compatible(conn,user,member(conn,other),cycle):
                proposals.append(dict(id=row['id'],profile=preview(member(conn,other)),expires_at=row['expires_at'],
                    confirmed=bool(row['confirm_a'] if uid==row['user_a'] else row['confirm_b'])))
    code='signup_incomplete' if not complete(user) else 'city_waitlist' if not status['discovery'] else 'allocated' if unavailable(conn,uid,cycle) else 'city_not_ready' if not status['ready'] else 'verification_pending' if user['bgv_status']!='verified' else 'ready'
    messages={'signup_incomplete':'Complete Vision, age, gender, city and Chemistry to explore.',
        'city_waitlist':'Your city is on the waitlist. We will open discovery when it is ready.',
        'allocated':'You already have a date-cycle allocation. Continue with your date preferences and availability.',
        'city_not_ready':'Explore now. Local verification, payments, restaurant and support readiness must be confirmed before dates open.',
        'verification_pending':'You can explore verified and unverified profiles. Complete verification to express interest and arrange dates.',
        'ready':'Up to two profiles each day. Only mutual interest followed by both confirmations creates a pairing.'}
    passed=sorted({r['candidate_id'] for r in db.fetch_all(conn,'DiscoveryDecision',user_id=uid,action='pass')})
    return dict(mode='discovery', passed=passed, profiles=profiles, proposals=proposals, status=code,message=messages[code],
        empty_message='No mutual match this time. We will check again when new compatible people become available.',
        cycle=cycle,quota=QUOTA,reset_timezone='Asia/Kolkata',date_ready=status['ready'] and user['bgv_status']=='verified',
        prepare_request={'path':'/api/v1/discovery/prepare','body':{}} if code not in ('signup_incomplete','city_waitlist','allocated') else None)


def prepare(conn, uid, cycle):
    with week_service.transition(conn, uid, serialize=f'discovery-generation:{cycle}'):   # perf-rowlock: allocation, once per member per cycle
        user=member(conn,uid)
        if not complete(user) or not market(conn,user.get('city'))['discovery'] or unavailable(conn,uid,cycle):
            return snapshot(conn,uid,cycle)
        seen=db.fetch_all(conn,'DiscoveryExposure',user_id=uid)
        today=[r for r in seen if r['day']==day()]
        candidates=[]
        all_exposures=db.fetch_all(conn,'DiscoveryExposure')
        pending=db.fetch_all(conn,'DiscoveryDecision',action='interest')
        for row in db.fetch_all(conn,'User'):
            if any(r['candidate_id']==row['id'] for r in today):
                continue
            other=member(conn,row['id'])
            prior=[r for r in seen if r['candidate_id']==row['id']]
            pick=decision(conn,uid,row['id'])
            if prior and not (pick and pick['action']=='reset' and pick['updated_at']>=max(r['created_at'] for r in prior)):
                continue
            if compatible(conn,user,other,cycle):
                count=sum(r['candidate_id']==row['id'] for r in all_exposures)
                account=db.fetch_one(conn,'Account',user_id=row['id']) or {}
                unanswered=sum(d['candidate_id']==row['id'] and d['updated_at']>time.time()-INTEREST_SECONDS and not decision(conn,row['id'],d['user_id']) for d in pending)
                candidates.append((count+unanswered,str(account.get('created_at') or ''),row['id']))
        for _,_,candidate in sorted(candidates)[:max(0,QUOTA-len(today))]:
            db.insert_row(conn,'DiscoveryExposure',dict(id=uuid.uuid4().hex,user_id=uid,candidate_id=candidate,day=day(),created_at=int(time.time())))
            event(conn,uid,candidate,'shown')
        return snapshot(conn,uid,cycle)


def act(conn, uid, candidate, action, cycle):
    if action not in ('interest','pass','reset','block') or not isinstance(candidate,str):
        raise ApiError('validation_error','Choose interest, pass, reset or block.')
    with week_service.transition(conn, uid, candidate):   # perf-rowlock: these two members only
        user=member(conn,uid);other=member(conn,candidate)
        old=decision(conn,uid,candidate)
        if action=='reset':
            legacy=db.fetch_all(conn,'Match',user_id=uid,candidate_id=candidate,action='pass')
            if not (old and old['action']=='pass' or legacy):
                raise ApiError('state_conflict','Only your own pre-date passes can be reconsidered.',409)
            if db.fetch_one(conn,'DiscoveryBlock',user_id=uid,candidate_id=candidate):
                raise ApiError('state_conflict','Blocked profiles cannot be reconsidered here.',409)
        elif not db.fetch_all(conn,'DiscoveryExposure',user_id=uid,candidate_id=candidate):
            raise ApiError('not_found','Profile not shown to you.',404)
        elif action=='interest':
            require_date_ready(conn,user,other,cycle)
        if action=='block':
            db.insert_row(conn,'DiscoveryBlock',dict(id=f'{uid}:{candidate}',user_id=uid,candidate_id=candidate))
        db.insert_row(conn,'DiscoveryDecision',dict(id=f'{uid}:{candidate}',user_id=uid,candidate_id=candidate,action=action,updated_at=int(time.time())))
        event(conn,uid,candidate,action)
        if action in ('pass','block','reset'):
            for row in db.fetch_all(conn,'DiscoveryProposal',state='proposed'):
                if {row['user_a'],row['user_b']}=={uid,candidate}:
                    row['state']='declined';db.insert_row(conn,'DiscoveryProposal',row)
        reciprocal=decision(conn,candidate,uid)
        if action=='interest' and reciprocal and reciprocal['action']=='interest' and reciprocal['updated_at']>time.time()-INTEREST_SECONDS:
            prior=[r for r in db.fetch_all(conn,'DiscoveryProposal',state='proposed') if {r['user_a'],r['user_b']}=={uid,candidate} and r['cycle']==cycle and r['expires_at']>time.time()]
            if not prior:
                a,b=sorted((uid,candidate))
                db.insert_row(conn,'DiscoveryProposal',dict(id=uuid.uuid4().hex,user_a=a,user_b=b,cycle=cycle,state='proposed',expires_at=int(time.time())+PROPOSAL_SECONDS,created_at=int(time.time())))
                event(conn,uid,candidate,'proposed')
        return snapshot(conn,uid,cycle)


def confirm(conn, uid, proposal_id, clock):
    # perf-rowlock: lock the actor and both members of this proposal. Competing
    # proposals that share a member queue on that member's row.
    peek=db.fetch_one(conn,'DiscoveryProposal',id=proposal_id) if isinstance(proposal_id,str) else None
    with week_service.transition(conn, uid, *((peek['user_a'],peek['user_b']) if peek else ())):
        row=db.fetch_one(conn,'DiscoveryProposal',id=proposal_id)
        if not row or uid not in (row['user_a'],row['user_b']):
            raise ApiError('not_found','Pairing not found.',404)
        if row['state']=='confirmed':
            return {'confirmed':True}
        if row['state']!='proposed' or row['expires_at']<=time.time() or row['cycle']!=cycle_for(clock):
            raise ApiError('proposal_expired','This proposal has ended. Explore available profiles.',409)
        a,b=member(conn,row['user_a']),member(conn,row['user_b'])
        require_date_ready(conn,a,b,cycle_for(clock))
        for x,y in ((a,b),(b,a)):
            pick=decision(conn,x['user_id'],y['user_id'])
            if not pick or pick['action']!='interest' or pick['updated_at']<=time.time()-INTEREST_SECONDS:
                raise ApiError('pair_unavailable','This pairing is no longer available.',409)
        row['confirm_a' if uid==row['user_a'] else 'confirm_b']=1
        if row['confirm_a'] and row['confirm_b']:
            for person in (row['user_a'],row['user_b']):
                db.insert_row(conn,'DiscoveryAllocation',dict(id=f'{person}:{row["cycle"]}',user_id=person,cycle=row['cycle'],proposal_id=row['id']))
            import lockin
            pair=lockin.on_mutual_interest(row['user_a'],row['user_b'],row['cycle'],clock)
            db.insert_row(conn,'LockIn',dict(id='discovery:'+row['id'],**pair))
            row['state']='confirmed'
            event(conn,uid,row['user_b'] if uid==row['user_a'] else row['user_a'],'confirmed')
        db.insert_row(conn,'DiscoveryProposal',row)
        return {'confirmed':row['state']=='confirmed'}


def register(api, get_db, get_clock):
    from flask import g,jsonify
    from api_contract import json_object
    def ready():
        if not enabled():raise ApiError('not_available','Daily discovery is not enabled.',404)
        return g.api_user['user_id']
    @api.get('/discovery')
    def read_discovery():
        return jsonify(snapshot(get_db(),ready(),cycle_for(get_clock())))
    @api.post('/discovery/prepare')
    def prepare_discovery():
        json_object()
        return jsonify(prepare(get_db(),ready(),cycle_for(get_clock())))
    @api.post('/discovery/decision')
    def decide_discovery():
        body=json_object(required={'candidate_id','action'})
        return jsonify(act(get_db(),ready(),body['candidate_id'],body['action'],cycle_for(get_clock())))
    @api.post('/discovery/confirm')
    def confirm_discovery():
        body=json_object(required={'proposal_id'})
        if not isinstance(body['proposal_id'],str):raise ApiError('validation_error','Choose a pairing.')
        return jsonify(confirm(get_db(),ready(),body['proposal_id'],get_clock()))
