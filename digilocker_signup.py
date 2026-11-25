import signzy_guard
"""Account-bound DigiLocker consent and minimal encrypted identity projection.

Human confirmation requests retrieval; only the provider supplies identity data.
Provider IO is outside transactions. Claimed calls are never automatically replayed.
"""
import os
import secrets
import uuid
from datetime import datetime, timezone, timedelta, date
import auth_sessions
import db
import bgv_policy
from api_contract import ApiError
from bgv_app import Protection
from signzy.client import Client, Config
from signzy.digilocker_create_url import session as provider_session, https_url
from signzy.digilocker_eaadhaar import identity_fields

VERSION = 'digilocker-identity-photo-v2'
BUNDLE_VERSION = 'digilocker-screening-v3'
PHOTO_VERSIONS = {VERSION, BUNDLE_VERSION}
BUNDLE_CONSENT = 'I consent to sharing Aadhaar name, date of birth, document address and photo, and available PAN document identifiers and mobile from DigiLocker through Signzy. DhaShu may use these details for criminal court, FIR and current-employer screening and a future selfie-to-document face comparison, and securely store the results.'
CONSENT = 'I consent to sharing my DigiLocker name, date of birth, document address and document photo with DhaShu through Signzy for identity checks and a future selfie-to-document face comparison.'

def now():
    return datetime.now(timezone.utc)

def cooldown_minutes():
    try:
        minutes=int(os.getenv('DHASHU_DIGILOCKER_COOLDOWN_MINUTES','30'))
        if not 1 <= minutes <= 1440: raise ValueError()
        return minutes
    except ValueError:
        raise ApiError('configuration_error','DigiLocker cooldown configuration needs attention.',503) from None

def cooling(row):
    return bool(row.get('cooldown_until') and now()<datetime.fromisoformat(row['cooldown_until']))

def configuration(uid):
    try:
        if os.getenv('DHASHU_DIGILOCKER_ENABLED') != '1':
            raise ValueError()
        cfg = Config.from_env(); cfg.validate()
        # Sandbox identity must never silently become a live account approval.
        if cfg.environment != 'preproduction':
            raise ValueError()
        https_url(os.environ['SIGNZY_DIGILOCKER_CALLBACK_BASE'])
        Protection()
        return cfg
    except (ValueError, KeyError):
        raise ApiError('digilocker_unavailable', 'DigiLocker is not enabled for this account yet.', 503) from None

def rows(conn, uid):
    return sorted(db.fetch_all(conn, 'DigiLockerSession', user_id=uid), key=lambda r:r['created_at'], reverse=True)

def owned(conn, uid, sid):
    row = db.fetch_one(conn, 'DigiLockerSession', id=sid, user_id=uid)
    if not row:
        raise ApiError('not_found', 'DigiLocker session not found.', 404)
    return row

def update(conn, sid, **values):
    values['updated_at'] = now().isoformat()
    auth_sessions.sql(conn, 'UPDATE "DigiLockerSession" SET ' + ','.join('"'+k+'"=?' for k in values) + ' WHERE id=?', (*values.values(), sid))

def view(conn, uid):
    try:
        cfg = configuration(uid)
    except ApiError:
        return {'enabled': False}
    result = {'enabled':True, 'environment':cfg.environment, 'consent_version':BUNDLE_VERSION, 'consent_text':BUNDLE_CONSENT,
              'cooldown_minutes':cooldown_minutes(),
              'session':None, 'overall_approval':False}
    result['provider_issue']=signzy_guard.public_pause(conn,cfg,'digilocker_create_url')
    latest = [r for r in rows(conn, uid) if r['environment'] == cfg.environment]
    if latest:
        row = latest[0]
        state = row['state']
        if state in ('awaiting_consent', 'pending') and now() >= datetime.fromisoformat(row['expires_at']):
            state = 'expired'
        item = {k:row[k] for k in ('id','expires_at','updated_at')}
        item['state'] = state
        from verification_progress import stalled
        item['recovery_required']=stalled(row) or state=='outcome_unknown'
        if state=='awaiting_consent' and row['attempts']==0:
            item['consent_url'] = Protection().open(row['protected_session'])['url']
        if state == 'complete':
            saved=Protection().open(row['protected_result'])
            item['identity'] = {k:v for k,v in saved.items() if not k.startswith('_')}
            item['field_verifications']={key:{'status':'received','received_at':saved.get('_received_at'),'verified_at':None} for key in ('name','dob','document_address')}
        item['reference_photo_available']=bool(row.get('protected_photo'))
        photo=Protection().open(row['protected_photo']) if row.get('protected_photo') else {}
        item['portrait_image_available']=bool(photo.get('image_base64'))
        item['portrait_download_state']=photo.get('download_state','not_started')
        item['cooldown_until']=row.get('cooldown_until')
        item['cooling_down']=cooling(row)
        item['can_restart']=state=='not_confirmed' and not cooling(row)
        item['can_request_photo']=state=='complete' and not cooling(row) and (row['consent_version']!=BUNDLE_VERSION or not row.get('protected_photo'))
        if state!='complete' and row.get('protected_result'):
            issue=Protection().open(row['protected_result']).get('provider_issue',{})
            if issue: item.update(message=issue.get('user_message'),error_code=issue.get('error_code'))
        result['session'] = item
    return result

