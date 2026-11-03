"""Private queued verification. Provider calls run in a separate worker."""
import json
import os
import uuid
from datetime import datetime, timezone, timedelta
from cryptography.fernet import Fernet
import auth_sessions
import db
import bgv_policy
from api_contract import ApiError
from signzy.client import Client, Config, OPERATIONS
from signzy.verification import binding, ingest

VERSION = 'signzy-checks-v1'
CONSENT = 'I consent to DhaShu sending the details for my selected check to Signzy and securely storing its response to verify my declarations.'
CHECKS = {'current_employer': 'Current employer',
          'individual_search': 'Criminal court screening', 'fir_search': 'FIR screening'}
RESULTS = {'individual_search':'individual_result', 'fir_search':'fir_result'}
RESULT_LABELS = {'individual_result':'Criminal court result', 'fir_result':'FIR result'}

def stamp():
    return datetime.now(timezone.utc).isoformat()

class Protection:
    mode = 'fernet'
    def __init__(self):
        self.cipher = Fernet(os.environ['SIGNZY_RECEIPT_ENCRYPTION_KEY'].encode())
    def encrypt(self, raw):
        return self.cipher.encrypt(raw)
    def seal(self, data):
        return self.encrypt(json.dumps(data).encode()).decode()
    def open(self, data):
        return json.loads(self.cipher.decrypt(data.encode()))

def config():
    if os.getenv('DHASHU_BGV_APP_ENABLED') != '1':
        raise ApiError('verification_unavailable', 'Verification checks are not enabled yet.', 503)
    try:
        cfg = Config.from_env()
        cfg.validate()
        Protection()
        return cfg
    except (ValueError, KeyError):
        raise ApiError('verification_unavailable', 'Verification configuration needs attention.', 503) from None

def view(conn, uid):
    try:
        cfg = config(); enabled = True; environment = cfg.environment
    except ApiError:
        enabled = False; environment = None
    available_checks=dict(CHECKS)
    if enabled and os.getenv('DHASHU_BGV_POLICY_ENABLED')=='1':
        available_checks={}
        for operation,key in [('current_employer','current_employer'),('individual_search','criminal_court'),('fir_search','fir')]:
            try:
                bgv_policy.check_for(conn,uid,key,environment)
                available_checks[operation]=CHECKS[operation]
            except ApiError:
                pass
        enabled=bool(available_checks)
    rows = sorted(db.fetch_all(conn, 'BgvRequest', user_id=uid), key=lambda r:r['created_at'], reverse=True)
    latest = {}
    for row in rows:
        if row['operation']=='digilocker_details':continue
        key = (row['operation'], row['environment'])
        if key not in latest:
            latest[key] = {'id': row['id'], 'operation': row['operation'], 'state': row['state'],
                'environment': row['environment'], 'updated_at': row['updated_at'],
                **json.loads(row['summary_json'])}
            item = latest[key]
            children = [r for r in rows if r.get('parent_request_id') == row['id']]
            last_child = children[0] if children else None
            item['can_fetch_result'] = bool(row['operation'] in RESULTS and
                row['state'] == 'result_available' and not last_child)
            item['can_check_again'] = bool(row['operation'] in RESULTS.values() and row['state']=='pending'
                and datetime.now(timezone.utc)-datetime.fromisoformat(row['updated_at']) >= timedelta(seconds=60))
    return {'enabled': enabled, 'environment': environment, 'consent_version': VERSION,
            'consent_text': CONSENT, 'checks': available_checks, 'result_labels':RESULT_LABELS, 'results': list(latest.values()),
            'bundle': __import__('bgv_bundle').view(conn,uid),
            'overall_approval': 'Separate BGV review required; these checks do not unlock matching.'}

def submit(conn, uid, body):
    cfg = config()
    try:
        rid = str(uuid.UUID(body['request_id']))
        operation = body['operation']
        if operation not in CHECKS or body.get('consent') is not True or body.get('consent_version') != VERSION:
            raise ValueError()
        values = OPERATIONS[operation].payload(body['inputs'])
        if operation == 'individual_search':
            if values.get('caseCategory') != 'criminal' or values.get('matchType') != 'possible':
                raise ValueError('Phase 1 requires explicit criminal possible matching')
        declared = binding(uid, body.get('declared', {}))['declared_fields']
        if operation == 'current_employer' and not declared.get('employer', '').strip():
            raise ValueError()
        if len(json.dumps(body)) > 12000:
            raise ValueError()
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ApiError('validation_error', 'Check the required details and consent before submitting.') from None
    protection = Protection()
    key={'current_employer':'current_employer','individual_search':'criminal_court','fir_search':'fir'}[operation]
    case_check_id=bgv_policy.check_for(conn,uid,key,cfg.environment)
    snapshot = {'inputs': values, 'declared': declared, 'consent': {'version': VERSION,
                'text': CONSENT, 'accepted_at': stamp(), 'user_id': uid, 'operation': operation}}
    with auth_sessions.transaction(conn):
        if db._is_postgres_connection(conn):
            auth_sessions.sql(conn, 'LOCK TABLE "BgvRequest" IN SHARE ROW EXCLUSIVE MODE')
        previous = db.fetch_one(conn, 'BgvRequest', id=rid)
        if previous:
            if previous['user_id'] != uid:
                raise ApiError('request_conflict', 'Use a new request reference.', 409)
            old = protection.open(previous['protected_input'])
            if previous['operation'] != operation or old['inputs'] != values or old['declared'] != declared:
                raise ApiError('request_conflict', 'This request reference has already been used.', 409)
            return
        active = db.fetch_all(conn, 'BgvRequest', user_id=uid, operation=operation, environment=cfg.environment)
        if any(r['state'] in ('queued', 'processing', 'pending', 'outcome_unknown','result_available') for r in active):
            raise ApiError('check_in_progress', 'A check is already in progress or awaiting review. Do not resubmit.', 409)
        now = stamp()
        auth_sessions.sql(conn, 'INSERT INTO "BgvRequest" '
            '(id,user_id,operation,environment,state,protected_input,created_at,updated_at,case_check_id) VALUES (?,?,?,?,?,?,?,?,?)',
            (rid, uid, operation, cfg.environment, 'queued', protection.seal(snapshot), now, now,case_check_id))

