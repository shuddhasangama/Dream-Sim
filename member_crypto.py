"""Field-level encryption for member data (sec-enc).

Encrypted fields (free text and photos only; fixed-vocabulary values that the
deterministic logic reads stay plain):

    Account.phone                       + Account.phone_index (HMAC blind index)
    ProfilePhoto.data_url               profile photo
    DateOutcome.a_reason / b_reason     Debrief reasons
    Exit.feedback_a_raw / _b_raw        exit feedback
    GateResponse.answer_text            gate answers
    NextLevelThread.answer_a / _b       next-level answers

Settings:
    DHASHU_FIELD_ENCRYPTION=1           encrypt on write (default 0: writes stay plain)
    DHASHU_DATA_ENCRYPTION_KEY          Fernet key (+ _ID / _PREVIOUS, see crypto_keys)
    DHASHU_BLIND_INDEX_KEY              HMAC key (>= 32 chars) for phone_index; set it
                                        before turning encryption on

Reads ALWAYS accept both plain and encrypted values, so turning encryption on,
off, or migrating existing rows (tools/encrypt_member_fields.py) never breaks a
read. Encrypted values carry the prefix 'enc1:'. db.insert_row seals and
db.fetch_all / fetch_one open these columns, so callers see plain values.
"""
import hashlib
import hmac
import os

PREFIX = 'enc1:'
KEY = 'DHASHU_DATA_ENCRYPTION_KEY'

FIELDS = {
    'Account': ('phone',),
    'ProfilePhoto': ('data_url',),
    'DateOutcome': ('a_reason', 'b_reason'),
    'Exit': ('feedback_a_raw', 'feedback_b_raw'),
    'GateResponse': ('answer_text',),
    'NextLevelThread': ('answer_a', 'answer_b'),
}
ENCRYPTED_COLUMNS = [(table, 'id', column) for table, columns in FIELDS.items() for column in columns]


class Unreadable(ValueError):
    """An encrypted value no configured key can open."""


def enabled():
    return os.environ.get('DHASHU_FIELD_ENCRYPTION', '0') == '1'


def _cipher():
    import crypto_keys
    return crypto_keys.cipher(KEY)


def is_sealed(value):
    return isinstance(value, str) and value.startswith(PREFIX)


def seal(value):
    """Encrypt when encryption is on; never double-encrypts; None stays None."""
    if not enabled() or not isinstance(value, str) or is_sealed(value):
        return value
    return PREFIX + _cipher().encrypt(value.encode('utf-8')).decode('ascii')


def force_seal(value):
    """Encrypt regardless of the switch (used by the batch migration)."""
    if not isinstance(value, str) or is_sealed(value):
        return value
    return PREFIX + _cipher().encrypt(value.encode('utf-8')).decode('ascii')


def open_value(value):
    if not is_sealed(value):
        return value
    from cryptography.fernet import InvalidToken
    try:
        return _cipher().decrypt(value[len(PREFIX):].encode('ascii')).decode('utf-8')
    except (InvalidToken, KeyError, ValueError):
        raise Unreadable('encrypted field cannot be opened with the configured keys') from None


def open_quiet(value, fallback=None):
    """For display-only readers (admin reports): never raises."""
    try:
        return open_value(value)
    except Unreadable:
        return fallback


def blind_index(phone):
    """HMAC of the canonical +E.164 phone, or None if no key / no phone."""
    secret = os.environ.get('DHASHU_BLIND_INDEX_KEY', '')
    if not phone or len(secret) < 32:
        return None
    import auth
    canonical = auth.normalize('phone', open_value(phone), stored=True)
    if not canonical:
        return None
    return hmac.new(secret.encode('utf-8'), canonical.encode('ascii'), hashlib.sha256).hexdigest()


def seal_row(table, row):
    columns = FIELDS.get(table)
    if not columns:
        return row
    out = dict(row)
    if table == 'Account' and 'phone' in out:
        out['phone_index'] = blind_index(out['phone'])
    if enabled():
        for column in columns:
            if column in out:
                out[column] = seal(out[column])
    return out


def open_row(table, row):
    columns = FIELDS.get(table)
    if not columns or not row:
        return row
    for column in columns:
        if is_sealed(row.get(column)):
            row[column] = open_value(row[column])
    return row
