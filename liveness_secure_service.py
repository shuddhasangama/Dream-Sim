import signzy_guard
"""Owner-bound hosted sandbox capture. Redirect/return never establishes identity."""
import os
import secrets
from datetime import datetime, timezone, timedelta
from urllib.parse import urlsplit
import auth_sessions
import db
from api_contract import ApiError
from bgv_app import Protection
from signzy.client import Client, Config
from signzy.document_photo import reference
from signzy.liveness_secure_create import session

VERSION = 'hosted-liveness-aadhaar-v1'
CONSENT = ('I agree to Signzy capturing my live selfie and comparing it with my Aadhaar portrait. '
           'Signzy retention for this sandbox test is six months. DhaShu stores encrypted results and may '
           'offer this selfie for avatar generation only with my separate OpenAI consent. One capture link '
           'is created per account. This sandbox check does not approve my account.')
HOST = 'liveliness-preproduction.signzy.app'
MESSAGES = {'not_started': 'Verify your live face against Aadhaar.', 'queued_create': 'Preparing your capture link.',
    'creating': 'Preparing your capture link.', 'awaiting_capture': 'Complete capture on Signzy, then return here.',
    'queued_get': 'Checking your capture result.', 'retrieving': 'Checking your capture result.',
    'pending': 'Capture is not complete yet. Finish on Signzy before checking again.',
    'matched': 'Liveness and Aadhaar face match passed.', 'not_matched': 'One or more face checks did not pass.',
    'unknown': 'The outcome could not be confirmed. Contact support before starting another paid check.',
    'expired': 'The capture session has expired. Contact support.', 'deleted': 'Private face evidence removed.'}


def stamp():
    return datetime.now(timezone.utc).isoformat()


def enabled():
    return os.getenv('DHASHU_LIVENESS_SECURE_ENABLED') == '1' and os.getenv('SIGNZY_ENV', 'preproduction') == 'preproduction'


def row(conn, uid):
    return db.fetch_one(conn, 'LivenessSession', id=uid)


def view(conn, uid):
    import face_match_service
    r = row(conn, uid)
    _, source = face_match_service.sources(conn, uid)
    state = r['state'] if r else 'not_started'
    result = Protection().open(r['protected_result']) if r and r.get('protected_result') else {}
    summary = result.get('summary', {})
    if enabled() and state in ('not_started','queued_create','queued_get'):
        summary={**summary,**signzy_guard.public_pause(conn,Config.from_env(),'liveness_secure_data' if state=='queued_get' else 'liveness_secure_create')}
    can_complete = bool(r and state in ('awaiting_capture', 'pending') and r['fetch_count'] < 3
        and r['next_fetch_at'] <= stamp() and r['capture_until'] > stamp())
    url = None
    if r and state in ('awaiting_capture', 'pending') and r.get('protected_session') and r['capture_until'] > stamp():
        url = Protection().open(r['protected_session'])['url']
    return {'enabled': enabled(), 'operation': 'liveness_secure', 'provider': 'signzy', 'sandbox': True,
        'state': state, 'session_id': r['flow_id'] if r else None, 'message': summary.get('user_message') or MESSAGES.get(state, 'Check status.'),
        'checked_at': r['updated_at'] if r and state in ('matched', 'not_matched') else None,
        'reference_ready': bool(source), 'can_request': enabled() and not r and bool(source) and not summary.get('provider_paused'),
        'can_complete': enabled() and can_complete, 'capture_url': url, 'consent_version': VERSION, 'consent_text': CONSENT,
        'threshold': .6, 'liveness': 'passed' if summary.get('liveness_passed') is True else 'failed' if summary.get('liveness_passed') is False else 'pending',
        'face_match_passed': summary.get('face_match_passed'), 'match_percentage': summary.get('match_percentage'),
        'combined_passed': summary.get('combined_passed'), 'additional_checks_passed': summary.get('additional_checks_passed'),
        'automatic_verification': False}