def create(conn, uid, body):
    import verification_payment
    verification_payment.require_paid(conn,uid)
    cfg = configuration(uid)
    if os.getenv('DHASHU_BGV_POLICY_ENABLED')=='1':
        import signup_markets
        signup_markets.ensure(conn,uid)
    case_check_id=bgv_policy.check_for(conn,uid,'identity_details',cfg.environment)
    try:
        sid = str(uuid.UUID(body['request_id']))
        if body['consent'] is not True or body['consent_version'] not in PHOTO_VERSIONS:
            raise ValueError()
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ApiError('validation_error', 'Confirm identity consent before creating a link.') from None
    protection = Protection()
    with auth_sessions.transaction(conn):
        db.lock_user_rows(conn, uid)  # perf-rowlock (was a table-wide LOCK TABLE)
        existing = db.fetch_one(conn, 'DigiLockerSession', id=sid)
        if existing:
            owned(conn, uid, sid)
            return
        previous = [r for r in rows(conn, uid) if r['environment'] == cfg.environment]
        if any(cooling(r) for r in previous):
            raise ApiError('cooldown_active','Wait until your DigiLocker cooldown ends before starting a new session.',429)
        if sum(datetime.fromisoformat(r['created_at']) > now()-timedelta(days=1) for r in previous) >= 3:
            raise ApiError('rate_limited', 'Daily consent-link limit reached. Please contact support.', 429)
        if previous:
            last = previous[0]
            old_completed=last['state']=='complete' and (last['consent_version']!=BUNDLE_VERSION or not last.get('protected_photo'))
            retry_after_cooldown=last['state']=='not_confirmed' and not cooling(last)
            if not old_completed and not retry_after_cooldown and (last['state'] in ('creating','retrieving','outcome_unknown','complete') or now() < datetime.fromisoformat(last['expires_at'])):
                raise ApiError('session_exists', 'Resume your existing DigiLocker session or contact support.', 409)
        signzy_guard.require_available(conn,cfg,'digilocker_create_url')
        stamp = now()
        auth_sessions.sql(conn, 'INSERT INTO "DigiLockerSession" (id,user_id,environment,state,protected_session,protected_result,consent_version,created_at,updated_at,expires_at,attempts,case_check_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            (sid,uid,cfg.environment,'creating',None,None,body['consent_version'],stamp.isoformat(),stamp.isoformat(),(stamp+timedelta(minutes=30)).isoformat(),0,case_check_id))
        if async_enabled():
            # perf-worker: the provider call runs in bgv_worker.py; the app shows
            # 'creating' and refreshes until the link is ready. Idempotent per session.
            import provider_jobs
            provider_jobs.enqueue(conn, 'digilocker_create', uid, sid, 'digilocker_create:'+sid)
    if async_enabled():
        return
    request_link(conn, cfg, sid, body['consent_version'], timeout=20)


def async_enabled():
    """perf-worker: DHASHU_ASYNC_DIGILOCKER=1 moves the consent-link provider call to
    the worker (default 0 = unchanged: the call happens inside the request)."""
    return os.getenv('DHASHU_ASYNC_DIGILOCKER', '0') == '1'


def request_link(conn, cfg, sid, consent_version, timeout):
    """The DigiLocker consent-link provider call for session sid (state 'creating')."""
    protection = Protection()
    evidence = []; summary={}
    try:
        summary = signzy_guard.execute(conn, cfg, Client(cfg, timeout=timeout), 'digilocker_create_url', {
            'callbackUrl':os.environ['SIGNZY_DIGILOCKER_CALLBACK_BASE'].rstrip('/')+'/'+secrets.token_hex(16),
            'internalId':'dhashu_'+secrets.token_hex(16), 'serviceName':'DhaShu','includePhoto':True,'includePan':consent_version==BUNDLE_VERSION}, consent_confirmed=True, evidence_sink=evidence.append)
        response = evidence[0].get('provider_response') or {}
        if summary.get('http_status') == 200 and not summary.get('error_code'):
            request_id, url = provider_session(response.get('json'))
            linked = {'requestId':request_id, 'url':url}
            protected = protection.seal(linked)
            state = 'awaiting_consent'
        else:
            protected = None
            state = 'outcome_unknown' if summary.get('http_status') is None else 'unavailable'
    except Exception:
        state, protected = 'outcome_unknown', None
    with auth_sessions.transaction(conn):
        update(conn, sid, state=state, protected_session=protected, protected_result=protection.seal({'provider_issue':summary}) if summary.get('error_code') else None)

def projection(body, today=None):
    fields = identity_fields(body)
    if set(fields) != {'name','dob','address'}:
        raise ValueError('Missing identity fields')
    born = datetime.strptime(fields['dob'], '%d/%m/%Y').date()
    today = today or (now()+timedelta(hours=5,minutes=30)).date()
    age = today.year-born.year-((today.month,today.day)<(born.month,born.day))
    if born > today or age > 120:
        raise ValueError('Invalid birth date')
    return {'name':fields['name'], 'dob':born.isoformat(), 'age':age, 'age_as_of':today.isoformat(),
            'document_address':fields['address'], 'source':'digilocker_eaadhaar',
            'adult':age >= 18, 'current_address_verified':False}

def complete(conn, uid, sid, body):
    cfg = configuration(uid)
    if body.get('consent_completed') is not True:
        raise ApiError('validation_error', 'Complete OTP and document consent in DigiLocker first.')
    with auth_sessions.transaction(conn):
        row = owned(conn, uid, sid)
        if row['environment'] != cfg.environment:
            raise ApiError('environment_mismatch', 'Start a session in the current environment.', 409)
        if row['state'] == 'complete':
            import verified_identity
            verified_identity.apply(conn,uid,sid,Protection().open(row['protected_result']),cfg.environment)
            return
        if cooling(row):
            raise ApiError('cooldown_active','This confirmation was already submitted. Wait for the cooldown or contact support.',429)
        if row['state'] != 'awaiting_consent' or row['attempts']!=0:
            raise ApiError('session_busy', 'Refresh status. This request cannot be repeated automatically.', 409)
        if now() >= datetime.fromisoformat(row['expires_at']):
            raise ApiError('expired', 'This consent session has expired. Create a new link.', 409)
        # CAS is important on PostgreSQL: concurrent confirmations must make one call.
        signzy_guard.require_available(conn,cfg,'digilocker_eaadhaar')
        claimed_at=now()
        claim = auth_sessions.sql(conn, 'UPDATE "DigiLockerSession" SET state=?, attempts=attempts+1, updated_at=?, cooldown_until=? WHERE id=? AND state=? AND attempts=?',
            ('retrieving',claimed_at.isoformat(),(claimed_at+timedelta(minutes=cooldown_minutes())).isoformat(),sid,row['state'],row['attempts']))
        if claim.rowcount != 1:
            raise ApiError('session_busy', 'Retrieval is already in progress.', 409)
    protection = Protection(); evidence=[]; protected=None; summary={}
    try:
        linked = protection.open(row['protected_session'])
        # Existing pre-photo consent is not silently expanded.
        summary = signzy_guard.execute(conn, cfg, Client(cfg, timeout=20), 'digilocker_eaadhaar', {'requestId':linked['requestId'],'includePhoto':row['consent_version'] in PHOTO_VERSIONS},
            consent_confirmed=True, evidence_sink=evidence.append)
        status = summary.get('http_status')
        if status == 200 and not summary.get('error_code'):
            try:
                identity = projection(evidence[0]['provider_response']['json'])
                identity['_received_at']=now().isoformat()
                if row['consent_version']==BUNDLE_VERSION:
                    import json
                    declared=json.loads(db.fetch_one(conn,'User',id=uid)['stats_json'] or '{}')
                    identity['_bundle']={'version':BUNDLE_VERSION,'accepted_at':row['created_at'],'pan_scope':True,'employer':declared.get('employer','')}
                protected = protection.seal(identity)
                state = 'complete' if identity['adult'] else 'needs_review'
            except (ValueError, TypeError, KeyError):
                state = 'needs_review'
        elif status == 202 and not summary.get('error_code'):
            state = 'not_confirmed'
        else:
            state = 'outcome_unknown' if status is None else 'needs_review'
    except Exception:
        state = 'outcome_unknown'
    if summary.get('error_code'):
        protected=protection.seal({'provider_issue':summary})
        state='outcome_unknown' if summary.get('http_status') is None else 'unavailable'
    photo=None
    if state=='complete' and row['consent_version'] in PHOTO_VERSIONS:
        from signzy.document_photo import reference
        found=reference(evidence[0]['provider_response']['json'])
        if found: photo=protection.seal({**found,'consent_version':row['consent_version'],'received_at':now().isoformat()})
    with auth_sessions.transaction(conn):
        update(conn, sid, state=state, protected_result=protected,protected_photo=photo)
        if state=='complete':
            import verified_identity
            verified_identity.apply(conn,uid,sid,identity,cfg.environment)


def _job_run(conn, job):
    """Worker handler: never replays a call whose outcome is unknown (max_attempts=1)."""
    row = db.fetch_one(conn, 'DigiLockerSession', id=job['ref'])
    if not row or row['state'] != 'creating':
        return   # already handled (or cancelled): nothing to do
    request_link(conn, configuration(row['user_id']), row['id'], row['consent_version'], timeout=10)


def _job_dead(conn, job):
    """A worker died mid-call: the provider outcome is unknown; tell the member plainly."""
    row = db.fetch_one(conn, 'DigiLockerSession', id=job['ref'])
    if row and row['state'] == 'creating':
        update(conn, row['id'], state='outcome_unknown')


def _register_jobs():
    import provider_jobs
    provider_jobs.register_kind('digilocker_create', _job_run, on_dead=_job_dead, max_attempts=1, lease=60)


_register_jobs()
