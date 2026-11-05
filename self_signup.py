"""Phone-verified, resumable launch signup. OTP/payment never approve BGV."""
import json
import uuid
from datetime import date
from flask import g,jsonify,current_app,request
import db
import auth_sessions
import onboarding
import launch_cities
import profile_choices
import stats_edit
from bgv_app import Protection
from api_contract import ApiError,json_object

VERSION=3
TEXT_FIELDS={'profession','employer','neighbourhoods','food_needs','venue_accessibility'}
MULTI={'religion','ethnicity','languages','cuisine','budget'}
FIELDS=(set(stats_edit.ALL_FIELDS)-{'age','children_count'})|TEXT_FIELDS

def create_account(conn,phone):
    """Caller owns AuthChallenge + Account locks; invoked only after provider OTP approval."""
    uid=onboarding.new_user_id()
    db.insert_row(conn,'User',{'id':uid,'journey_state':'onboarding','bgv_status':'declared','stats_json':json.dumps({'signup_version':VERSION}),
        'vision_json':'[]','skills_json':'{}','preferences_json':json.dumps({'fixed':{'dealbreakers':[]},'adjustable':{'distance_km':[0,30]}})})
    account={'id':uuid.uuid4().hex,'user_id':uid,'phone':phone,'auth_enabled':1,'verification_required':1,'verified_phone':1,'created_at':str(auth_sessions.now())}
    db.insert_row(conn,'Account',account)
    db.insert_row(conn,'EnrollmentDraft',{'id':uid,'payload_json':'{}','revision':0})
    return account

def options():
    return {'cities':launch_cities.active(),'metro_catalogue':launch_cities.CITIES,'gender':onboarding.GENDERS_FOR_SIGNUP,
        'fields':onboarding.STAT_OPTIONS,'ranges':{k:v for k,v in onboarding.STAT_RANGES.items() if k not in ('age','children_count')},
        'health':profile_choices.HEALTH,'max_religions':2,'max_ethnicities':2}

def parts(conn,uid):
    user=db.fetch_one(conn,'User',id=uid)
    if not user:raise ApiError('not_found','Account not found.',404)
    return user,json.loads(user['stats_json'] or '{}')

def state(conn,uid):
    user,stats=parts(conn,uid)
    modern=stats.get('signup_version')==VERSION
    draft=db.fetch_one(conn,'EnrollmentDraft',id=uid)
    payload=db.load_json_field(draft['payload_json'],{}) if draft else {}
    claims=Protection().open(payload['identity_claims']) if payload.get('identity_claims') else {}
    import verified_identity
    identity=verified_identity.owner_identity(conn,uid)
    values={k:stats.get(k) for k in FIELDS}
    values.update(name=identity['name'] if identity else claims.get('name',''),dob=identity['dob'] if identity else claims.get('dob',''),
        gender=stats.get('gender',''),city=stats.get('city',''),health=stats.get('health_shared',{}))
    skills=db.load_json_field(user['skills_json'],{})
    step=0 if stats.get('vision_schema_version')!=2 else 1 if not stats.get('signup_stats_saved') else 2 if len(skills.get('activities',{}))<onboarding.MIN_SORTED else 3
    return {'version':VERSION,'modern':modern,'next_step':step,'submitted':bool(stats.get('signup_submitted')),'admitted':user['bgv_status']=='verified' and user['journey_state']=='dating',
        'identity_confirmed':bool(identity),'values':values,'options':options()}

