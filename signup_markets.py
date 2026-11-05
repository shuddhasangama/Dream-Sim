"""Explicit sandbox coverage for the three selected launch cities, no user-ID allowlist."""
import json
import os
import auth_sessions
import bgv_policy
import db
import launch_cities
from api_contract import ApiError

def ensure(conn,uid):
    user=db.fetch_one(conn,'User',id=uid)
    if not user:raise ApiError('not_found','Account not found.',404)
    stats=json.loads(user['stats_json'] or '{}')
    city=launch_cities.find(stats.get('city'))
    if not city or not city['enabled']:raise ApiError('launch_city_required','Choose Bangalore, Delhi or Mumbai before verification.',409)
    if user.get('active_bgv_case_id'):return user['active_bgv_case_id']
    if os.getenv('SIGNZY_ENV','preproduction')!='preproduction':raise ApiError('market_unavailable','This signup rollout currently uses Signzy sandbox only.',409)
    code=city['code'];pid=f'IN-{code}-signup-v1'
    checks=[{**check,**({'label':'Liveness Secure','operations':['liveness_secure_create','liveness_secure_data']} if check['key']=='liveness' else {})} for check in bgv_policy.CHECKS]
    for check in checks:check.pop('blocked_reason',None)
    definition=json.dumps({'id':pid,'country':'IN','city':code,'checks':checks,'total':147,'currency':None,'approval_gate':'evidence_required'},sort_keys=True,separators=(',',':'))
    with auth_sessions.transaction(conn):
        if db._is_postgres_connection(conn):auth_sessions.sql(conn,'LOCK TABLE "BgvCase" IN SHARE ROW EXCLUSIVE MODE')
        fresh=db.fetch_one(conn,'User',id=uid)
        if fresh.get('active_bgv_case_id'):return fresh['active_bgv_case_id']
        existing=db.fetch_one(conn,'BgvPolicy',id=pid)
        if existing and existing['definition_json']!=definition:raise ApiError('policy_version_conflict','This market policy needs a new version.',409)
        auth_sessions.sql(conn,'INSERT INTO "BgvPolicy" (id,definition_json,created_at) VALUES (?,?,?) ON CONFLICT (id) DO NOTHING',(pid,definition,bgv_policy.stamp()))
        auth_sessions.sql(conn,'INSERT INTO "BgvMarketPolicy" (country_code,city_code,policy_id) VALUES (?,?,?) ON CONFLICT (country_code,city_code) DO NOTHING',('IN',code,pid))
        for check in checks:
            auth_sessions.sql(conn,'INSERT INTO "BgvProviderCoverage" (id,provider,check_key,country_code,city_code,environment,state) VALUES (?,?,?,?,?,?,?) ON CONFLICT (id) DO UPDATE SET state=excluded.state',('signzy-IN-'+code+'-'+check['key'],'signzy',check['key'],'IN',code,'preproduction','pilot'))
        import uuid
        cid=str(uuid.uuid4())
        auth_sessions.sql(conn,'INSERT INTO "BgvCase" (id,user_id,policy_id,country_code,city_code,environment,definition_json,assignment_reason,created_at) VALUES (?,?,?,?,?,?,?,?,?)',(cid,uid,pid,'IN',code,'preproduction',definition,'Account selected an enabled launch city during authenticated signup.',bgv_policy.stamp()))
        for check in checks:auth_sessions.sql(conn,'INSERT INTO "BgvCaseCheck" (id,case_id,check_definition_id,provider) VALUES (?,?,?,?)',(str(uuid.uuid4()),cid,check['key'],'signzy'))
        auth_sessions.sql(conn,'UPDATE "User" SET active_bgv_case_id=? WHERE id=?',(cid,uid))
    return cid
