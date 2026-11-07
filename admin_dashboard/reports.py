"""Bounded, allowlisted reporting queries. No raw evidence, Guru text or secrets."""
from contextlib import contextmanager
import json
import os
import time
import db
import auth_sessions

@contextmanager
def connection():
    dsn = os.getenv('ADMIN_REPORT_DATABASE_URL')
    if dsn:
        import psycopg
        from psycopg.rows import dict_row
        conn = psycopg.connect(dsn, row_factory=dict_row)
    else:
        conn = db.get_connection(os.getenv('ADMIN_LOCAL_DB_PATH', db.DEFAULT_DB_PATH))
    try:
        if db._is_postgres_connection(conn):
            conn.execute('SET TRANSACTION READ ONLY')
            conn.execute("SET LOCAL statement_timeout = '5s'")
        else:
            conn.execute('PRAGMA query_only=ON')
        yield conn
    finally:
        conn.rollback(); conn.close()

def rows(c, sql, args=()):
    return [dict(r) for r in auth_sessions.sql(c,sql,args).fetchall()]

def scalar(c, sql, args=()):
    result = rows(c,sql,args)
    return next(iter(result[0].values())) if result else 0

def js(c, key):
    if key not in {'city','signup_version','signup_stats_saved','signup_submitted','vision_schema_version'}:
        raise ValueError('Unapproved projection')
    if db._is_postgres_connection(c):
        return f"(u.stats_json::jsonb ->> '{key}')"
    return f"CAST(json_extract(u.stats_json, '$.{key}') AS TEXT)"

def overview(c):
    now = int(time.time())
    base = ' FROM "Account" a JOIN "User" u ON u.id=a.user_id '
    enabled = base + ' WHERE a.auth_enabled=1 '
    metrics = [
        ('Enabled accounts',scalar(c,'SELECT COUNT(*) n'+enabled),'Includes existing beta accounts; excludes disabled accounts and profiles without an account.'),
        ('Phone verified',scalar(c,'SELECT COUNT(*) n'+enabled+' AND a.verified_phone=1'),'Phone ownership confirmed; not an identity or BGV pass.'),
        ('New signup flow',scalar(c,'SELECT COUNT(*) n'+enabled+" AND "+js(c,'signup_version')+"='3'"),'Accounts created through the current self-signup flow.'),
        ('Overall BGV verified',scalar(c,'SELECT COUNT(*) n'+enabled+" AND u.bgv_status='verified'"),'Current stored account-level status; sandbox and production checks shown separately in Checks.'),
        ('Dating stage',scalar(c,'SELECT COUNT(*) n'+enabled+" AND u.journey_state='dating'"),'Journey stage only. This is not a claim that every account is currently eligible for matching.'),
        ('Disabled accounts',scalar(c,'SELECT COUNT(*) n'+base+' WHERE a.auth_enabled=0'),'Retained account records; not active registrations.')]
    observed_since=scalar(c,'SELECT MIN(first_seen_at) FROM "UserActivity"')
    for days,label in [(1,'Active in last 24 hours'),(7,'Active in last 7 days'),(30,'Active in last 30 days')]:
        metrics.append((label,scalar(c,'SELECT COUNT(*) n FROM "UserActivity" v JOIN "Account" a ON a.user_id=v.user_id WHERE a.auth_enabled=1 AND v.last_seen_at>=?',(now-days*86400,)) if observed_since else None,
                        'Observed authenticated requests since activity tracking was enabled; not historical estimates.'))
    funnel=[]
    for key,label in [('vision_schema_version','Vision saved'),('signup_stats_saved','Stats saved'),('signup_submitted','Signup submitted')]:
        expression=js(c,key)
        condition = expression+"='2'" if key=='vision_schema_version' else expression+" IN ('true','1')"
        funnel.append({'milestone':label,'accounts':scalar(c,'SELECT COUNT(*) n'+enabled+' AND '+condition)})
    funnel.append({'milestone':'Chemistry saved','accounts':None})
    return {'metrics':[{'label':a,'value':b,'note':d,'filter':{'Enabled accounts':'enabled','Phone verified':'phone_verified','New signup flow':'new_signup','Overall BGV verified':'bgv_verified','Dating stage':'dating','Disabled accounts':'disabled','Active in last 24 hours':'active_1','Active in last 7 days':'active_7','Active in last 30 days':'active_30'}[a]} for a,b,d in metrics],
        'groups':rows(c,'SELECT u.journey_state AS stage,COUNT(*) AS accounts'+enabled+' GROUP BY u.journey_state ORDER BY COUNT(*) DESC'),
        'funnel':funnel,'notes':['Counts are distinct enabled accounts unless labelled otherwise. A valid session does not prove the person is online.',
        'Chemistry completion is not inferred from empty/default JSON; its milestone count needs a dedicated event.',
        'Actual matching eligibility is not calculated here because preparation/eligibility workflows can mutate member state.']}