def fetch_result(conn, uid, source_id, request_id):
    """Queue one linked lookup. Never accept a provider ID from the app."""
    cfg = config(); protection = Protection()
    try:
        rid = str(uuid.UUID(request_id))
    except (ValueError, TypeError, AttributeError):
        raise ApiError('validation_error', 'Use a valid request reference.') from None
    with auth_sessions.transaction(conn):
        if db._is_postgres_connection(conn):
            auth_sessions.sql(conn, 'LOCK TABLE "BgvRequest" IN SHARE ROW EXCLUSIVE MODE')
        source = db.fetch_one(conn,'BgvRequest',id=source_id,user_id=uid)
        if not source or source['environment'] != cfg.environment:
            raise ApiError('not_found','Search request not found.',404)
        prior = db.fetch_one(conn,'BgvRequest',id=rid)
        if prior:
            if prior['user_id'] != uid or prior.get('parent_request_id') != source_id:
                raise ApiError('request_conflict','Use a new request reference.',409)
            return
        if source['operation'] not in RESULTS or source['state'] != 'result_available':
            raise ApiError('result_unavailable','This search has no confirmed result identifier. Refresh or contact support.',409)
        if db.fetch_all(conn,'BgvRequest',parent_request_id=source_id):
            raise ApiError('result_exists','The result lookup already exists. Refresh its status.',409)
        evidence = protection.open(source['protected_result'])
        provider = evidence.get('provider_response') or {}
        if provider.get('http_status') not in (200,202):
            raise ApiError('result_unavailable','The search did not succeed.',409)
        body = provider.get('json')
        from signzy.fir_search import result_identifier
        operation = RESULTS[source['operation']]
        try:
            inputs = ({'caseId':body.get('caseId')} if operation=='individual_result' else
                      {'verifyId':result_identifier(body)})
            inputs = OPERATIONS[operation].payload(inputs)
        except (ValueError, AttributeError):
            raise ApiError('contract_review','The provider identifier requires support review.',409) from None
        snapshot = protection.open(source['protected_input'])
        snapshot = {**snapshot,'inputs':inputs,'source_request_id':source_id}
        stamp_now = stamp()
        auth_sessions.sql(conn,'INSERT INTO "BgvRequest" (id,user_id,operation,environment,state,protected_input,created_at,updated_at,parent_request_id,case_check_id) VALUES (?,?,?,?,?,?,?,?,?,?)',
            (rid,uid,operation,cfg.environment,'queued',protection.seal(snapshot),stamp_now,stamp_now,source_id,source.get('case_check_id')))

def check_again(conn, uid, rid):
    cfg=config()
    with auth_sessions.transaction(conn):
        row=db.fetch_one(conn,'BgvRequest',id=rid,user_id=uid)
        if not row or row['environment'] != cfg.environment:
            raise ApiError('not_found','Result request not found.',404)
        if row['operation'] not in RESULTS.values() or row['state'] != 'pending':
            raise ApiError('not_pending','Only a provider-confirmed pending result can be checked again.',409)
        if datetime.now(timezone.utc)-datetime.fromisoformat(row['updated_at']) < timedelta(seconds=60) or row.get('poll_count',0)>=5:
            raise ApiError('rate_limited','Wait before checking again, or contact support.',429)
        # CAS protects simultaneous refreshes on PostgreSQL.
        changed=auth_sessions.sql(conn,'UPDATE "BgvRequest" SET state=?,updated_at=?,poll_count=poll_count+1 WHERE id=? AND state=?',
            ('queued',stamp(),rid,'pending'))
        if changed.rowcount != 1:
            raise ApiError('request_conflict','A result lookup is already queued.',409)

