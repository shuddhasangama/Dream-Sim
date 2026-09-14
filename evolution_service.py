"""Profile evolution shared by web and JSON adapters, without provider calls."""
from contextlib import contextmanager
import json
import math
import uuid
import db
import auth_sessions
import stats_edit
import onboarding
import matching
import chemistry
import expectations
import vision
from api_contract import ApiError


@contextmanager
def transaction(conn):
    with auth_sessions.transaction(conn), db.defer_commits(conn):
        # User is also the first lock used by dating transitions. Serializing
        # the eligibility read with those writes closes the edit/lock-in race.
        if db._is_postgres_connection(conn):
            conn.execute('LOCK TABLE "User" IN SHARE ROW EXCLUSIVE MODE')
        yield


def text(value, field, maximum=4000):
    if not isinstance(value, str) or not value.strip() or len(value) > maximum:
        raise ApiError('validation_error', f'{field} must be nonempty text up to {maximum} characters.')
    return value.strip()


def hours(clock):
    return (clock.week-1)*168 + clock.day_index*24 + clock.hour


def save_stats(conn, uid, submitted, situation, clock, strict=False):
    with transaction(conn):
        row = db.fetch_one(conn, 'User', id=uid)
        state = situation()
        stored = db.load_json_field(row['stats_json'], {})
        stats = onboarding.normalise_stats(stored)
        changes, refused, errors = [], [], []
        if strict and (type(submitted) is not dict or not submitted or set(submitted)-set(stats_edit.ALL_FIELDS)):
            raise ApiError('validation_error', 'Provide known stats fields only.')
        for field in stats_edit.ALL_FIELDS:
            if field not in submitted:
                continue
            raw = submitted[field]
            if strict:
                if field in onboarding.MULTI_VALUE_STATS:
                    if raw is not None and (type(raw) is not list or any(not isinstance(v,str) for v in raw)):
                        raise ApiError('validation_error', field+' must be an array of strings or null.')
                elif field in onboarding.STAT_RANGES:
                    if raw is not None and (type(raw) not in (int,float) or not math.isfinite(raw) or int(raw)!=raw):
                        raise ApiError('validation_error', field+' must be a whole number or null.')
                elif raw is not None and not isinstance(raw,str):
                    raise ApiError('validation_error', field+' must be text or null.')
                if isinstance(raw,str) and len(raw)>500:
                    raise ApiError('validation_error', field+' is too long.')
                raw = str(raw) if type(raw) in (int,float) else raw
            got = stats_edit.coerce(field, raw, onboarding.STAT_RANGES, onboarding.MULTI_VALUE_LIMIT)
            if not got['ok']:
                errors.append(got['error']); continue
            before, after = stats.get(field), got['value']
            if ('' if before is None else str(before)) == ('' if after is None else str(after)):
                continue
            if not stats_edit.editable(field,state)['editable']:
                refused.append(field); continue
            changes.append((field,before,after))
            if after is None:
                stats.pop(field,None)
            else:
                stats[field]=after
        if strict and (errors or refused):
            raise ApiError('stats_held' if refused else 'validation_error', '; '.join(errors+(['Held fields: '+', '.join(refused)] if refused else [])),409 if refused else 400)
        if changes or stats != stored:
            row['stats_json']=json.dumps(stats,ensure_ascii=False)
            row['preferences_json']=json.dumps(matching.unlock_levers_for(db.load_json_field(row['preferences_json'],{}),stats),ensure_ascii=False)
            db.insert_row(conn,'User',row)
            if stats_edit.discloses_to_partner(state):
                for field,before,after in changes:
                    db.insert_row(conn,'StatChange',{'id':uuid.uuid4().hex,**stats_edit.change_record(uid,field,before,after,str(clock))})
        return {'saved':[onboarding.STAT_LABELS.get(k,k) for k,_,_ in changes], 'refused':[onboarding.STAT_LABELS.get(k,k) for k in refused], 'errors':errors}


def save_activities(conn,uid,activities):
    if type(activities) is not dict or set(activities)-set(onboarding.ACTIVITIES) or any(not isinstance(v,str) for v in activities.values()):
        raise ApiError('validation_error','Provide known activity names and bucket strings.')
    result=onboarding.validate_activities(activities)
    if not result['ok']:
        raise ApiError('validation_error',result['error'])
    with transaction(conn):
        row=db.fetch_one(conn,'User',id=uid)
        row['skills_json']=json.dumps(onboarding.build_skills(result['activities']),ensure_ascii=False)
        db.insert_row(conn,'User',row)


def save_entry(conn,uid,key,value,clock,guard):
    allowed=(*chemistry.MANDATORY_KEYS,*chemistry.INTIMACY_MANDATORY_KEYS)
    if not isinstance(key,str) or key not in allowed:
        raise ApiError('validation_error','Unknown chemistry key.')
    value=text(value,'value')
    options={'physical_boundary':chemistry.PHYSICAL_BOUNDARY_OPTIONS,'intimacy_pace':chemistry.INTIMACY_PACE_OPTIONS,'health_openness':chemistry.HEALTH_OPENNESS_OPTIONS}
    if key in options and value not in options[key]:
        raise ApiError('validation_error','Choose a listed option.')
    with transaction(conn):
        guard(key)
        old=db.fetch_one(conn,'ChemistryEntry',user_id=uid,key=key)
        if old and old['value']==value:
            return
        db.insert_row(conn,'ChemistryEntry',{'id':f'{uid}:{key}',**chemistry.set_entry(uid,key,value,str(clock),hours(clock))})


def add_vision(conn,uid,body,clock,change=False):
    key=body.get('element_key')
    if key not in vision.VISION_ELEMENT_KEYS:
        raise ApiError('validation_error','Unknown vision element.')
    with transaction(conn):
        if change:
            if body.get('disclosed_to_partner') is not True:
                raise ApiError('disclosure_required','A reversal must be disclosed to the partner.',409)
            row=vision.declare_vision_change(uid,key,text(body.get('from_value'),'from_value'),text(body.get('to_value'),'to_value'),str(clock),True)
            table='VisionChange'
        else:
            entries=db.fetch_all(conn,'VisionEntry',user_id=uid,element_key=key)
            row=vision.add_vision_detail(uid,key,text(body.get('detail_text'),'detail_text'),str(clock),entries[-1]['id'] if entries else None)
            table='VisionEntry'
        # Client-supplied opaque request ID makes append-only changes retry-safe.
        request_id=text(body.get('request_id'),'request_id',80)
        rid=f'{uid}:{request_id}'
        old=db.fetch_one(conn,table,id=rid)
        if old:
            compared=('element_key','from_value','to_value') if change else ('element_key','detail_text')
            if any(old[k]!=row[k] for k in compared):
                raise ApiError('request_conflict','Request ID already used with different content.',409)
            return old
        db.insert_row(conn,table,{'id':rid,**row})
        return db.fetch_one(conn,table,id=rid)
