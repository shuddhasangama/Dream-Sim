"""Operator-invited beta enrollment. No provider approval or identity minting API."""
import math
import uuid
import auth
import auth_sessions
import db
import onboarding as forms
import locale_defaults
from evolution_service import transaction
from planning_service import save
from api_contract import ApiError


def invite(conn, email=None, phone=None, apply=False):
    contacts = {}
    for key, value in (('email', email), ('phone', phone)):
        contacts[key] = auth.normalize(key, value, stored=True) if value else None
        if value and not contacts[key]:
            raise ValueError('Invalid '+key+'; include the phone country code.')
    if not any(contacts.values()):
        raise ValueError('A real tester-controlled contact is required.')
    with transaction(conn):
        if db._is_postgres_connection(conn):
            auth_sessions.sql(conn, 'LOCK TABLE "Account" IN SHARE ROW EXCLUSIVE MODE')
        for row in db.fetch_all(conn, 'Account'):
            if any(value and auth.normalize(key, row.get(key), stored=True) == value for key, value in contacts.items()):
                raise ValueError('Contact already belongs to an account; use existing account administration.')
        if not apply:
            return {'applied': False, 'message': 'Would reserve an invited onboarding profile; OTP still required.'}
        uid = forms.new_user_id()
        db.insert_row(conn, 'User', {'id': uid, 'journey_state': 'onboarding', 'bgv_status': 'declared'})
        db.insert_row(conn, 'Account', {'id': uuid.uuid4().hex, 'user_id': uid, **contacts,
            'auth_enabled': 1, 'verification_required': 1, 'created_at': str(auth_sessions.now())})
        db.insert_row(conn, 'EnrollmentDraft', {'id': uid, 'payload_json': '{}', 'revision': 0})
        return {'applied': True, 'user_id': uid, 'message': 'Reserved. Sign in with OTP to complete enrollment.'}


def owned(conn, uid):
    account = db.fetch_one(conn, 'Account', user_id=uid)
    if not account or not account['auth_enabled']:
        raise ApiError('enrollment_not_approved', 'Operator approval is required.', 403)
    return db.fetch_one(conn, 'EnrollmentDraft', id=uid), account


def state(conn, uid):
    row, account = owned(conn, uid)
    return {'mode': 'operator_invited_beta', 'status': ('submitted_for_review' if row['completed_at'] else 'draft') if row else 'existing_profile',
        'revision': row['revision'] if row else None, 'draft': db.load_json_field(row['payload_json'], {}) if row else None,
        'contact_verified': bool(account['verified_email'] or account['verified_phone']),
        'bgv_status': db.fetch_one(conn, 'User', id=uid)['bgv_status'],
        'verification_provider': 'manual_review_required', 'verification_granted': False,
        'public_signup_available': False}


def options():
    return {'vision': {key: list(values) for key, values in vision_options().items()},
        'stats_options': {k:v for k,v in forms.STAT_OPTIONS.items() if k != 'income_band'}, 'stats_ranges': forms.STAT_RANGES,
        'required_stats': forms.REQUIRED_STAT_KEYS, 'activities': forms.ACTIVITIES,
        'activity_buckets': sorted(forms.BUCKET_IDS), 'genders': forms.GENDERS_FOR_SIGNUP,
        'cities': forms.CITIES_FOR_SIGNUP,
        'salary_required': True, 'city_required': True}


def vision_options():
    # round3-fixes-spec.md §7.1: Travel together carries no sub-options
    # any more, so there is no travel_style array to submit.
    return {'intimacy_kinds': forms.INTIMACY_KINDS, 'other_keys': forms.OTHER_VISION_KEYS,
        'cohabit_focus': forms.COHABIT_FOCUS, 'kids_route': forms.KIDS_ROUTES}