def work_one(conn):
    cfg = config(); protection = Protection()
    with auth_sessions.transaction(conn):
        if db._is_postgres_connection(conn):
            auth_sessions.sql(conn, 'LOCK TABLE "BgvRequest" IN SHARE ROW EXCLUSIVE MODE')
        rows = sorted((r for r in db.fetch_all(conn, 'BgvRequest', state='queued', environment=cfg.environment)
                       if r['operation'] in {*CHECKS,*RESULTS.values(),'digilocker_details'}), key=lambda r:r['created_at'])
        if not rows:
            return False
        row = rows[0]
        auth_sessions.sql(conn, 'UPDATE "BgvRequest" SET state=?, updated_at=? WHERE id=?', ('processing', stamp(), row['id']))
    # Claim is committed before the external call. Interrupted attempts are never resent automatically.
    try:
        data = protection.open(row['protected_input'])
        if row['operation']=='individual_search' and (data['inputs'].get('caseCategory')!='criminal' or data['inputs'].get('matchType')!='possible'):
            with auth_sessions.transaction(conn):
                auth_sessions.sql(conn,'UPDATE "BgvRequest" SET state=?,summary_json=?,updated_at=? WHERE id=?',
                    ('unavailable',json.dumps({'message':'This queued search is outside the current criminal-only scope. Support review required.'}),stamp(),row['id']))
            return True
        if os.getenv('DHASHU_BGV_POLICY_ENABLED')=='1':
            key={'current_employer':'current_employer','individual_search':'criminal_court','individual_result':'criminal_court','fir_search':'fir','fir_result':'fir','digilocker_details':'identity_details'}[row['operation']]
            try:
                allowed=bgv_policy.check_for(conn,row['user_id'],key,cfg.environment)
                if allowed != row.get('case_check_id'):
                    raise ApiError('case_mismatch','Queued check does not belong to the active plan.',409)
            except ApiError:
                with auth_sessions.transaction(conn):
                    auth_sessions.sql(conn,'UPDATE "BgvRequest" SET state=?,summary_json=?,updated_at=? WHERE id=?',
                        ('unavailable',json.dumps({'message':'The assigned plan or provider is not enabled. Support review required.'}),stamp(),row['id']))
                return True
        evidence = []
        summary = Client(cfg).execute(row['operation'], data['inputs'], consent_confirmed=True, evidence_sink=evidence.append)
        item = evidence[0]
        item['binding'] = binding(row['user_id'], data['declared'])
        item['consent'] = data['consent']
        state = 'needs_review'
        if summary.get('error_code') or summary.get('http_status') not in (200, 202):
            state = 'unavailable'
        if summary.get('outcome') == 'transport_error_outcome_unknown':
            state = 'outcome_unknown'
        elif summary.get('http_status') == 202:
            state = 'pending'
        if row['operation'] in RESULTS and summary.get('http_status') in (200,202) and not summary.get('error_code'):
            try:
                body = (item.get('provider_response') or {}).get('json')
                if row['operation'] == 'fir_search':
                    from signzy.fir_search import result_identifier
                    result_identifier(body)
                else:
                    OPERATIONS['individual_result'].payload({'caseId':body.get('caseId')})
                state = 'result_available'
            except (ValueError, AttributeError):
                state = 'needs_review'
        if row['operation'] in RESULTS.values() and summary.get('outcome') == 'accepted_pending_confirmation':
            state = 'pending'
        public = {'fields': {}, 'message': 'Results require review.'}
        # Persist raw evidence before comparison so a comparison failure never loses a paid result.
        with auth_sessions.transaction(conn):
            auth_sessions.sql(conn,'INSERT INTO "BgvAttempt" (id,request_id,protected_evidence,created_at) VALUES (?,?,?,?)',
                (item['receipt_id'],row['id'],protection.seal(item),stamp()))
            auth_sessions.sql(conn, 'UPDATE "BgvRequest" SET protected_result=? WHERE id=?', (protection.seal(item), row['id']))
        if row['operation'] == 'current_employer' and state == 'needs_review':
            status = ingest(conn, item, protection)
            saved = db.fetch_one(conn, 'BgvEvidence', id=item['receipt_id'])
            public['fields'] = json.loads(saved['fields_json'])
            state = status if status in ('verified', 'partially_verified') else 'needs_review'
        public['message'] = {'verified': 'Selected fields match.', 'partially_verified': 'Some fields match; review the remaining details.',
            'unavailable': 'Check unavailable. Support needs to review provider access or availability.',
            'outcome_unknown': 'Confirmation pending. Please do not submit again.',
            'pending': 'The provider is still processing this check.'}.get(state, 'Review your declared details; this result needs review.')
        if state == 'result_available':
            public['message'] = 'Search accepted. Retrieve the linked result when ready.'
        with auth_sessions.transaction(conn):
            auth_sessions.sql(conn, 'UPDATE "BgvRequest" SET state=?,summary_json=?,updated_at=? WHERE id=?',
                (state, json.dumps(public), stamp(), row['id']))
    except Exception:
        with auth_sessions.transaction(conn):
            auth_sessions.sql(conn, 'UPDATE "BgvRequest" SET state=?,summary_json=?,updated_at=? WHERE id=?',
                ('outcome_unknown', json.dumps({'message':'Support review needed. Please do not resubmit.'}), stamp(), row['id']))
    return True
