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
import bgv
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
        ver_rows = db.fetch_all(conn, 'Verification', user_id=uid)
        verified_fields = stats_edit.verified_field_set(ver_rows)
        changes, refused, errors, reopened = [], [], [], []
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
            if not stats_edit.editable(field,state,verified_now=field in verified_fields)['editable']:
                refused.append(field); continue
            changes.append((field,before,after))
            if field in verified_fields:
                reopened.append(field)
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
            # A field that WAS verified just moved under the person's own
            # hand — the badge is not honest any more until BGV looks at
            # the new value. Re-open it the same way stats_reverify()
            # already does (in_review, not pending) rather than inventing
            # a second re-check pathway.
            for field in reopened:
                key = stats_edit.bgv_field(field)
                existing = next((r for r in ver_rows if r['field']==key), None)
                db.insert_row(conn,'Verification',{
                    **(dict(existing) if existing else {'id': f'{uid}:{key}'}),
                    'user_id': uid, 'field': key, 'status': bgv.IN_REVIEW,
                    'note': 'Re-opened: value changed by user.', 'updated_at': str(clock),
                })
        return {'saved':[onboarding.STAT_LABELS.get(k,k) for k,_,_ in changes], 'refused':[onboarding.STAT_LABELS.get(k,k) for k in refused], 'errors':errors,
                'reopened':[onboarding.STAT_LABELS.get(k,k) for k in reopened]}


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


def _vision_replay_or_conflict(conn,table,rid,content):
    """Client-supplied opaque request ID makes append-only changes
    retry-safe. `content` is the row about to be inserted — an existing
    row at this id must match it exactly (an identical replay) or the
    request_id has been reused for something else, which is refused."""
    old=db.fetch_one(conn,table,id=rid)
    if old is None:
        return None
    if any(old.get(k)!=v for k,v in content.items()):
        raise ApiError('request_conflict','Request ID already used with different content.',409)
    return old


def add_vision_detail(conn,uid,body,clock):
    """round3-fixes-spec.md §7.2: "Add Detail" — a pillar or sub-selection
    not previously present. Writes the real vision_json (vision.add_detail()
    validates against the full four-pillar rule set) and a structured
    VisionEntry audit row in the same transaction.

    The request_id replay check runs BEFORE add_detail() — unlike the old
    free-text system, this one actually mutates vision_json, so a naive
    retry would see its own prior addition as already-present and be
    refused as redundant instead of replayed."""
    pillar=body.get('pillar')
    sub_selection=body.get('sub_selection')
    request_id=text(body.get('request_id'),'request_id',80)
    detail_text=sub_selection if sub_selection is not None else pillar
    rid=f'{uid}:{request_id}'
    with transaction(conn):
        old=_vision_replay_or_conflict(conn,'VisionEntry',rid,{'element_key':pillar,'detail_text':detail_text})
        if old is not None:
            return old
        row=db.fetch_one(conn,'User',id=uid)
        vision_json=db.load_json_field(row['vision_json'],[])
        result=vision.add_detail(vision_json,pillar,sub_selection)
        if not result['ok']:
            raise ApiError('validation_error',result['error'])
        row['vision_json']=json.dumps(result['vision_json'],ensure_ascii=False)
        db.insert_row(conn,'User',row)
        db.insert_row(conn,'VisionEntry',{'id':rid,'user_id':uid,'element_key':pillar,
            'detail_text':detail_text,'added_at':str(clock),'parent_id':None})
        return db.fetch_one(conn,'VisionEntry',id=rid)


def declare_vision_change(conn,uid,body,clock):
    """round3-fixes-spec.md §7.3: "Declare a Change" — add and/or remove
    sub-selections within an EXISTING pillar. Requires disclosure and an
    open RC window (vision.declare_change() enforces both), and the
    resulting full vision must still pass every §7.1 rule.

    The request_id replay check runs AFTER declare_change(), against the
    real from/to it computed — unlike add_detail(), re-applying the same
    add/remove twice is harmless (the second call is a no-op: the state
    it produces already matches), so there is no "already applied"
    rejection to race against."""
    pillar=body.get('pillar')
    add=body.get('add') or []
    remove=body.get('remove') or []
    request_id=text(body.get('request_id'),'request_id',80)
    rid=f'{uid}:{request_id}'
    with transaction(conn):
        row=db.fetch_one(conn,'User',id=uid)
        vision_json=db.load_json_field(row['vision_json'],[])
        result=vision.declare_change(vision_json,pillar,add,remove,
            disclosed_to_partner=body.get('disclosed_to_partner') is True,clock=clock)
        if not result['ok']:
            code='disclosure_required' if 'disclosed' in result['error'] else (
                'change_window_closed' if 'Reality Check' in result['error'] else 'validation_error')
            status=409 if code!='validation_error' else 400
            raise ApiError(code,result['error'],status)
        from_value=', '.join(result['from']) or '(none)'
        to_value=', '.join(result['to']) or '(none)'
        old=_vision_replay_or_conflict(conn,'VisionChange',rid,
            {'element_key':pillar,'from_value':from_value,'to_value':to_value})
        if old is not None:
            return old
        row['vision_json']=json.dumps(result['vision_json'],ensure_ascii=False)
        db.insert_row(conn,'User',row)
        db.insert_row(conn,'VisionChange',{'id':rid,'user_id':uid,'element_key':pillar,
            'from_value':from_value,'to_value':to_value,'declared_at':str(clock),
            'disclosed_to_partner':1,'guru_conversation_id':None})
        return db.fetch_one(conn,'VisionChange',id=rid)
