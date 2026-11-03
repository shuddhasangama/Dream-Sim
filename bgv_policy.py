"""Versioned market policy snapshots. No provider calls or account approvals."""
import json
import os
import uuid
from datetime import datetime, timezone
import auth_sessions
import db
from api_contract import ApiError

POLICY_ID='IN-BLR-phase1-v2'
CHECKS=[
    {'key':'identity_details','label':'DigiLocker identity details','phase':'1a','operations':['digilocker_create_url','digilocker_eaadhaar'],'cost':7},
    {'key':'current_employer','label':'Current employer','phase':'1a','operations':['current_employer'],'cost':4},
    {'key':'liveness','label':'Liveness Secure / Face Smart','phase':'1a','operations':['smart_verification'],'cost':6,'blocked_reason':'Vendor upload/capture contract and reference-image source required'},
    {'key':'criminal_court','label':'Criminal court screening','phase':'1b','operations':['individual_search','individual_result'],'cost':80},
    {'key':'fir','label':'FIR screening','phase':'1b','operations':['fir_search','fir_result'],'cost':50},
]

def stamp(): return datetime.now(timezone.utc).isoformat()

def seed(conn):
    """Explicit operator setup; never silently change an existing version."""
    policy={'id':POLICY_ID,'checks':CHECKS,'total':147,'currency':None,
            'approval_gate':'not_configured','country':'IN','city':'BLR'}
    raw=json.dumps(policy,sort_keys=True,separators=(',',':'))
    with auth_sessions.transaction(conn):
        existing=db.fetch_one(conn,'BgvPolicy',id=POLICY_ID)
        if existing and existing['definition_json'] != raw:
            raise ValueError('Published policy differs. Create a new version; do not overwrite it.')
        if not existing:
            auth_sessions.sql(conn,'INSERT INTO "BgvPolicy" (id,definition_json,created_at) VALUES (?,?,?)',(POLICY_ID,raw,stamp()))
        # Exact launch market only; there is no assumed global/country fallback.
        auth_sessions.sql(conn,'INSERT INTO "BgvMarketPolicy" (country_code,city_code,policy_id) VALUES (?,?,?) ON CONFLICT (country_code,city_code) DO NOTHING',('IN','BLR',POLICY_ID))
        for check in CHECKS:
            auth_sessions.sql(conn,'INSERT INTO "BgvProviderCoverage" (id,provider,check_key,country_code,city_code,environment,state) VALUES (?,?,?,?,?,?,?) ON CONFLICT (id) DO NOTHING',
                ('signzy-IN-BLR-'+check['key'],'signzy',check['key'],'IN','BLR','preproduction','contract_missing' if check['key']=='liveness' else 'pilot'))
    return policy

def assign(conn,uid,country,city,reason):
    if not isinstance(reason,str) or not reason.strip() or len(reason)>500:
        raise ValueError('An operator assignment reason is required')
    with auth_sessions.transaction(conn):
        if db._is_postgres_connection(conn):
            auth_sessions.sql(conn,'LOCK TABLE "BgvCase" IN SHARE ROW EXCLUSIVE MODE')
        user=db.fetch_one(conn,'User',id=uid)
        if not user: raise ValueError('Unknown account')
        if user.get('active_bgv_case_id'): raise ValueError('Account already has an active case; explicit reassessment is required')
        route=db.fetch_one(conn,'BgvMarketPolicy',country_code=country,city_code=city)
        if not route: raise ValueError('No policy configured for this exact market')
        policy=db.fetch_one(conn,'BgvPolicy',id=route['policy_id'])
        if not policy: raise ValueError('Policy definition missing')
        definition=json.loads(policy['definition_json'])
        cid=str(uuid.uuid4())
        auth_sessions.sql(conn,'INSERT INTO "BgvCase" (id,user_id,policy_id,country_code,city_code,environment,definition_json,assignment_reason,created_at) VALUES (?,?,?,?,?,?,?,?,?)',
            (cid,uid,policy['id'],country,city,'preproduction',policy['definition_json'],reason.strip(),stamp()))
        for check in definition['checks']:
            auth_sessions.sql(conn,'INSERT INTO "BgvCaseCheck" (id,case_id,check_definition_id,provider) VALUES (?,?,?,?)',
                (str(uuid.uuid4()),cid,check['key'],'signzy'))
        auth_sessions.sql(conn,'UPDATE "User" SET active_bgv_case_id=? WHERE id=?',(cid,uid))
    return cid