def queue_create(conn, uid, body):
    import face_match_service
    if not enabled():
        raise ApiError('liveness_unavailable', 'Hosted liveness is not enabled.', 503)
    if body.get('consent') is not True or body.get('consent_version') != VERSION:
        raise ApiError('consent_required', 'Confirm Signzy capture consent.')
    with auth_sessions.transaction(conn):
        if db._is_postgres_connection(conn):
            auth_sessions.sql(conn, 'LOCK TABLE "LivenessSession" IN SHARE ROW EXCLUSIVE MODE')
        if row(conn, uid):
            return  # Existing capture reservation is idempotent, including lost responses.
        _, source = face_match_service.sources(conn, uid)
        if not source or not reference({'result': {'photo': source[1].get('url')}}):
            raise ApiError('aadhaar_photo_required', 'Complete DigiLocker photo sharing first.', 409)
        now = datetime.now(timezone.utc)
        db.insert_row(conn, 'LivenessSession', {'id': uid, 'flow_id': secrets.token_hex(16), 'state': 'queued_create',
            'digilocker_session_id': source[0]['id'], 'protected_input': Protection().seal({'photo_url': source[1]['url']}),
            'protected_session': None, 'protected_result': None, 'fetch_count': 0, 'next_fetch_at': stamp(),
            'consent_version': VERSION, 'consent_at': stamp(), 'created_at': stamp(), 'updated_at': stamp(),
            'capture_until': (now + timedelta(hours=24)).isoformat(), 'expires_at': (now + timedelta(days=30)).isoformat()})


def queue_get(conn, uid, flow_id):
    if not enabled():
        raise ApiError('liveness_unavailable', 'Hosted liveness is not enabled.', 503)
    with auth_sessions.transaction(conn):
        r = row(conn, uid)
        if not r or r['flow_id'] != flow_id:
            raise ApiError('session_not_found', 'Capture session not found.', 404)
        if r['state'] not in ('awaiting_capture', 'pending'):
            return
        if r['capture_until'] <= stamp():
            raise ApiError('capture_expired', 'The capture session expired. Contact support.', 409)
        if r['fetch_count'] >= 3 or r['next_fetch_at'] > stamp():
            raise ApiError('capture_cooldown', 'Finish capture before checking again. Checks have a one-minute cooldown and a three-request limit.', 409)
        auth_sessions.sql(conn, 'UPDATE "LivenessSession" SET state=?,updated_at=? WHERE id=? AND state=?',
            ('queued_get', stamp(), uid, r['state']))


def selfie(conn, uid):
    r = row(conn, uid)
    if not r or r['state'] != 'matched' or not r.get('protected_result') or r['expires_at'] <= stamp():
        return None
    return Protection().open(r['protected_result']).get('selfie')


def clear(conn, uid):
    auth_sessions.sql(conn, 'UPDATE "LivenessSession" SET state=?,protected_input=NULL,protected_session=NULL,protected_result=NULL,updated_at=? WHERE id=?',
        ('deleted', stamp(), uid))