def cohort(c, name):
    allowed={
        'enabled':('a.auth_enabled=1',()),
        'phone_verified':('a.auth_enabled=1 AND a.verified_phone=1',()),
        'new_signup':('a.auth_enabled=1 AND '+js(c,'signup_version')+"='3'",()),
        'bgv_verified':("a.auth_enabled=1 AND u.bgv_status='verified'",()),
        'dating':("a.auth_enabled=1 AND u.journey_state='dating'",()),
        'disabled':('a.auth_enabled=0',())}
    for days in (1,7,30):allowed['active_'+str(days)]=('a.auth_enabled=1 AND v.last_seen_at>=?',(int(time.time())-days*86400,))
    for key,label in [('vision_schema_version','vision'),('signup_stats_saved','stats'),('signup_submitted','submitted')]:
        allowed[label]=('a.auth_enabled=1 AND '+js(c,key)+("='2'" if label=='vision' else " IN ('true','1')"),())
    if name.startswith('city:') and len(name)<=100:return "a.auth_enabled=1 AND COALESCE(NULLIF("+js(c,'city')+",''),'Not set')=?",(name[5:],)
    if name.startswith('payment:') and name[8:] in ('sandbox','live','test'):
        return '''a.auth_enabled=1 AND EXISTS (SELECT 1 FROM "BillingPurchase" b WHERE b.user_id=a.user_id AND b.mode=? AND b.payment_status='captured' AND b.refund_status='none')''',(name[8:],)
    if name.startswith('stage:') and len(name)<=80:return 'a.auth_enabled=1 AND u.journey_state=?',(name[6:],)
    if name not in allowed:raise ValueError('Invalid account filter')
    return allowed[name]

def users(c, query='', page=1, filter_name=''):

    query=str(query).strip()[:128]; args=[]; where=''
    if query:
        escaped=query.lower().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
        phone=''.join(x for x in query if x.isdigit())
        where=" WHERE (LOWER(a.user_id) LIKE ? ESCAPE '\\' OR REPLACE(REPLACE(COALESCE(a.phone,''),'+',''),' ','')=?)"
        args=['%'+escaped+'%',phone or '-']
    if filter_name:
        condition,values=cohort(c,filter_name)
        where+=(' AND ' if where else ' WHERE ')+condition
        args.extend(values)
    result=rows(c,'SELECT a.user_id,a.phone,a.auth_enabled,a.verified_phone,a.created_at,u.journey_state,u.bgv_status,u.stats_json,v.last_seen_at FROM "Account" a JOIN "User" u ON u.id=a.user_id LEFT JOIN "UserActivity" v ON v.user_id=a.user_id'+where+' ORDER BY a.created_at DESC,a.user_id LIMIT 51 OFFSET ?',(*args,(page-1)*50))
    output=[]
    for row in result[:50]:
        try: stats=json.loads(row.pop('stats_json') or '{}')
        except (ValueError,TypeError): stats={}
        phone=''.join(x for x in str(row.pop('phone') or '') if x.isdigit())
        row['auth_enabled']=bool(row['auth_enabled']);row['verified_phone']=bool(row['verified_phone'])
        output.append({**row,'phone':'•••• '+phone[-4:] if phone else 'Not set','city':str(stats.get('city') or 'Not set')[:80],
            'signup_flow':'Current signup' if stats.get('signup_version')==3 else 'Existing / beta'})
    return {'rows':output,'page':page,'has_more':len(result)>50,'notes':['Search using a full phone number or part of a user ID. Phone values remain masked in results. No identity documents or private profile disclosures are returned.']}

