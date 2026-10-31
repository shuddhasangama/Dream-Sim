"""User-bound, append-only field evidence; never changes overall BGV approval."""
import base64
import json
import unicodedata
from datetime import date
import db
import auth_sessions
from .pan_simple import valid_result
from .receipts import read_private

def normalized(value):
    return ' '.join(unicodedata.normalize('NFKC', value).casefold().split())

def evaluate(evidence):
    declared = evidence['binding']['declared_fields']
    provider = evidence.get('provider_response') or {}
    body = provider.get('json') or {}
    fields = {}
    values = {}
    operation = evidence['operation']
    summary = evidence['wrapper_summary']
    success = provider.get('http_status') == 200 and not summary.get('error_code')
    if operation == 'pan_simple':
        # Fourth PAN character identifies holder type: P is an individual.
        individual = evidence['request']['input_fields']['panNumber'][3] == 'P'
        success = success and valid_result(body) and individual
        result = body.get('result', {}) if isinstance(body, dict) else {}
        result = result if isinstance(result, dict) else {}
        values = {'name': result.get('name'), 'dob': result.get('dob')}
    elif operation == 'current_employer':
        result = body.get('employmentSummary', {}) if isinstance(body, dict) else {}
        result = result if isinstance(result, dict) else {}
        recent = result.get('recent_employer_data') or {}
        values = {'employer': recent.get('establishment_name') if isinstance(recent, dict) else None}
        # Historical employment is not evidence of the declared current employer.
        success = success and summary.get('result_code') == 200 and result.get('is_employed') is True
    else:
        raise ValueError('This operation has no field comparison rules yet')
    for field, value in values.items():
        expected = declared.get(field)
        if not success:
            fields[field] = 'unverified' if operation == 'current_employer' and provider.get('http_status') == 200 else 'failed_to_verify'
        elif not expected or not isinstance(value, str) or not value.strip():
            fields[field] = 'unverified'
        else:
            fields[field] = 'verified' if normalized(expected) == normalized(value) else 'unverified'
    states = list(fields.values())
    status = ('verified' if states and all(s == 'verified' for s in states) else
              'partially_verified' if 'verified' in states else
              'failed_to_verify' if 'failed_to_verify' in states else 'unverified')
    return status, fields, values

def ingest(conn, evidence, store):
    binding = evidence.get('binding')
    if not isinstance(binding, dict) or not binding.get('user_id'):
        raise ValueError('Receipt is not bound to a user; no automatic account assignment allowed')
    uid = binding['user_id']
    if not db.fetch_one(conn, 'User', id=uid):
        raise ValueError('Unknown user')
    status, fields, values = evaluate(evidence)
    private = {'declared_fields': binding['declared_fields'], 'provider_fields': values,
               'evidence': evidence}
    protected = base64.b64encode(store.encrypt(json.dumps(private).encode())).decode()
    with auth_sessions.transaction(conn):
        existing = db.fetch_one(conn, 'BgvEvidence', id=evidence['receipt_id'])
        if existing:
            if existing['user_id'] != uid:
                raise ValueError('Receipt already assigned to another user')
            return existing['status']
        auth_sessions.sql(conn, 'INSERT INTO "BgvEvidence" '
            '(id,user_id,environment,operation,status,fields_json,protected_details,protection,received_at) '
            'VALUES (?,?,?,?,?,?,?,?,?)',
            (evidence['receipt_id'], uid, evidence['environment'], evidence['operation'], status,
             json.dumps(fields), protected, store.mode, evidence['finished_at_utc']))
    return status

def import_receipt(conn, path, store):
    return ingest(conn, read_private(path), store)

def binding(user_id, declared_fields):
    if set(declared_fields) - {'name', 'dob', 'employer'}:
        raise ValueError('Unsupported declared fields')
    if any(not isinstance(v, str) for v in declared_fields.values()):
        raise ValueError('Declared fields must be strings')
    if declared_fields.get('dob'):
        date.fromisoformat(declared_fields['dob'])
    return {'user_id': user_id, 'declared_fields': dict(declared_fields)}
