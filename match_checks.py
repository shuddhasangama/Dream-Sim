"""Consented, minimal match disclosures and pure REACH predicates.

No documents, provider IDs, legal records, employer names or provider calls.
Freshness always uses real UTC; the simulated dating clock is irrelevant.
"""
import json
import os
from datetime import datetime,timezone,timedelta
import auth_sessions
import db
from api_contract import ApiError
CATEGORIES=['Salaried','Self-employed','Freelancer','Business owner','Other']
DEFAULT={'categories':[],'include_undisclosed':True,'verified_only':False,'max_age_days':0}
LABELS={'court':'Criminal court','fir':'FIR','employment':'Employment'}
STATUSES={'verified':'Verified','current_confirmed':'Current confirmed','history_found':'History found','self_declared':'Self-declared','pending':'Processing','review_required':'Review required','unavailable':'Not confirmed','not_checked':'Not checked'}

def moment(value):
    try:
        dt=datetime.fromisoformat(value)
        return dt.astimezone(timezone.utc) if dt.tzinfo else None
    except (TypeError,ValueError):return None

def preferences(user):
    saved=user.get('preferences',{}).get('work_verification',{})
    return {**DEFAULT,**saved}

def validate(body):
    if not isinstance(body,dict) or set(body)!=set(DEFAULT):raise ApiError('validation_error','Provide employment categories, disclosure preference and verification/freshness choices.')
    cats=body['categories']
    if type(cats)is not list or any(type(c)is not str or c not in CATEGORIES for c in cats) or len(cats)!=len(set(cats)):raise ApiError('validation_error','Choose listed employment categories only.')
    if type(body['include_undisclosed'])is not bool or type(body['verified_only'])is not bool:raise ApiError('validation_error','Filter choices must be true or false.')
    if type(body['max_age_days'])is not int or body['max_age_days'] not in (0,90,180):raise ApiError('validation_error','Choose Any time, 90 days or 180 days.')
    if not body['verified_only'] and body['max_age_days']!=0:raise ApiError('validation_error','Enable verified checks before selecting freshness.')
    return {**body,'categories':[c for c in CATEGORIES if c in cats]}

def public(user):
    summary=user.get('_match_checks') or {'shared':False,'checks':[]}
    return {'shared':summary['shared'],'sandbox':summary.get('sandbox',False),
            'checks':[{k:r.get(k) for k in ('key','label','status','status_label','checked_on')} for r in summary.get('checks',[])]}

