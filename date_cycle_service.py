"""Atomic, date-scoped feedback and resolution. Reports are not findings."""
from datetime import datetime, timedelta
import json
import db
import guru_dating
import lockin
import outcomes
import payments
import stage_gate
import dateplan
import planning_service as planning
from api_contract import ApiError

sql = planning.sql
FLAGS = ('a_green_flags', 'a_red_flags', 'b_green_flags', 'b_red_flags')


def owned(conn, uid, pid):
    plan = db.fetch_one(conn, 'DatePlan', id=pid)
    pair = db.fetch_one(conn, 'LockIn', id=plan['lockin_id']) if plan else None
    if not pair or uid not in (pair['user_a'], pair['user_b']):
        raise ApiError('not_found', 'Date not found.', 404)
    return pair, plan


def timing(plan, clock, epoch):
    try:
        starts = datetime.fromisoformat(plan['datetime'])
        if starts.tzinfo is not None:
            raise ValueError('Expected the existing naive simulation timestamp')
    except (ValueError, TypeError):
        raise ApiError('invalid_date_time', 'The stored date time needs correction.', 409)
    now = datetime.combine(epoch, datetime.min.time()) + timedelta(weeks=clock.week-1, days=clock.day_index, hours=clock.hour)
    opens = starts.replace(hour=dateplan.debrief_opens_hour(plan['meal']), minute=0, second=0)
    return {'open': now >= opens, 'started': now >= starts, 'opens_at': opens.isoformat(),
            'closed': clock.week > (starts.date()-epoch).days//7+1,
            'notice_hours': (starts-now).total_seconds()/3600}


def receipt(conn, pid):
    return db.fetch_one(conn, 'DateResolution', dateplan_id=pid)


def submission(conn, uid, pid):
    row = db.fetch_one(conn, 'DateFeedback', dateplan_id=pid, user_id=uid)
    return db.load_json_field(row['payload_json'], {}) if row else {}


def save_submission(conn, uid, pid, payload):
    planning.save(conn, 'DateFeedback', {'id':pid+':'+uid, 'dateplan_id':pid,'user_id':uid,'payload_json':json.dumps(payload)})


def mutable(conn, uid, pair, plan, clock, epoch, *, feedback=True, allow_closed=False):
    actor = db.fetch_one(conn, 'User', id=uid)
    if not actor or actor['bgv_status'] != 'verified' or actor['journey_state'] != 'dating':
        raise ApiError('feedback_unavailable', 'A verified Dating profile is required.', 403)
    if receipt(conn, plan['id']) or pair['status'] != 'active' or plan['status'] != 'confirmed':
        raise ApiError('state_conflict', 'This date is not open for changes.', 409)
    legacy = db.fetch_one(conn, 'DateOutcome', dateplan_id=plan['id'])
    if legacy and legacy.get('a_decision') and legacy.get('b_decision'):
        raise ApiError('legacy_resolution_required', 'This historical date needs resolution review before further changes.', 409)
    times = timing(plan, clock, epoch)
    if feedback and not times['open']:
        raise ApiError('feedback_not_open', 'Feedback opens one hour after the date starts.', 409)
    if feedback and times['closed'] and not allow_closed:
        raise ApiError('feedback_window_closed','The feedback week has closed; reconcile this date.',409)
    return times


def outcome(conn, pid):
    row = db.fetch_one(conn, 'DateOutcome', dateplan_id=pid)
    result = dict(row) if row else {'id':'outcome:'+pid, **outcomes.record_outcome(pid, True, None, None)}
    for key in FLAGS:
        result[key] = db.load_json_field(result.pop(key+'_json', None), result.get(key, []))
    return result


def save_outcome(conn, result):
    row = dict(result)
    for key in FLAGS:
        row[key+'_json'] = json.dumps(row.pop(key, []))
    planning.save(conn, 'DateOutcome', row)