def check_for(conn,uid,key,environment):
    if os.getenv('DHASHU_BGV_POLICY_ENABLED') != '1': return None
    user=db.fetch_one(conn,'User',id=uid)
    case=db.fetch_one(conn,'BgvCase',id=user.get('active_bgv_case_id')) if user and user.get('active_bgv_case_id') else None
    if not case or case['user_id'] != uid or case['environment'] != environment:
        raise ApiError('bgv_plan_required','Support must assign your market verification plan before testing.',409)
    selected=next((c for c in json.loads(case['definition_json'])['checks'] if c['key']==key),None)
    coverage=db.fetch_one(conn,'BgvProviderCoverage',provider='signzy',check_key=key,country_code=case['country_code'],city_code=case['city_code'],environment=environment)
    if not selected or selected.get('blocked_reason') or not coverage or coverage['state'] != 'pilot':
        raise ApiError('check_unavailable','This check has no enabled provider for your market.',503)
    row=db.fetch_one(conn,'BgvCaseCheck',case_id=case['id'],check_definition_id=key)
    if not row or row['provider']!='signzy': raise ApiError('check_unavailable','This check has no connected provider in your assigned plan.',409)
    return row['id']

def view(conn,uid):
    user=db.fetch_one(conn,'User',id=uid)
    case=db.fetch_one(conn,'BgvCase',id=user.get('active_bgv_case_id')) if user and user.get('active_bgv_case_id') else None
    if not case or case['user_id'] != uid:
        return {'assigned':False,'policy_enforced':os.getenv('DHASHU_BGV_POLICY_ENABLED')=='1'}
    definition=json.loads(case['definition_json'])
    checks=[]
    for item in definition['checks']:
        check=db.fetch_one(conn,'BgvCaseCheck',case_id=case['id'],check_definition_id=item['key'])
        requests=db.fetch_all(conn,'BgvRequest',user_id=uid,case_check_id=check['id']) if check else []
        sessions=db.fetch_all(conn,'DigiLockerSession',user_id=uid,case_check_id=check['id']) if check else []
        attempts=sorted(requests+sessions,key=lambda r:r['created_at'],reverse=True)
        latest=attempts[0] if attempts else None
        entry={'key':item['key'],'label':item['label'],'phase':item['phase'],
            'state':'blocked' if item.get('blocked_reason') else latest['state'] if latest else 'not_started',
            'message':item.get('blocked_reason'), 'provider':check['provider'] if check else None}
        reviews=sorted(db.fetch_all(conn,'BgvReview',case_check_id=check['id']),key=lambda r:r['created_at'],reverse=True) if check else []
        if reviews:
            review=reviews[0]
            attempts=sorted(db.fetch_all(conn,'BgvAttempt',request_id=latest['id']),key=lambda r:r['created_at'],reverse=True) if latest and 'operation' in latest else []
            current_source=attempts[0]['id'] if attempts else latest['id'] if latest else None
            if review['decision']=='waived' or review['source_id']==current_source:
                entry['review_decision']=review['decision']
                entry['state']='waived' if review['decision']=='waived' else 'reviewed_'+review['decision']
        checks.append(entry)
    return {'assigned':True,'case_id':case['id'],'policy_id':case['policy_id'],'country':case['country_code'],
            'city':case['city_code'],'environment':case['environment'],'checks':checks,
            'approval_gate':definition['approval_gate'],'overall_approval':False}

def review(conn,case_check_id,source_id,decision,reason,reviewer):
    """Private operator decision; never an overall approval or matching unlock."""
    if decision not in ('satisfied','needs_review','not_satisfied','waived') or not isinstance(reason,str) or not reason.strip() or len(reason)>2000 or not isinstance(reviewer,str) or not reviewer.strip() or len(reviewer)>120:
        raise ValueError('Decision, operator identity and a review reason are required')
    # Import lazily: the app imports policy for routing.
    from bgv_app import Protection
    protection=Protection()
    with auth_sessions.transaction(conn):
        check=db.fetch_one(conn,'BgvCaseCheck',id=case_check_id)
        if not check: raise ValueError('Unknown case check')
        case=db.fetch_one(conn,'BgvCase',id=check['case_id'])
        if decision=='waived':
            if source_id: raise ValueError('Waivers are exceptions, not evidence verification; omit source-id')
        else:
            attempt=db.fetch_one(conn,'BgvAttempt',id=source_id)
            source=db.fetch_one(conn,'BgvRequest',id=attempt['request_id']) if attempt else db.fetch_one(conn,'DigiLockerSession',id=source_id)
            if not source or source.get('case_check_id')!=case_check_id or source['user_id']!=case['user_id'] or source['environment']!=case['environment']:
                raise ValueError('Evidence does not belong to this account/case/environment')
            if source['state'] not in ('needs_review','verified','partially_verified','complete'):
                raise ValueError('Evidence is not ready for review')
            if source.get('operation') in ('individual_search','fir_search'):
                raise ValueError('Review the linked result, not the search acknowledgement')
        rid=str(uuid.uuid4())
        auth_sessions.sql(conn,'INSERT INTO "BgvReview" (id,case_check_id,source_id,decision,protected_note,created_at) VALUES (?,?,?,?,?,?)',
            (rid,case_check_id,source_id,decision,protection.seal({'reason':reason.strip(),'reviewer':reviewer.strip()}),stamp()))
    return {'review_id':rid,'decision':decision,'overall_approval':False}