def attach(conn,users,now=None):
    now=now or datetime.now(timezone.utc)
    wanted={u['user_id'] for u in users if u.get('stats',{}).get('share_verification_summary')=='Yes'}
    summaries={uid:{'shared':True,'sandbox':os.getenv('SIGNZY_ENV','preproduction')=='preproduction','checks':[]} for uid in wanted}
    if wanted:
        marks=','.join('?' for _ in wanted);params=tuple(sorted(wanted))
        people={r['id']:dict(r) for r in auth_sessions.sql(conn,'SELECT id,active_bgv_case_id FROM "User" WHERE id IN ('+marks+')',params).fetchall()}
        active=tuple({r.get('active_bgv_case_id') for r in people.values() if r.get('active_bgv_case_id')})
        places=','.join('?' for _ in active)
        checks={r['id']:dict(r) for r in auth_sessions.sql(conn,'SELECT id,case_id,check_definition_id FROM "BgvCaseCheck" WHERE case_id IN ('+places+')',active).fetchall()} if active else {}
        cases={r['id']:dict(r) for r in auth_sessions.sql(conn,'SELECT id,user_id,environment FROM "BgvCase" WHERE id IN ('+places+')',active).fetchall()} if active else {}
        env=os.getenv('SIGNZY_ENV','preproduction')
        rows=[dict(r) for r in auth_sessions.sql(conn,'SELECT id,user_id,operation,state,environment,case_check_id,parent_request_id,summary_json,created_at,updated_at FROM "BgvRequest" WHERE user_id IN ('+marks+') AND environment=? ORDER BY created_at DESC',(*params,env)).fetchall()]
        reviews={}
        review_rows=auth_sessions.sql(conn,'SELECT case_check_id,source_id,decision,created_at FROM "BgvReview" WHERE case_check_id IN ('+','.join('?' for _ in checks)+') ORDER BY created_at DESC',tuple(checks)).fetchall() if checks else []
        for review in review_rows:reviews.setdefault(review['case_check_id'],dict(review))
        attempts={}
        if reviews and rows:
            refs=tuple(r['id'] for r in rows);placeholders=','.join('?' for _ in refs)
            for attempt in auth_sessions.sql(conn,'SELECT id,request_id FROM "BgvAttempt" WHERE request_id IN ('+placeholders+') ORDER BY created_at DESC',refs).fetchall():attempts.setdefault(attempt['request_id'],attempt['id'])
        by_user={uid:[] for uid in wanted}
        for row in rows:
            check=checks.get(row.get('case_check_id'),{})
            case=cases.get(check.get('case_id'),{})
            expected={'individual_search':'criminal_court','individual_result':'criminal_court','fir_search':'fir','fir_result':'fir','current_employer':'current_employer'}.get(row['operation'])
            if expected and check.get('check_definition_id')==expected and case.get('user_id')==row['user_id'] and case.get('environment')==env and check.get('case_id')==people.get(row['user_id'],{}).get('active_bgv_case_id'):by_user[row['user_id']].append(row)
        for uid in wanted:
            owned=by_user[uid]
            for key,op,parent_op in [('court','individual_result','individual_search'),('fir','fir_result','fir_search'),('employment','current_employer',None)]:
                row=next((r for r in owned if r['operation']==op),None)
                parent=next((r for r in owned if r['operation']==parent_op),None) if parent_op else None
                if parent and (not row or row.get('parent_request_id')!=parent['id']):row=parent
                status='self_declared' if key=='employment' else 'not_checked';stamp=None
                if row:
                    data=json.loads(row['summary_json']);state=row['state']
                    if state in ('queued','processing','pending','result_available'):status='pending'
                    elif key=='employment':
                        if state=='verified' and data.get('employment_record',{}).get('current_employment_confirmed') is True:status='current_confirmed'
                        elif state=='history_available':status='history_found'
                        else:status='self_declared'
                    elif state=='verified' and data.get('match_type')=='exact' and data.get('processing_complete') is True and type(data.get('candidate_count'))is int and data['candidate_count']==0:status='verified'
                    elif state=='needs_review' and data.get('match_type')=='exact':status='review_required'
                    else:status='unavailable'
                    review=reviews.get(row.get('case_check_id'),{})
                    if key!='employment' and review and review.get('source_id')==attempts.get(row['id']) and attempts.get(row['id']):
                        if review['decision']=='satisfied' and data.get('match_type')=='exact' and data.get('processing_complete') is True:status='verified'
                        elif review['decision'] in ('not_satisfied','needs_review'):status='review_required'
                    if status in ('verified','current_confirmed','history_found','review_required'):
                        stamp=moment(row['updated_at'])
                        if stamp and stamp>now:stamp=None
                        if not stamp:status='self_declared' if key=='employment' else 'not_checked'
                summaries[uid]['checks'].append({'key':key,'label':LABELS[key],'status':status,'status_label':STATUSES[status],
                    'checked_on':stamp.date().isoformat() if stamp else None,'checked_at':stamp.isoformat() if stamp else None})
    return [{**u,'_match_checks':summaries.get(u['user_id'],{'shared':False,'checks':[]})} for u in users]

def fits(owner,candidate,now=None):
    if owner.get('preferences',{}).get('work_verification_ignored'):return True
    pref=preferences(owner);category=candidate.get('stats',{}).get('employment_category')
    if pref['categories']:
        if category is None:
            if not pref['include_undisclosed']:return False
        elif category not in pref['categories']:return False
    if not pref['verified_only']:return True
    summary=candidate.get('_match_checks',{})
    if not summary.get('shared'):return False
    checks={r['key']:r for r in summary.get('checks',[])}
    now=now or datetime.now(timezone.utc)
    for key,status in [('court','verified'),('fir','verified'),('employment','current_confirmed')]:
        check=checks.get(key,{})
        if check.get('status')!=status:return False
        if pref['max_age_days']:
            stamp=moment(check.get('checked_at'))
            if not stamp or not timedelta(0)<=now-stamp<=timedelta(days=pref['max_age_days']):return False
    return True

def reach(user):
    return {'categories':CATEGORIES,'preferences':preferences(user),'ignored':user.get('preferences',{}).get('work_verification_ignored',False)}
