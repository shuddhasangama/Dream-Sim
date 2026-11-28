"""Store reviewer account (client answer 9, 2026-11-27).

Apple and Google reviewers cannot receive an SMS code, so ONE reviewer account signs in
with phone + password only (member_password.login: no OTP at sign-in) and is admitted
straight to the main screens (verified, Dating, signup complete) without DigiLocker,
liveness or payment.

Safety:
- Created or updated only by tools/create_reviewer_account.py with an explicit --apply.
  The phone and password are typed at run time and never stored in any file; the
  password is kept only as a scrypt hash, the phone as the app stores any phone
  (encrypted when field encryption is on, with its blind index).
- Never turns an existing member into a reviewer: a phone that belongs to a
  non-reviewer account is refused.
- A reviewer is never shown to, counted for or matched with any member
  (account_deletion.hidden_ids), and is never offered a real member in weekly
  matching (week_service.prepare), so no member's data reaches a store reviewer.
- No test switch is involved, so it works under prod_guard / security_config.
"""
from __future__ import annotations

import json
import uuid

from werkzeug.security import generate_password_hash

import auth_sessions as sessions
import db

USER_PREFIX = 'reviewer_'
MIN_PASSWORD, MAX_PASSWORD = 12, 128           # same rule as member_password
ACTIVITIES = ('Cooking', 'Hiking', 'Reading', 'Movies')   # catalogue items, onboarding.MIN_SORTED = 4


class ReviewerError(ValueError):
    """A refusal the tool shows as-is (never contains the phone or password)."""


def canonical_phone(value):
    import auth
    phone = auth.normalize('phone', value) if isinstance(value, str) else None
    if not phone:
        raise ReviewerError('Enter the phone number in full international form, for example +91 followed by 10 digits.')
    return phone


def check_password(password):
    if not isinstance(password, str) or not MIN_PASSWORD <= len(password) <= MAX_PASSWORD:
        raise ReviewerError(f'Use a password of {MIN_PASSWORD} to {MAX_PASSWORD} characters.')
    return password


def reviewer_ids(conn):
    return {r['user_id'] for r in sessions.sql(conn, 'SELECT user_id FROM "Account" WHERE reviewer = 1').fetchall()}


def is_reviewer(conn, uid):
    row = sessions.sql(conn, 'SELECT reviewer FROM "Account" WHERE user_id = ?', (uid,)).fetchone()
    return bool(row and row['reviewer'])


def _account_for_phone(conn, phone):
    import auth
    matches = [dict(a) for a in db.fetch_all(conn, 'Account') if auth.normalize('phone', a.get('phone'), stored=True) == phone]
    if len(matches) > 1:
        raise ReviewerError('More than one account uses this phone number. Resolve that first; nothing was changed.')
    return matches[0] if matches else None


def _profile(uid):
    stats = {'signup_version': 3, 'vision_schema_version': 2, 'vision_template': 'grow', 'kids_intent': 'want',
             'signup_stats_saved': True, 'signup_submitted': True, 'reviewer': True,
             'age': 30, 'declared_age': 30, 'gender': 'female', 'city': 'Bangalore',
             'diet': 'Vegetarian', 'cuisine': ['South Indian'], 'budget': ['₹₹ · 800 – 2,000']}
    vision = [{'key': 'Intimacy', 'stance': ['Emotional']}, {'key': 'Kids', 'stance': None},
              {'key': 'Cohabitate', 'stance': None}, {'key': 'Travel together', 'stance': None}]
    activities = {name: 'good' for name in ACTIVITIES}
    skills = {'activities': activities, 'by_bucket': {'good': list(ACTIVITIES)}, 'custom_activities': [], 'partner_any': []}
    return {'id': uid, 'journey_state': 'dating', 'bgv_status': 'verified', 'stats_json': json.dumps(stats),
            'vision_json': json.dumps(vision), 'skills_json': json.dumps(skills),
            'preferences_json': json.dumps({'fixed': {'dealbreakers': []}, 'adjustable': {'distance_km': [0, 30]}})}


def upsert(conn, phone, password):
    """Create or update THE reviewer account. Returns (user_id, 'created' | 'updated')."""
    phone = canonical_phone(phone)
    hashed = generate_password_hash(check_password(password), method='scrypt')
    import member_crypto
    with sessions.transaction(conn):
        existing = _account_for_phone(conn, phone)
        others = reviewer_ids(conn) - ({existing['user_id']} if existing else set())
        if others:
            raise ReviewerError('Another reviewer account already exists. Keep one reviewer account; nothing was changed.')
        if existing and not existing.get('reviewer'):
            raise ReviewerError('This phone number belongs to a member account. Use a dedicated reviewer number; nothing was changed.')
        now = sessions.now()
        if existing:
            uid, outcome = existing['user_id'], 'updated'
            db.lock_user_rows(conn, uid)
            sessions.sql(conn, 'UPDATE "Account" SET password_hash = ?, auth_enabled = 1, verified_phone = 1, reviewer = 1, '
                               'locked_at = NULL WHERE id = ?', (hashed, existing['id']))
            sessions.sql(conn, 'UPDATE "AuthSession" SET revoked_at = ? WHERE user_id = ? AND revoked_at IS NULL', (now, uid))
        else:
            uid, outcome = USER_PREFIX + uuid.uuid4().hex[:12], 'created'
            db.insert_row(conn, 'User', _profile(uid))
            db.insert_row(conn, 'Account', {'id': uuid.uuid4().hex, 'user_id': uid, 'phone': member_crypto.seal(phone),
                                            'phone_index': member_crypto.blind_index(phone), 'password_hash': hashed,
                                            'auth_enabled': 1, 'verified_phone': 1, 'verification_required': 0,
                                            'reviewer': 1, 'created_at': str(now)})
        if outcome == 'updated':
            row = db.fetch_one(conn, 'User', id=uid)
            if row is None or row['journey_state'] != 'dating' or row['bgv_status'] != 'verified':
                db.insert_row(conn, 'User', _profile(uid))
        sessions.record_security_event(conn, uid, 'reviewer_account_' + outcome, None)
    return uid, outcome
