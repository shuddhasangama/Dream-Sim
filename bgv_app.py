"""Private queued verification. Provider calls run in a separate worker."""
import json
import os
import uuid
from datetime import datetime, timezone, date
from cryptography.fernet import Fernet
import auth_sessions
import db
from api_contract import ApiError
from signzy.client import Client, Config, OPERATIONS
from signzy.verification import binding, ingest

VERSION = 'signzy-checks-v1'
CONSENT = 'I consent to DhaShu sending the details for my selected check to Signzy and securely storing its response to verify my declarations.'
CHECKS = {'pan_simple': 'Name and date of birth', 'current_employer': 'Current employer',
          'individual_search': 'Court record review', 'uan_passbook': 'EPF passbook review'}

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
    rows = sorted(db.fetch_all(conn, 'BgvRequest', user_id=uid), key=lambda r:r['created_at'], reverse=True)
    latest = {}
    for row in rows:
        key = (row['operation'], row['environment'])
        if key not in latest:
            latest[key] = {'id': row['id'], 'operation': row['operation'], 'state': row['state'],
                'environment': row['environment'], 'updated_at': row['updated_at'],
                **json.loads(row['summary_json'])}
    return {'enabled': enabled, 'environment': environment, 'consent_version': VERSION,
            'consent_text': CONSENT, 'checks': CHECKS, 'results': list(latest.values()),
            'overall_approval': 'Separate BGV review required; these checks do not unlock matching.'}

def submit(conn, uid, body):
    cfg = config()
    try:
        rid = str(uuid.UUID(body['request_id']))
        operation = body['operation']
        if operation not in CHECKS or body.get('consent') is not True or body.get('consent_version') != VERSION:
            raise ValueError()
        values = OPERATIONS[operation].payload(body['inputs'])
        declared = binding(uid, body.get('declared', {}))['declared_fields']
        if operation == 'pan_simple':
            if not declared.get('name', '').strip() or not declared.get('dob'):
                raise ValueError()
            if date.fromisoformat(declared['dob']) > date.today():
                raise ValueError()
        if operation == 'current_employer' and not declared.get('employer', '').strip():
            raise ValueError()
        if len(json.dumps(body)) > 12000:
            raise ValueError()
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ApiError('validation_error', 'Check the required details and consent before submitting.') from None
    protection = Protection()
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
        if any(r['state'] in ('queued', 'processing', 'pending', 'outcome_unknown') for r in active):
            raise ApiError('check_in_progress', 'A check is already in progress or awaiting review. Do not resubmit.', 409)
        now = stamp()
        auth_sessions.sql(conn, 'INSERT INTO "BgvRequest" '
            '(id,user_id,operation,environment,state,protected_input,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?)',
            (rid, uid, operation, cfg.environment, 'queued', protection.seal(snapshot), now, now))

def work_one(conn):
    cfg = config(); protection = Protection()
    with auth_sessions.transaction(conn):
        if db._is_postgres_connection(conn):
            auth_sessions.sql(conn, 'LOCK TABLE "BgvRequest" IN SHARE ROW EXCLUSIVE MODE')
        rows = sorted(db.fetch_all(conn, 'BgvRequest', state='queued', environment=cfg.environment), key=lambda r:r['created_at'])
        if not rows:
            return False
        row = rows[0]
        auth_sessions.sql(conn, 'UPDATE "BgvRequest" SET state=?, updated_at=? WHERE id=?', ('processing', stamp(), row['id']))
    # Claim is committed before the external call. Interrupted attempts are never resent automatically.
    try:
        data = protection.open(row['protected_input'])
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
        public = {'fields': {}, 'message': 'Results require review.'}
        # Persist raw evidence before comparison so a comparison failure never loses a paid result.
        with auth_sessions.transaction(conn):
            auth_sessions.sql(conn, 'UPDATE "BgvRequest" SET protected_result=? WHERE id=?', (protection.seal(item), row['id']))
        if row['operation'] in ('pan_simple', 'current_employer') and state == 'needs_review':
            status = ingest(conn, item, protection)
            saved = db.fetch_one(conn, 'BgvEvidence', id=item['receipt_id'])
            public['fields'] = json.loads(saved['fields_json'])
            state = status if status in ('verified', 'partially_verified') else 'needs_review'
        public['message'] = {'verified': 'Selected fields match.', 'partially_verified': 'Some fields match; review the remaining details.',
            'unavailable': 'Check unavailable. Support needs to review provider access or availability.',
            'outcome_unknown': 'Confirmation pending. Please do not submit again.',
            'pending': 'The provider is still processing this check.'}.get(state, 'Review your declared details; this result needs review.')
        with auth_sessions.transaction(conn):
            auth_sessions.sql(conn, 'UPDATE "BgvRequest" SET state=?,summary_json=?,updated_at=? WHERE id=?',
                (state, json.dumps(public), stamp(), row['id']))
    except Exception:
        with auth_sessions.transaction(conn):
            auth_sessions.sql(conn, 'UPDATE "BgvRequest" SET state=?,summary_json=?,updated_at=? WHERE id=?',
                ('outcome_unknown', json.dumps({'message':'Support review needed. Please do not resubmit.'}), stamp(), row['id']))
    return True