def sessions(c, page=1):
    now=int(time.time())
    result=rows(c,'''SELECT s.id,s.user_id,s.kind,s.created_at,s.access_expires_at,s.expires_at,s.revoked_at,
        a.auth_enabled,v.last_seen_at,
        CASE WHEN EXISTS (SELECT 1 FROM "AuthRefresh" r WHERE r.session_id=s.id AND r.consumed_at IS NULL AND r.expires_at>?) THEN 1 ELSE 0 END AS refreshable
        FROM "AuthSession" s JOIN "Account" a ON a.user_id=s.user_id LEFT JOIN "UserActivity" v ON v.user_id=s.user_id
        ORDER BY s.created_at DESC,s.id LIMIT 51 OFFSET ?''',(now,(page-1)*50))
    output=[]
    for r in result[:50]:
        status='Access valid'
        if r['revoked_at'] is not None:status='Revoked'
        elif not r['auth_enabled']:status='Account disabled'
        elif r['id'].startswith('tester_') and not auth_sessions.tester_allowed(r['user_id']):status='Tester session disabled'
        elif r['expires_at']<=now:status='Expired'
        elif r['access_expires_at']<=now:status='Refresh available' if r['kind']=='mobile' and r['refreshable'] else 'Login required'
        output.append({'reference':r['id'][:12],'user_id':r['user_id'],'type':r['kind'],'status':status,'signed_in_at':r['created_at'],
            'access_expires_at':r['access_expires_at'],'expires_at':r['expires_at'],'revoked_at':r['revoked_at'],'account_last_active_at':r['last_seen_at']})
    return {'rows':output,'page':page,'has_more':len(result)>50,'notes':['Each row is a successful sign-in, not a unique physical phone. Last activity is account-level, not attributed to an individual session.',
            'Access valid means credentials can authenticate. It does not mean the person is online. This page cannot revoke sessions.']}

def checks(c):
    results=rows(c,'SELECT operation,environment,state,COUNT(*) AS checks FROM "BgvRequest" GROUP BY operation,environment,state ORDER BY operation,environment,state')
    for table,label in [('DigiLockerSession','DigiLocker'),('LivenessSession','Hosted liveness'),('FaceMatchJob','Face comparison'),('AvatarJob','Avatar generation')]:
        # These face/avatar implementations are explicitly sandbox or non-BGV; never label them production proof.
        if table=='DigiLockerSession':
            data=rows(c,'SELECT environment,state,COUNT(*) AS checks FROM "DigiLockerSession" GROUP BY environment,state')
        else:data=rows(c,'SELECT state,COUNT(*) AS checks FROM "'+table+'" GROUP BY state')
        for row in data:results.append({'operation':label,'environment':row.get('environment','not an identity check' if table=='AvatarJob' else 'preproduction'),'state':row['state'],'checks':row['checks']})
    pauses=rows(c,'SELECT environment,operation,error_code,paused_until,updated_at FROM "SignzyGuard" WHERE active=1 AND (paused_until=0 OR paused_until>?) ORDER BY updated_at DESC LIMIT 50',(int(time.time()),))
    errors=rows(c,'SELECT reference,occurred_at,user_id,endpoint,error_type FROM "ErrorReport" ORDER BY occurred_at DESC LIMIT 50')
    return {'rows':results,'pauses':pauses,'errors':errors,'notes':['Check counts are request/session records, not distinct verified people. Sandbox results remain labelled sandbox.',
        'Technical errors are not identity failures. No raw provider response, document, stack trace or private error message is exposed.',
        'The existing CLI recovery procedure is still required to clear a provider pause. No paid check can be retriggered here.']}