def finish(conn, pair, plan, kind, uid, clock, *, count=False):
    # Called only inside planning.transition; primary/unique keys also guard replay.
    planning.save(conn, 'DateResolution', {'id':plan['id'], 'dateplan_id':plan['id'],
        'kind':kind, 'actor_id':uid, 'created_at':str(clock)})
    if count:
        sql(conn, 'UPDATE "LockIn" SET dates_completed=dates_completed+1 WHERE id=?', (pair['id'],))
    status = 'cancelled' if kind in ('cancelled', 'no_show_reported') else 'completed'
    if kind == 'both_relationship':
        status = 'confirmed'  # The existing relationship gate still reads this date.
        if not db.fetch_one(conn, 'StageGate', pair_id=pair['id']):
            gate = stage_gate.open_gate(pair['id'], 'exclusivity_raised', str(clock))
            planning.save(conn, 'StageGate', {'id':'gate:'+pair['id'], **gate})
    sql(conn, 'UPDATE "DatePlan" SET status=? WHERE id=?', (status, plan['id']))
    if kind == 'keep_dating':
        sql(conn, 'DELETE FROM "Availability" WHERE lockin_id=?', (pair['id'],))
        sql(conn, 'UPDATE "LockIn" SET week=? WHERE id=?', (max(pair['week']+1, clock.week), pair['id']))
    elif kind in ('rejected', 'ghosted', 'cancelled', 'no_show_reported'):
        released = lockin.release(pair, kind)
        sql(conn, 'UPDATE "LockIn" SET status=?, release_reason=? WHERE id=?', (released['status'], released['release_reason'], pair['id']))


def flags(conn, uid, pid, body, clock, epoch):
    green, red = body.get('green_flags'), body.get('red_flags')
    for values, options, lower, upper in ((green,guru_dating.GREEN_FLAGS,2,2),(red,guru_dating.RED_FLAGS,0,2)):
        if not isinstance(values,list) or any(not isinstance(v,str) for v in values) or len(values)!=len(set(values)) or not lower<=len(values)<=upper or any(v not in options for v in values):
            raise ApiError('validation_error', 'Select two valid green flags and up to two distinct red flags.')
    if any(type(body.get(key,False)) is not bool for key in ('together_photo','bill_photo')):
        raise ApiError('validation_error', 'Photo consent values must be booleans.')
    captured = guru_dating.capture_flags(green,red)
    value = {'green_flags':captured['green'], 'red_flags':captured['red'],
        'together_photo':body.get('together_photo',False),'bill_photo':body.get('bill_photo',False)}
    with planning.transition(conn):
        pair, plan = owned(conn,uid,pid)
        mine = submission(conn,uid,pid)
        if mine.get('flags') == value:
            return
        mutable(conn,uid,pair,plan,clock,epoch)
        if mine.get('decision'):
            raise ApiError('state_conflict','Feedback is frozen after your decision.',409)
        mine['flags']=value
        save_submission(conn,uid,pid,mine)
        row = outcome(conn,pid)
        role = 'a' if pair['user_a']==uid else 'b'
        row[role+'_green_flags'], row[role+'_red_flags'] = captured['green'], captured['red']
        # Shared photo consent is true only after BOTH actors opt in, never OR.
        other = pair['user_b'] if role=='a' else pair['user_a']
        their = submission(conn,other,pid).get('flags',{})
        row['happened'] = bool(their.get('green_flags'))
        for key in ('together_photo','bill_photo'):
            row[key] = value[key] and their.get(key,False)
        save_outcome(conn,row)


