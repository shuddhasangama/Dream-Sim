"""Actor-private ROAD storage and explicitly shared availability."""
import re
from datetime import date,timedelta
import db
import relationship_service as relationship
from evolution_service import transaction,text
from api_contract import ApiError

DAYS=('Mon','Tue','Wed','Thu','Fri','Sat','Sun')


def road(conn,uid,cid):
    return db.fetch_one(conn,'RoadProfile',user_id=uid,couple_id=cid) or {'id':cid+':'+uid,'user_id':uid,'couple_id':cid,'routine_json':'[]','availability_json':'[]'}


def minutes(value):
    if not isinstance(value,str) or not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]',value):raise ApiError('validation_error','Times must use HH:MM (00:00–23:59).')
    h,m=map(int,value.split(':'));return h*60+m


def key(slot):return '|'.join(slot[k] for k in ('day','start','end'))


def availability(conn,uid,cid,monday,derive):
    row=road(conn,uid,cid)
    derived=derive(db.load_json_field(row['routine_json'],[]))
    # Recurring free time is narrowed by actual dated obligations for this week.
    entries=db.fetch_all(conn,'CalendarEntry',couple_id=cid,owner_id=uid)
    for day in DAYS:
        actual=(date.fromisoformat(monday)+timedelta(days=DAYS.index(day))).isoformat()
        if any(e['type'] in ('obligation','travel') and e['starts_at'][:10]<=actual<=e['ends_at'][:10] for e in entries):derived[day]=[]
    return derived


def live_shared(conn,uid,cid,monday,derive):
    live={key(s):s for slots in availability(conn,uid,cid,monday,derive).values() for s in slots}
    stored=db.load_json_field(road(conn,uid,cid)['availability_json'],[])
    return [live[key(s)] for s in stored if key(s) in live]


def block(conn,uid,cid,body,clock):
    category=body.get('category');days=body.get('days')
    if category not in ('work','fitness','free') or type(days) is not list or not days or any(not isinstance(d,str) or d not in DAYS for d in days) or len(set(days))!=len(days):raise ApiError('validation_error','Choose a category and unique valid days.')
    start,end=body.get('start'),body.get('end')
    if minutes(start)>=minutes(end):raise ApiError('validation_error','End must be after start; split overnight blocks.')
    label=text(body.get('label'),'label',200)
    with transaction(conn):
        relationship.couple(conn,uid,cid)
        normalized={'category':category,'days':days,'start':start,'end':end,'label':label}
        receipt,fresh=relationship.event(conn,uid,cid,'road','routine',normalized,clock,body.get('request_id'))
        if not fresh:return
        row=road(conn,uid,cid);blocks=db.load_json_field(row['routine_json'],[])
        if len(blocks)>=100:raise ApiError('routine_limit','At most 100 routine blocks.',409)
        row['routine_json']=db.json_field([*blocks,{'id':receipt['id'],**normalized}]);db.insert_row(conn,'RoadProfile',row)


def remove_block(conn,uid,cid,rid):
    with transaction(conn):
        relationship.couple(conn,uid,cid);row=road(conn,uid,cid)
        blocks=db.load_json_field(row['routine_json'],[])
        if not any(b['id']==rid for b in blocks):return
        row['routine_json']=db.json_field([b for b in blocks if b['id']!=rid]);db.insert_row(conn,'RoadProfile',row)


def obligation(conn,uid,cid,body,clock):
    kind=body.get('type');mode=body.get('travel_mode')
    if kind not in ('obligation','travel') or (kind=='travel' and mode not in ('solo','partner_solo','together')) or (kind=='obligation' and mode is not None):raise ApiError('validation_error','Choose a valid obligation and travel mode.')
    start,end=body.get('start_date'),body.get('end_date')
    try:
        valid=isinstance(start,str) and isinstance(end,str) and len(start)==10 and len(end)==10 and date.fromisoformat(start)<=date.fromisoformat(end)
    except ValueError:valid=False
    if not valid:raise ApiError('validation_error','Use ordered YYYY-MM-DD dates.')
    if type(body.get('shared')) is not bool:raise ApiError('validation_error','shared must be boolean.')
    title=text(body.get('title'),'title',200)
    with transaction(conn):
        relationship.couple(conn,uid,cid)
        data={'type':kind,'travel_mode':mode,'starts_at':start,'ends_at':end,'title':title,'shared':body['shared']}
        receipt,fresh=relationship.event(conn,uid,cid,'road','obligation',data,clock,body.get('request_id'))
        if fresh:db.insert_row(conn,'CalendarEntry',{'id':receipt['id'],'owner_id':uid,'couple_id':cid,**data})


def remove_obligation(conn,uid,cid,rid):
    with transaction(conn):
        relationship.couple(conn,uid,cid)
        row=db.fetch_one(conn,'CalendarEntry',id=rid)
        if not row:return
        if row['owner_id']!=uid or row['couple_id']!=cid:raise ApiError('not_found','Obligation not found.',404)
        db.delete_row(conn,'CalendarEntry',rid)


def share(conn,uid,cid,slots,monday,derive):
    if type(slots) is not list or any(type(s) is not dict or set(s)!={'day','start','end'} or any(not isinstance(v,str) for v in s.values()) for s in slots):raise ApiError('validation_error','slots must contain day/start/end objects.')
    with transaction(conn):
        relationship.couple(conn,uid,cid)
        live={key(s) for daily in availability(conn,uid,cid,monday,derive).values() for s in daily}
        if len({key(s) for s in slots})!=len(slots) or any(key(s) not in live for s in slots):raise ApiError('stale_availability','Share only unique currently available slots.',409)
        row=road(conn,uid,cid);row['availability_json']=db.json_field(slots);db.insert_row(conn,'RoadProfile',row)


def vision_set(conn,uid,cid,body,clock,options):
    with transaction(conn):
        relationship.couple(conn,uid,cid)
        row=db.fetch_one(conn,'User',id=uid);entries=db.load_json_field(row['vision_json'],[])
        selected=next((v for v in entries if v['key']==body.get('key')),None)
        keyname=body.get('key');stance=body.get('stance')
        if not isinstance(keyname,str) or keyname not in options or not selected:raise ApiError('validation_error','Choose an existing vision goal.')
        values=stance if type(stance) is list else [stance]
        if not values or any(not isinstance(v,str) or v not in options[keyname] for v in values) or len(set(values))!=len(values):raise ApiError('validation_error','Choose listed stance options.')
        if keyname!='Cohabitate' and type(stance) is not str:raise ApiError('validation_error','Use one stance for this goal.')
        if keyname=='Cohabitate' and type(stance) is not list:raise ApiError('validation_error','Use an array of stances.')
        prior=db.fetch_one(conn,'JourneyAction',id=uid+':'+text(body.get('request_id'),'request_id',80))
        if prior:
            recorded=db.load_json_field(prior['payload_json'],{})
            if prior['couple_id']==cid and prior['scope']=='road' and prior['kind']=='vision' and recorded.get('key')==keyname and recorded.get('stance')==stance:return
            raise ApiError('request_conflict','Request ID has already been used.',409)
        if selected.get('stance') and selected['stance']!=stance and body.get('disclosed_to_partner') is not True:raise ApiError('disclosure_required','Disclose changes to an existing stance.',409)
        receipt,fresh=relationship.event(conn,uid,cid,'road','vision',{'key':keyname,'stance':stance,'previous':selected.get('stance')},clock,body.get('request_id'))
        if not fresh:return
        selected['stance']=stance;row['vision_json']=db.json_field(entries);db.insert_row(conn,'User',row)