def marketing(c):
    enabled=' FROM "Account" a JOIN "User" u ON u.id=a.user_id WHERE a.auth_enabled=1 '
    city=js(c,'city')
    cities=rows(c,"SELECT COALESCE(NULLIF("+city+",''),'Not set') AS city,COUNT(*) AS registrations"+enabled+' GROUP BY '+city+' ORDER BY COUNT(*) DESC')
    payments=rows(c,'SELECT mode,COUNT(DISTINCT b.user_id) AS users FROM "BillingPurchase" b JOIN "Account" a ON a.user_id=b.user_id WHERE a.auth_enabled=1 AND b.payment_status=? AND b.refund_status=? GROUP BY mode',('captured','none'))
    return {'cities':cities,'payments':payments,'notes':['City and payment figures cover enabled accounts; they do not establish campaign attribution.',
        'Captured sandbox payments are test transactions, not revenue. Live payments are shown separately.',
        'Downloads, first opens, campaign spend, acquisition cost and campaign attribution are not connected in this release.',
        'Brand Meadows billable registrations are not calculated until the contractual definition, billing period and exclusions are confirmed.'],
        'unavailable':['App downloads','Campaign attribution','Acquisition cost','Brand Meadows invoice count']}

def audit_log(c):
    return {'rows':rows(c,'SELECT i.email,a.action,a.section,a.created_at FROM "AdminAudit" a LEFT JOIN "AdminIdentity" i ON i.id=a.admin_id ORDER BY a.created_at DESC LIMIT 100'),
            'notes':['Audit entries store the administrator, action, section and time. Search terms, passwords, codes and member details are not logged.']}


def user_summary(c, user_id):
    account=rows(c,'SELECT a.user_id,a.auth_enabled,u.journey_state,u.bgv_status FROM "Account" a JOIN "User" u ON u.id=a.user_id WHERE a.user_id=?',(user_id,))
    if not account:return None
    checks=rows(c,'SELECT operation,environment,state,created_at,updated_at FROM "BgvRequest" WHERE user_id=? ORDER BY created_at DESC LIMIT 50',(user_id,))
    for table,label in [('DigiLockerSession','DigiLocker'),('LivenessSession','Hosted liveness'),('FaceMatchJob','Face comparison'),('AvatarJob','Avatar generation')]:
        field='user_id' if table=='DigiLockerSession' else 'id'
        columns='environment,state,created_at,updated_at' if table=='DigiLockerSession' else 'state,created_at,updated_at'
        result=rows(c,'SELECT '+columns+' FROM "'+table+'" WHERE '+field+'=? ORDER BY created_at DESC LIMIT 5',(user_id,))
        for r in result:checks.append({'operation':label,'environment':r.get('environment','not an identity check' if table=='AvatarJob' else 'preproduction'),'state':r['state'],'created_at':r['created_at'],'updated_at':r['updated_at']})
    return {'account':account,'checks':checks,'errors':rows(c,'SELECT reference,occurred_at,endpoint,error_type FROM "ErrorReport" WHERE user_id=? ORDER BY occurred_at DESC LIMIT 20',(user_id,)),
        'notes':['Private user summary. No identity images, health details, Guru conversations or raw provider records are returned.','Read-only: use established operator procedures for recovery; this page cannot approve checks or repeat paid calls.']}


def check_records(c,operation,environment,state,page=1):
    tables={'DigiLocker':('DigiLockerSession','user_id'),'Hosted liveness':('LivenessSession','id'),'Face comparison':('FaceMatchJob','id'),'Avatar generation':('AvatarJob','id')}
    if operation in tables:
        table,uid=tables[operation]
        expected='not an identity check' if operation=='Avatar generation' else 'preproduction'
        if operation!='DigiLocker' and environment!=expected:raise ValueError('Invalid environment')
        condition='state=?';args=[state]
        if operation=='DigiLocker':condition+=' AND environment=?';args.append(environment)
        statement='SELECT '+uid+' AS user_id,state,created_at,updated_at FROM "'+table+'" WHERE '+condition
    else:
        statement='SELECT user_id,operation,environment,state,created_at,updated_at FROM "BgvRequest" WHERE operation=? AND environment=? AND state=?'
        args=[operation,environment,state]
    result=rows(c,statement+' ORDER BY created_at DESC LIMIT 51 OFFSET ?',(*args,(page-1)*50))
    return {'rows':result[:50],'page':page,'has_more':len(result)>50,'notes':['These are individual request/session records, not distinct people. Raw provider evidence is excluded.']}