def save_stats(conn,uid,body):
    from datetime import datetime
    if set(body)!={'name','dob','gender','city','fields','health'}:raise ApiError('validation_error','Provide identity, launch city and your declared details.')
    if not isinstance(body['name'],str) or not 1<=len(body['name'].strip())<=200:raise ApiError('validation_error','Enter your name as on Aadhaar.')
    try:
        born=date.fromisoformat(body['dob']);today=date.today()
        age=today.year-born.year-((today.month,today.day)<(born.month,born.day))
        if age<18 or age>120:raise ValueError()
    except (TypeError,ValueError):raise ApiError('validation_error','Enter a valid date of birth. You must be 18 or older.')
    city=launch_cities.find(body['city'])
    if not city or not city['enabled']:raise ApiError('launch_city_required','Choose Bangalore, Delhi or Mumbai.')
    if body['gender'] not in onboarding.GENDERS_FOR_SIGNUP:raise ApiError('validation_error','Choose your gender for matching.')
    fields=body['fields']
    if type(fields) is not dict or set(fields)-FIELDS:raise ApiError('validation_error','Unknown Stats field.')
    clean={}
    for key,value in fields.items():
        if value is None or value=='':continue
        if key in TEXT_FIELDS:
            if not isinstance(value,str) or len(value)>200:raise ApiError('validation_error',key+' must be up to 200 characters.')
            clean[key]=value.strip()
        elif key in MULTI:
            if type(value) is not list or any(type(v) is not str or v not in onboarding.STAT_OPTIONS[key] for v in value) or len(set(value))!=len(value) or (key in ('religion','ethnicity') and len(value)>2):raise ApiError('validation_error','Choose listed '+key+' options; religion and ethnicity allow up to two.')
            if value:clean[key]=value
        elif key in onboarding.STAT_RANGES:
            lo,hi=onboarding.STAT_RANGES[key]
            if type(value) is not int or not lo<=value<=hi:raise ApiError('validation_error',key+' must be a whole number in the listed range.')
            clean[key]=value
        elif key in onboarding.STAT_OPTIONS:
            if type(value) is not str or value not in onboarding.STAT_OPTIONS[key]:raise ApiError('validation_error','Choose a listed '+key+' option.')
            clean[key]=value
    health=body['health']
    if type(health) is not dict or set(health)!={'disclosure','categories','note','consent'} or health['disclosure'] not in ('undisclosed','none','shared') or type(health['consent']) is not bool:raise ApiError('validation_error','Choose whether to disclose health/accessibility details.')
    if health['disclosure']=='shared' and not health['consent']:raise ApiError('consent_required','Confirm consent to share your health/accessibility details.')
    shared,_=profile_choices.validate({'categories':health['categories'] if health['disclosure']=='shared' else [],'share_health':health['disclosure']=='shared' and health['consent'],'note':health['note'] if health['disclosure']=='shared' else '', 'openness':'any','open_categories':[],'include_undisclosed':True})
    shared['disclosure']=health['disclosure']
    import verified_identity
    identity=verified_identity.owner_identity(conn,uid)
    if identity and (body['name'].strip()!=identity['name'] or body['dob']!=identity['dob']):raise ApiError('identity_owned_field','Your name and DOB are set by confirmed DigiLocker details.',409)
    with auth_sessions.transaction(conn):
        user,stats=parts(conn,uid)
        if stats.get('signup_version')!=VERSION or stats.get('signup_submitted'):raise ApiError('signup_closed','Use profile editing for an existing submitted profile.',409)
        if user.get('active_bgv_case_id') and stats.get('city')!=city['name']:
            if db.fetch_all(conn,'DigiLockerSession',user_id=uid) or db.fetch_all(conn,'BgvRequest',user_id=uid):raise ApiError('market_locked','Your verification has started for this city. Contact support to change it.',409)
            user['active_bgv_case_id']=None
        for field in FIELDS:stats.pop(field,None)
        stats.update(clean,health_shared=shared,city=city['name'],gender=body['gender'],signup_stats_saved=True,age=identity['age'] if identity else age,age_band=onboarding.age_band_for(identity['age'] if identity else age))
        user['stats_json']=json.dumps(stats,ensure_ascii=False);db.insert_row(conn,'User',user)
        draft=db.fetch_one(conn,'EnrollmentDraft',id=uid)
        payload=db.load_json_field(draft['payload_json'],{})
        payload['identity_claims']=Protection().seal({'name':body['name'].strip(),'dob':body['dob']})
        draft.update(payload_json=json.dumps(payload),revision=draft['revision']+1);db.insert_row(conn,'EnrollmentDraft',draft)
    import signup_markets
    signup_markets.ensure(conn,uid)
    return state(conn,uid)