def decide(conn,uid,pid,body,clock,epoch):
    choice, reason = body.get('decision'), body.get('reason')
    if choice not in ('continue','relationship','pass') or (reason is not None and (not isinstance(reason,str) or len(reason)>2000)):
        raise ApiError('validation_error','Invalid decision or reason.')
    if choice!='pass' and reason:
        raise ApiError('validation_error','A reason applies only to pass.')
    reason = guru_dating.capture_pass_reason(reason)['reason'] if choice=='pass' else None
    with planning.transition(conn):
        pair,plan=owned(conn,uid,pid)
        mine=submission(conn,uid,pid)
        if mine.get('decision')==choice and mine.get('reason')==reason:
            return
        mutable(conn,uid,pair,plan,clock,epoch)
        if mine.get('decision'):
            raise ApiError('state_conflict','Your decision has already been recorded.',409)
        row=outcome(conn,pid)
        role='a' if pair['user_a']==uid else 'b'
        if len(row.get(role+'_green_flags',[]))<guru_dating.MIN_GREEN_FLAGS:
            raise ApiError('flags_required','Submit flag feedback first.',409)
        mine.update(decision=choice,reason=reason)
        save_submission(conn,uid,pid,mine)
        row[role+'_decision'],row[role+'_reason']=choice,reason
        save_outcome(conn,row)
        result=outcomes.apply_resolution(row)
        kind='rejected' if choice=='pass' else result['resolution']
        if kind!='pending':
            count=all(row.get(k) in ('continue','relationship','pass') for k in ('a_decision','b_decision'))
            finish(conn,pair,plan,kind,uid,clock,count=count)


def cancel(conn,uid,pid,clock,epoch):
    with planning.transition(conn):
        pair,plan=owned(conn,uid,pid)
        done=receipt(conn,pid)
        if done and done['kind']=='cancelled' and done['actor_id']==uid:
            return
        times=mutable(conn,uid,pair,plan,clock,epoch,feedback=False)
        if times['started']:
            raise ApiError('state_conflict','The date has started; use the debrief/report flow.',409)
        terms=dateplan.cancellation(times['notice_hours'],payments.fee(payments.CANCELLATION)['amount_inr'])
        sql(conn,'UPDATE "DatePlan" SET cancel_fee=? WHERE id=?',(terms['fee_inr'],pid))
        if terms['late']:
            planning.save(conn,'ComplianceEvent',{'id':'cancel:'+pid,**outcomes.record_compliance_event(uid,'late_cancel',clock.week,value='late_cancel',notes=terms['reason'])})
            if payments.is_enabled():
                planning.save(conn,'DateCharge',{'id':pid,'dateplan_id':pid,'user_id':uid,
                    'amount_inr':terms['fee_inr'],'status':'pending','created_at':str(clock)})
        finish(conn,pair,plan,'cancelled',uid,clock)


def no_show(conn,uid,pid,clock,epoch):
    with planning.transition(conn):
        pair,plan=owned(conn,uid,pid)
        mine=submission(conn,uid,pid)
        if mine.get('no_show_reported'):
            return
        mutable(conn,uid,pair,plan,clock,epoch)
        if mine.get('flags'):
            raise ApiError('state_conflict','You already submitted feedback that the date happened.',409)
        mine['no_show_reported']=True
        save_submission(conn,uid,pid,mine)
        # Release as before, but no punitive strike or shared happened=False claim.
        finish(conn,pair,plan,'no_show_reported',uid,clock)


def reconcile(conn,uid,pid,clock,epoch):
    """Explicit idempotent timeout, never triggered by a new API GET."""
    with planning.transition(conn):
        pair,plan=owned(conn,uid,pid)
        if receipt(conn,pid):
            return
        mutable(conn,uid,pair,plan,clock,epoch,allow_closed=True)
        stamp=datetime.fromisoformat(plan['datetime']).date()
        date_week=(stamp-epoch).days//7+1
        if clock.week<=date_week:
            raise ApiError('feedback_window_open','The feedback week has not closed.',409)
        row=outcome(conn,pid)
        for role in ('a','b'):
            if row.get(role+'_decision') is None:
                row[role+'_decision']='ghosted'
        save_outcome(conn,row)
        finish(conn,pair,plan,outcomes.resolution(row),uid,clock)
