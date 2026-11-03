"""Consent-bound, durable screening orchestration. GETs never invoke providers.

Deterministic request IDs and case-level suppression prevent repeated paid calls.
Only a worker schedules linked results; uncertain calls require operator review.
"""
import json
import os
import uuid
from datetime import datetime,timezone,timedelta
import auth_sessions
import db
import bgv_app
import bgv_policy
from api_contract import ApiError
from signzy.digilocker_details import documents
from digilocker_signup import BUNDLE_VERSION, BUNDLE_CONSENT

def automatic_rechecks():
    try:return max(0,min(5,int(os.getenv('DHASHU_BGV_AUTO_RESULT_RECHECKS','0'))))
    except ValueError:return 0

def latest(conn,uid,environment):
    rows=[r for r in db.fetch_all(conn,'DigiLockerSession',user_id=uid) if r['environment']==environment]
    return max(rows,key=lambda r:r['created_at']) if rows else None

def consent(conn,uid,body):
    cfg=bgv_app.config()
    if body.get('consent') is not True or body.get('consent_version')!=BUNDLE_VERSION:
        raise ApiError('validation_error','Confirm screening consent first.')
    employer=body.get('employer','')
    if not isinstance(employer,str) or len(employer)>200 or any(ord(c)<32 for c in employer):
        raise ApiError('validation_error','Check your declared employer.')
    bgv_policy.check_for(conn,uid,'identity_details',cfg.environment)
    with auth_sessions.transaction(conn):
        if db._is_postgres_connection(conn):
            auth_sessions.sql(conn,'LOCK TABLE "DigiLockerSession" IN SHARE ROW EXCLUSIVE MODE')
        row=latest(conn,uid,cfg.environment)
        if not row or row['id']!=body.get('session_id') or row['state']!='complete':
            raise ApiError('identity_required','Complete the current DigiLocker session first.',409)
        value=bgv_app.Protection().open(row['protected_result'])
        old=value.get('_bundle',{})
        # An employer declaration is immutable once any employer request exists.
        if old.get('employer')!=employer.strip() and db.fetch_all(conn,'BgvRequest',user_id=uid,operation='current_employer',environment=cfg.environment):
            raise ApiError('already_submitted','Your employer check is already submitted. Contact support to change its declaration.',409)
        value['_bundle']={'version':BUNDLE_VERSION,'accepted_at':old.get('accepted_at',bgv_app.stamp()),
                          'pan_scope':row['consent_version']==BUNDLE_VERSION,'employer':employer.strip()}
        auth_sessions.sql(conn,'UPDATE "DigiLockerSession" SET protected_result=? WHERE id=?',
                          (bgv_app.Protection().seal(value),row['id']))

def request_id(sid,operation):
    return str(uuid.uuid5(uuid.NAMESPACE_URL,'dhashu:bgv:'+sid+':'+operation))

def detail_data(request,protection):
    if not request or request['state'] not in ('needs_review','verified') or not request.get('protected_result'):return None
    evidence=protection.open(request['protected_result'])
    response=evidence.get('provider_response') or {}
    if response.get('http_status')!=200:return None
    try:return documents(response.get('json'))
    except ValueError:return None

def schedule(conn):
    cfg=bgv_app.config(); protection=bgv_app.Protection()
    from digilocker_photo_cache import purge_expired
    purge_expired(conn)
    sessions=sorted(db.fetch_all(conn,'DigiLockerSession'),key=lambda r:r['created_at'],reverse=True)
    seen=set()
    for row in sessions:
        uid=row['user_id']
        if row['environment']!=cfg.environment or uid in seen:continue
        seen.add(uid)
        if row['state']!='complete':continue
        identity=protection.open(row['protected_result']); bundle=identity.get('_bundle',{})
        if bundle.get('version')!=BUNDLE_VERSION:continue
        try:
            identity_check=bgv_policy.check_for(conn,uid,'identity_details',cfg.environment)
            if identity_check!=row.get('case_check_id'):continue
            from digilocker_photo_cache import cache
            cache(conn,row)
            for operation in ('individual_search','fir_search'):
                inputs={'name':identity['name'],'address':identity['document_address'],'matchType':'exact'}
                if operation=='individual_search':inputs['caseCategory']='criminal'
                queue(conn,row,bundle,operation,inputs,{})
            details_id=request_id(row['id'],'digilocker_details')
            if bundle.get('pan_scope'):
                with auth_sessions.transaction(conn):
                    if db._is_postgres_connection(conn):auth_sessions.sql(conn,'LOCK TABLE "BgvRequest" IN SHARE ROW EXCLUSIVE MODE')
                    if not db.fetch_one(conn,'BgvRequest',id=details_id):
                        linked=protection.open(row['protected_session'])
                        snapshot={'inputs':{'requestId':linked['requestId']},'declared':{},'bundle_session_id':row['id'],
                                  'consent':{'version':BUNDLE_VERSION,'text':BUNDLE_CONSENT,'user_id':uid,'accepted_at':bundle['accepted_at']}}
                        now=bgv_app.stamp()
                        auth_sessions.sql(conn,'INSERT INTO "BgvRequest" (id,user_id,operation,environment,state,protected_input,created_at,updated_at,case_check_id) VALUES (?,?,?,?,?,?,?,?,?)',
                            (details_id,uid,'digilocker_details',cfg.environment,'queued',protection.seal(snapshot),now,now,identity_check))
            details=detail_data(db.fetch_one(conn,'BgvRequest',id=details_id),protection)
            # The listing's account name must agree with the Aadhaar legal name.
            normalize=lambda value:' '.join((value or '').casefold().split())
            if details and details['pan'] and details['mobile'] and bundle.get('employer') and normalize(details['name'])==normalize(identity['name']):
                queue(conn,row,bundle,'current_employer',{'panNumber':details['pan'],'mobile':details['mobile']},{'employer':bundle['employer']})
        except ApiError:
            # Disabled plan / existing work is not permission to retry a paid call.
            continue
    # Automatic linked result lookups apply only to this explicitly consented workflow.
    for row in db.fetch_all(conn,'BgvRequest',environment=cfg.environment):
        snapshot=protection.open(row['protected_input'])
        if not snapshot.get('bundle_session_id'):continue
        if row['operation'] in bgv_app.RESULTS and snapshot['inputs'].get('matchType')!='exact':continue
        try:
            if row['operation'] in bgv_app.RESULTS and row['state']=='result_available' and not db.fetch_all(conn,'BgvRequest',parent_request_id=row['id']):
                bgv_app.fetch_result(conn,row['user_id'],row['id'],request_id(row['id'],'result'))
            elif row['operation'] in bgv_app.RESULTS.values() and row['state']=='pending' and row.get('poll_count',0)<automatic_rechecks() and datetime.now(timezone.utc)-datetime.fromisoformat(row['updated_at'])>=timedelta(seconds=60):
                bgv_app.check_again(conn,row['user_id'],row['id'])
        except ApiError:continue