def reconcile(conn,uid):
    user,stats=parts(conn,uid)
    if stats.get('signup_version')!=VERSION or not stats.get('signup_submitted') or user['bgv_status']=='verified':return
    import verified_identity,liveness_secure_service,verification_payment
    identity=verified_identity.owner_identity(conn,uid)
    if not identity or identity['age']<18 or not verification_payment.view(conn,uid)['can_begin']:return
    face=liveness_secure_service.row(conn,uid)
    if not face or face['state']!='matched' or face['digilocker_session_id']!=stats.get('identity_session_id'):return
    case=db.fetch_one(conn,'BgvCase',id=user.get('active_bgv_case_id'))
    if not case or case['environment']!=stats.get('identity_environment'):return
    ids={r['id'] for r in db.fetch_all(conn,'BgvCaseCheck',case_id=user.get('active_bgv_case_id'))}
    source=db.fetch_one(conn,'DigiLockerSession',id=stats.get('identity_session_id'))
    if not source or source.get('case_check_id') not in ids:return
    latest={}
    for r in sorted(db.fetch_all(conn,'BgvRequest',user_id=uid),key=lambda r:r['created_at'],reverse=True):
        if r.get('case_check_id') in ids and r['environment']==case['environment'] and r['operation'] not in latest:latest[r['operation']]=r
    required=['individual_result','fir_result']+(['current_employer'] if stats.get('employment_category')=='Salaried' else [])
    if any(latest.get(op,{}).get('state')!='verified' for op in required):return
    with auth_sessions.transaction(conn):
        auth_sessions.sql(conn,'UPDATE "User" SET bgv_status=?,journey_state=? WHERE id=? AND journey_state=?',('verified','dating',uid,'onboarding'))

def complete(conn,uid):
    snapshot=state(conn,uid)
    if not snapshot['modern'] or snapshot['next_step']<3:raise ApiError('signup_incomplete','Complete Vision, Stats and Chemistry first.',409)
    import verification_payment
    verification_payment.require_paid(conn,uid)
    if not snapshot['identity_confirmed']:raise ApiError('identity_required','Complete Aadhaar verification first.',409)
    with auth_sessions.transaction(conn):
        user,stats=parts(conn,uid);stats['signup_submitted']=True
        user.update(stats_json=json.dumps(stats),bgv_status='pending' if user['bgv_status']=='declared' else user['bgv_status']);db.insert_row(conn,'User',user)
        draft=db.fetch_one(conn,'EnrollmentDraft',id=uid)
        if draft and not draft.get('completed_at'):
            draft.update(completed_at=str(auth_sessions.now()),revision=draft['revision']+1);db.insert_row(conn,'EnrollmentDraft',draft)
    reconcile(conn,uid)
    return state(conn,uid)

def register(api,get_db):
    def actor():
        if not current_app.config.get('AUTH_ENABLED') or not request.headers.get('Authorization','').startswith('Bearer ') or not getattr(g,'auth_session',None):raise ApiError('secure_auth_required','Sign in with your own phone and OTP to manage signup.',403)
        return g.api_user['user_id']
    @api.get('/signup/state')
    def signup_state():
        reconcile(get_db(),actor())
        return jsonify(state(get_db(),actor()))
    @api.put('/signup/stats')
    def signup_stats():
        body=json_object(required={'name','dob','gender','city','fields','health'})
        return jsonify(save_stats(get_db(),actor(),body))
    @api.post('/signup/complete')
    def signup_complete():
        json_object();return jsonify(complete(get_db(),actor()))