def work_one(conn, client_factory=Client, download=None):
    from digilocker_photo_cache import download as download_image
    download = download or download_image
    with auth_sessions.transaction(conn):
        cutoff = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        auth_sessions.sql(conn, 'UPDATE "LivenessSession" SET state=?,updated_at=? WHERE state IN (?,?) AND updated_at<?',
            ('unknown', stamp(), 'creating', 'retrieving', cutoff))
        auth_sessions.sql(conn, 'UPDATE "LivenessSession" SET state=? WHERE capture_until<? AND state IN (?,?,?)',
            ('expired', stamp(), 'awaiting_capture', 'pending', 'queued_create'))
        expired = auth_sessions.sql(conn, 'SELECT * FROM "LivenessSession" WHERE expires_at<? AND (protected_input IS NOT NULL OR protected_session IS NOT NULL)', (stamp(),)).fetchall()
        for old in expired:
            old = dict(old)
            record = Protection().open(old['protected_result']) if old.get('protected_result') else {}
            auth_sessions.sql(conn, 'UPDATE "LivenessSession" SET protected_input=NULL,protected_session=NULL,protected_result=? WHERE id=?',
                (Protection().seal({'summary': record.get('summary', {})}), old['id']))
    if not enabled():
        return False
    with auth_sessions.transaction(conn):
        raw = auth_sessions.sql(conn, 'SELECT * FROM "LivenessSession" WHERE state IN (?,?) ORDER BY created_at LIMIT 1', ('queued_create', 'queued_get')).fetchone()
        if not raw:
            return False
        r = dict(raw)
        creating = r['state'] == 'queued_create'
        if signzy_guard.blocked(conn,Config.from_env(),'liveness_secure_create' if creating else 'liveness_secure_data'): return False
        claimed = 'creating' if creating else 'retrieving'
        count = r['fetch_count'] + (0 if creating else 1)
        changed = auth_sessions.sql(conn, 'UPDATE "LivenessSession" SET state=?,fetch_count=?,updated_at=? WHERE id=? AND state=?',
            (claimed, count, stamp(), r['id'], r['state']))
        if changed.rowcount != 1:
            return False
    evidence = None
    summary = {}
    protected_session = r.get('protected_session')
    result = {}
    state = 'unknown'
    def sink(value):
        nonlocal evidence
        evidence = value
    try:
        config = Config.from_env()
        if config.environment != 'preproduction':
            raise ValueError('Sandbox only')
        if creating:
            original = Protection().open(r['protected_input'])
            summary = signzy_guard.execute(conn, config, client_factory(config), 'liveness_secure_create', {'matchImage': [original['photo_url']],
                'faceMatchThreshold': .6, 'piiDeletionTTL': '6 months'}, consent_confirmed=True, evidence_sink=sink)
            if summary.get('capture_link_received') is True and evidence and not summary.get('error_code'):
                token, url, consumer = session(evidence['provider_response']['json'])
                if urlsplit(url).hostname != HOST:
                    raise ValueError('Unexpected capture host')
                protected_session = Protection().seal({'token': token, 'url': url, 'consumer': consumer})
                state = 'awaiting_capture'
        else:
            link = Protection().open(r['protected_session'])
            summary = signzy_guard.execute(conn, config, client_factory(config), 'liveness_secure_data', {'token': link['token']}, consent_confirmed=True, evidence_sink=sink)
            if summary.get('error_code'): raise ValueError('Provider request could not complete')
            body = ((evidence or {}).get('provider_response') or {}).get('json') or {}
            provider = body.get('result') if isinstance(body, dict) else None
            if not isinstance(provider, dict) or provider.get('token') != link['token'] or provider.get('consumerId') != link['consumer']:
                summary={'outcome':'session_binding_mismatch','combined_passed':None}
                raise ValueError('Session binding not confirmed')
            if summary.get('combined_passed') is True:
                state = 'matched'
                # A selfie-download failure cannot turn successful identity checks into failure.
                try:
                    photo = download(provider.get('capturedImage'))
                    result['selfie'] = 'data:' + photo['mime_type'] + ';base64,' + photo['image_base64']
                except Exception:
                    result['selfie_unavailable'] = True
            elif summary.get('combined_passed') is False:
                state = 'not_matched'
            elif summary.get('outcome') == 'capture_not_completed':
                state = 'pending' if count < 3 else 'unknown'
    except Exception:
        state = 'unknown'
    result.update(summary=summary, evidence=evidence)
    with auth_sessions.transaction(conn):
        auth_sessions.sql(conn, 'UPDATE "LivenessSession" SET state=?,protected_session=?,protected_result=?,next_fetch_at=?,updated_at=? WHERE id=? AND state=?',
            (state, protected_session, Protection().seal(result), stamp() if creating else (datetime.now(timezone.utc) + timedelta(minutes=1)).isoformat(), stamp(), r['id'], claimed))
    return True