def queue(conn,session,bundle,operation,inputs,declared):
    key={'individual_search':'criminal_court','fir_search':'fir','current_employer':'current_employer'}[operation]
    try:case_check=bgv_policy.check_for(conn,session['user_id'],key,session['environment'])
    except ApiError:return
    # No automatic reassessment, including after definitive failure or a new consent link.
    with auth_sessions.transaction(conn):
        if db._is_postgres_connection(conn):auth_sessions.sql(conn,'LOCK TABLE "BgvRequest" IN SHARE ROW EXCLUSIVE MODE')
        existing=db.fetch_all(conn,'BgvRequest',user_id=session['user_id'],operation=operation,environment=session['environment'])
        if any(r.get('case_check_id')==case_check and (operation=='current_employer' or bgv_app.Protection().open(r['protected_input'])['inputs'].get('matchType')=='exact') for r in existing):return
        values=bgv_app.OPERATIONS[operation].payload(inputs)
        now=bgv_app.stamp()
        snapshot={'inputs':values,'declared':declared,'bundle_session_id':session['id'],
                  'consent':{'version':BUNDLE_VERSION,'text':BUNDLE_CONSENT,'user_id':session['user_id'],'accepted_at':bundle['accepted_at']}}
        auth_sessions.sql(conn,'INSERT INTO "BgvRequest" (id,user_id,operation,environment,state,protected_input,created_at,updated_at,case_check_id) VALUES (?,?,?,?,?,?,?,?,?)',
            (request_id(session['id'],operation+(':exact-v1' if operation in bgv_app.RESULTS else '')),session['user_id'],operation,session['environment'],'queued',bgv_app.Protection().seal(snapshot),now,now,case_check))

def view(conn,uid):
    try:cfg=bgv_app.config()
    except ApiError:return {'enabled':False}
    row=latest(conn,uid,cfg.environment)
    result={'enabled':True,'consent_version':BUNDLE_VERSION,'consent_text':BUNDLE_CONSENT,'consented':False,'pan_state':'not_requested','employer_declared':False}
    user=db.fetch_one(conn,'User',id=uid)
    stats=json.loads(user.get('stats_json','{}')) if user else {}
    if type(stats.get('age')) is int:result['declared_age']=stats['age']
    if not row or row['state']!='complete':return result
    photo=bgv_app.Protection().open(row['protected_photo']) if row.get('protected_photo') else {}
    result['photo_sources']={'aadhaar_reference_available':bool(row.get('protected_photo')),'aadhaar_image_available':bool(photo.get('image_base64')),
                             'aadhaar_download_state':photo.get('download_state','not_started'),'pan_photo_available':False,
                             'pan_photo_state':'not_provided_by_get_details','avatar_state':'not_generated'}
    value=bgv_app.Protection().open(row['protected_result']); bundle=value.get('_bundle',{})
    result.update(session_id=row['id'],consented=bundle.get('version')==BUNDLE_VERSION,employer_declared=bool(bundle.get('employer')) or bool(db.fetch_all(conn,'BgvRequest',user_id=uid,operation='current_employer',environment=cfg.environment)))
    detail=db.fetch_one(conn,'BgvRequest',id=request_id(row['id'],'digilocker_details'),user_id=uid)
    data=detail_data(detail,bgv_app.Protection())
    if data:
        result['pan_state']=data['pan_state']; result['mobile_available']=bool(data['mobile'])
        result['identity_name_match']=' '.join((data['name'] or '').casefold().split())==' '.join(value['name'].casefold().split())
    elif detail:result['pan_state']='pending' if detail['state'] in ('queued','processing','pending') else 'unavailable'
    elif bundle.get('pan_scope'):result['pan_state']='pending'
    return result
