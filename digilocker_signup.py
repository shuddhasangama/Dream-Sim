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
        testers = os.getenv('DHASHU_DIGILOCKER_TESTERS', '').split(',')
        if cfg.environment != 'preproduction' or uid not in {v.strip() for v in testers}:
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
    latest = [r for r in rows(conn, uid) if r['environment'] == cfg.environment]
    if latest:
        row = latest[0]
        state = row['state']
        if state in ('awaiting_consent', 'pending') and now() >= datetime.fromisoformat(row['expires_at']):
            state = 'expired'
        item = {k:row[k] for k in ('id','expires_at','updated_at')}
        item['state'] = state
        if state=='awaiting_consent' and row['attempts']==0:
            item['consent_url'] = Protection().open(row['protected_session'])['url']
        if state == 'complete':
            item['identity'] = {k:v for k,v in Protection().open(row['protected_result']).items() if not k.startswith('_')}
        item['reference_photo_available']=bool(row.get('protected_photo'))
        photo=Protection().open(row['protected_photo']) if row.get('protected_photo') else {}
        item['portrait_image_available']=bool(photo.get('image_base64'))
        item['portrait_download_state']=photo.get('download_state','not_started')
        item['cooldown_until']=row.get('cooldown_until')
        item['cooling_down']=cooling(row)
        item['can_restart']=state=='not_confirmed' and not cooling(row)
        item['can_request_photo']=state=='complete' and not cooling(row) and (row['consent_version']!=BUNDLE_VERSION or not row.get('protected_photo'))
        result['session'] = item
    return result

def create(conn, uid, body):
    import verification_payment
    verification_payment.require_paid(conn,uid)
    cfg = configuration(uid)
    case_check_id=bgv_policy.check_for(conn,uid,'identity_details',cfg.environment)
    try:
        sid = str(uuid.UUID(body['request_id']))
        if body['consent'] is not True or body['consent_version'] not in PHOTO_VERSIONS:
            raise ValueError()
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ApiError('validation_error', 'Confirm identity consent before creating a link.') from None
    protection = Protection()
    with auth_sessions.transaction(conn):
        if db._is_postgres_connection(conn):
            auth_sessions.sql(conn, 'LOCK TABLE "DigiLockerSession" IN SHARE ROW EXCLUSIVE MODE')
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
        stamp = now()
        auth_sessions.sql(conn, 'INSERT INTO "DigiLockerSession" (id,user_id,environment,state,protected_session,protected_result,consent_version,created_at,updated_at,expires_at,attempts,case_check_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)',
            (sid,uid,cfg.environment,'creating',None,None,body['consent_version'],stamp.isoformat(),stamp.isoformat(),(stamp+timedelta(minutes=30)).isoformat(),0,case_check_id))
    evidence = []
    try:
        summary = Client(cfg, timeout=20).execute('digilocker_create_url', {
            'callbackUrl':os.environ['SIGNZY_DIGILOCKER_CALLBACK_BASE'].rstrip('/')+'/'+secrets.token_hex(16),
            'internalId':'dhashu_'+secrets.token_hex(16), 'serviceName':'DhaShu','includePhoto':True,'includePan':body['consent_version']==BUNDLE_VERSION}, consent_confirmed=True, evidence_sink=evidence.append)
        response = evidence[0].get('provider_response') or {}
        if summary.get('http_status') == 200:
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
        update(conn, sid, state=state, protected_session=protected)

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
        claimed_at=now()
        claim = auth_sessions.sql(conn, 'UPDATE "DigiLockerSession" SET state=?, attempts=attempts+1, updated_at=?, cooldown_until=? WHERE id=? AND state=? AND attempts=?',
            ('retrieving',claimed_at.isoformat(),(claimed_at+timedelta(minutes=cooldown_minutes())).isoformat(),sid,row['state'],row['attempts']))
        if claim.rowcount != 1:
            raise ApiError('session_busy', 'Retrieval is already in progress.', 409)
    protection = Protection(); evidence=[]; protected=None
    try:
        linked = protection.open(row['protected_session'])
        # Existing pre-photo consent is not silently expanded.
        summary = Client(cfg, timeout=20).execute('digilocker_eaadhaar', {'requestId':linked['requestId'],'includePhoto':row['consent_version'] in PHOTO_VERSIONS},
            consent_confirmed=True, evidence_sink=evidence.append)
        status = summary.get('http_status')
        if status == 200:
            try:
                identity = projection(evidence[0]['provider_response']['json'])
                if row['consent_version']==BUNDLE_VERSION:
                    identity['_bundle']={'version':BUNDLE_VERSION,'accepted_at':row['created_at'],'pan_scope':True,'employer':''}
                protected = protection.seal(identity)
                state = 'complete' if identity['adult'] else 'needs_review'
            except (ValueError, TypeError, KeyError):
                state = 'needs_review'
        elif status == 202:
            state = 'not_confirmed'
        else:
            state = 'outcome_unknown' if status is None else 'needs_review'
    except Exception:
        state = 'outcome_unknown'
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