def validate(section, body):
    if type(body) is not dict:
        raise ApiError('validation_error', 'Section must be a JSON object.')
    if section == 'vision':
        allowed = vision_options()
        if set(body) != set(allowed):
            raise ApiError('validation_error', 'Supply all four vision arrays.')
        for key, values in body.items():
            if type(values) is not list or any(type(v) is not str or v not in allowed[key] for v in values) or len(set(values)) != len(values):
                raise ApiError('validation_error', 'Invalid vision choices.')
        result = forms.validate_vision(**body)
    elif section == 'activities':
        if any(k not in forms.ACTIVITIES or type(v) is not str or v not in forms.BUCKET_IDS for k, v in body.items()):
            raise ApiError('validation_error', 'Invalid activity choices.')
        result = forms.validate_activities(body)
    elif section == 'stats':
        if set(body) - ((set(forms.STAT_LABELS) - {'income_band'}) | {'city', 'gender', 'salary'}):
            raise ApiError('validation_error', 'Unknown stats field.')
        if type(body.get('city')) is not str or not body['city'].strip() or len(body['city']) > 100 or body.get('gender') not in ('male', 'female'):
            raise ApiError('validation_error', 'Provide city and a supported gender.')
        numeric = {k for k, *_ in forms.NUMERIC_STATS + forms.OPTIONAL_NUMERIC_STATS} | {'salary'}
        for key, value in body.items():
            if key in numeric:
                if type(value) not in (int, float) or value <= 0 or value > 1e12 or not math.isfinite(value) or (key != 'salary' and value != int(value)):
                    raise ApiError('validation_error', 'Numeric stats must be finite positive numbers; measurements must be whole numbers.')
            elif key in forms.MULTI_VALUE_STATS:
                choices = locale_defaults.budget_bands_for(body['city']) if key == 'budget' else forms.STAT_OPTIONS.get(key, [])
                if type(value) is not list or any(type(v) is not str or v not in choices for v in value) or len(set(value)) != len(value):
                    raise ApiError('validation_error', 'Invalid multi-select stats.')
            elif type(value) is not str or len(value) > 500:
                raise ApiError('validation_error', 'Expected a bounded string.')
        result = forms.validate_stats(body)
    else:
        raise ApiError('not_found', 'Unknown enrollment section.', 404)
    if not result['ok']:
        raise ApiError('validation_error', result['error'])
    return body


def write(conn, uid, revision, section=None, body=None):
    if type(revision) is not int or revision < 0:
        raise ApiError('validation_error', 'revision must be a non-negative integer.')
    if section is not None:
        validate(section, body)
    with transaction(conn):
        if db._is_postgres_connection(conn):
            auth_sessions.sql(conn, 'LOCK TABLE "Account" IN SHARE ROW EXCLUSIVE MODE')
        row, account = owned(conn, uid)
        if not row:
            raise ApiError('enrollment_closed', 'Existing profiles use profile editing.', 409)
        if not (account['verified_email'] or account['verified_phone']):
            raise ApiError('contact_verification_required', 'Complete OTP sign-in first.', 403)
        draft = db.load_json_field(row['payload_json'], {})
        if row['completed_at']:
            if section is None:
                return state(conn, uid)
            raise ApiError('enrollment_closed', 'Enrollment has already been submitted.', 409)
        if section and draft.get(section) == body:
            return state(conn, uid)
        if revision != row['revision']:
            raise ApiError('stale_revision', 'Read the latest draft before changing it.', 409)
        if section:
            draft[section] = body
            row.update(payload_json=db.json_field(draft), revision=revision+1)
        else:
            if set(draft) != {'vision', 'stats', 'activities'}:
                raise ApiError('enrollment_incomplete', 'Complete all three sections first.', 409)
            for key, value in draft.items():
                validate(key, value)
            user = db.fetch_one(conn, 'User', id=uid)
            if user['journey_state'] != 'onboarding' or user['bgv_status'] != 'declared':
                raise ApiError('state_conflict', 'Profile has changed; enrollment cannot overwrite it.', 409)
            stats = forms.validate_stats(draft['stats'])['stats']
            built = forms.build_user_row(uid, draft['stats']['city'].strip(), draft['stats']['gender'], stats,
                forms.build_visions(**draft['vision']), draft['activities'])
            save(conn, 'User', {**user, **built, 'bgv_status': 'pending'})
            row.update(completed_at=str(auth_sessions.now()), revision=revision+1)
            # Do not persist exact salary after submission; only the derived band.
            draft['stats'].pop('salary', None)
            row['payload_json'] = db.json_field(draft)
        save(conn, 'EnrollmentDraft', row)
        return state(conn, uid)
