"""Encryption keys with rotation (sec-keys).

Every encryption setting keeps its existing variable, which holds the CURRENT
key (the one that encrypts):

    WAITLIST_ENCRYPTION_KEY=<fernet key>               current key
    WAITLIST_ENCRYPTION_KEY_ID=k2                      its id (optional, default "current")
    WAITLIST_ENCRYPTION_KEY_PREVIOUS=k1:<key>,k0:<key>   older keys, decrypt only (optional)

Values encrypted under an older key keep working (MultiFernet tries the current
key first, then each previous key). tools/reencrypt_keys.py re-encrypts stored
values onto the current key (dry run by default); after it reports 0 values on
old keys, the previous keys can be removed. With only the current key set, the
behaviour is exactly the old single-key Fernet behaviour.

Key ids are names for people (reports, the backup document); Fernet tokens do
not carry them, so which() finds the key by trying each one.
"""
import os

from cryptography.fernet import Fernet, InvalidToken, MultiFernet


class MissingKey(KeyError, ValueError):
    """Raised when the current key is not set. A KeyError for callers that read
    os.environ[...] before, and a ValueError for callers that caught Fernet('')."""


def entries(name):
    """[(key_id, Fernet)] newest first. Raises MissingKey or ValueError."""
    current = os.environ.get(name, '').strip()
    if not current:
        raise MissingKey(name)
    found = [(os.environ.get(name + '_ID', '').strip() or 'current', Fernet(current.encode('ascii')))]
    for position, item in enumerate(v.strip() for v in os.environ.get(name + '_PREVIOUS', '').split(',')):
        if not item:
            continue
        key_id, _, key = item.rpartition(':') if ':' in item and len(item.split(':', 1)[0]) < 40 else ('', '', item)
        found.append((key_id or f'previous-{position + 1}', Fernet(key.encode('ascii'))))
    return found


def cipher(name):
    """A MultiFernet: encrypts with the current key, decrypts with any listed key."""
    try:
        return MultiFernet([fernet for _, fernet in entries(name)])
    except UnicodeError:
        raise ValueError(name + ' is not a valid key') from None


def which(name, token):
    """Id of the key that decrypts token, or None (tampered or unknown key)."""
    data = token.encode('ascii') if isinstance(token, str) else token
    for key_id, fernet in entries(name):
        try:
            fernet.decrypt(data)
            return key_id
        except InvalidToken:
            continue
    return None


def current_id(name):
    return entries(name)[0][0]
