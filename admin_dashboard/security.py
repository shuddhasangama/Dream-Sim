"""Independent password + RFC 6238 TOTP authentication and opaque admin sessions."""
import base64
import hashlib
import hmac
import os
import secrets
import struct
import time
import uuid
from cryptography.fernet import Fernet
from werkzeug.security import check_password_hash, generate_password_hash
import auth_sessions
import db

ROLES = {'owner', 'support', 'marketing'}
DUMMY_HASH = generate_password_hash(secrets.token_urlsafe(24))

def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()

def protection():
    return Fernet(os.environ['ADMIN_TOTP_ENCRYPTION_KEY'].encode())

def code(secret, counter):
    key = base64.b32decode(secret + '=' * (-len(secret) % 8))
    value = hmac.new(key, struct.pack('>Q', counter), hashlib.sha1).digest()
    offset = value[-1] & 15
    return str((struct.unpack('>I', value[offset:offset+4])[0] & 0x7fffffff) % 1000000).zfill(6)

def counter_for(secret, supplied, now=None):
    if not isinstance(supplied, str) or len(supplied) != 6 or not supplied.isascii() or not supplied.isdigit():
        return None
    counter = int(time.time() if now is None else now) // 30
    for candidate in (counter, counter-1, counter+1):
        if candidate >= 0 and hmac.compare_digest(code(secret, candidate), supplied):
            return candidate
    return None

def audit(conn, admin_id, action, section=None):
    conn.execute('INSERT INTO "AdminAudit" (id,admin_id,action,section,created_at) VALUES (' + ','.join([db._placeholder(conn)]*5) + ')',
                 (uuid.uuid4().hex, admin_id, action, section, int(time.time())))

def create_identity(conn, email, password, secret, supplied_code, role='owner'):
    email = email.strip().lower()
    if role not in ROLES or len(password) < 14 or '@' not in email:
        raise ValueError('Use a valid email, supported role and password of at least 14 characters.')
    counter = counter_for(secret, supplied_code)
    if counter is None:
        raise ValueError('Authenticator code did not match. No account was created.')
    with auth_sessions.transaction(conn):
        if auth_sessions.sql(conn, 'SELECT id FROM "AdminIdentity" WHERE email=?', (email,)).fetchone():
            raise ValueError('This admin already exists. Use the documented recovery procedure.')
        uid = uuid.uuid4().hex
        auth_sessions.sql(conn, 'INSERT INTO "AdminIdentity" (id,email,role,password_hash,protected_totp,last_totp_counter,created_at) VALUES (?,?,?,?,?,?,?)',
            (uid,email,role,generate_password_hash(password),protection().encrypt(secret.encode()).decode(),counter,int(time.time())))
        audit(conn, uid, 'identity_created', role)
    return uid

def login(conn, email, password, otp, ip):
    now = int(time.time()); email = str(email).strip().lower()
    # Durable throttles cover both email and network source across workers.
    keys = [digest('email:' + email), digest('network:' + ip)]
    with auth_sessions.transaction(conn):
        for key in keys:
            row = auth_sessions.sql(conn, 'SELECT * FROM "AdminThrottle" WHERE id=?', (key,)).fetchone()
            if row and row['expires_at'] > now and row['attempts'] >= 10:
                return None, 'throttled'
            auth_sessions.sql(conn, 'INSERT INTO "AdminThrottle" (id,attempts,expires_at) VALUES (?,1,?) ON CONFLICT (id) DO UPDATE SET attempts=CASE WHEN "AdminThrottle".expires_at<=? THEN 1 ELSE "AdminThrottle".attempts+1 END, expires_at=CASE WHEN "AdminThrottle".expires_at<=? THEN ? ELSE "AdminThrottle".expires_at END',
                (key,now+900,now,now,now+900))
        suffix = ' FOR UPDATE' if db._is_postgres_connection(conn) else ''
        row = auth_sessions.sql(conn, 'SELECT * FROM "AdminIdentity" WHERE email=?' + suffix, (email,)).fetchone()
        valid_password = check_password_hash(row['password_hash'] if row else DUMMY_HASH, str(password))
        counter = None
        if row and row['enabled'] and valid_password:
            secret = protection().decrypt(row['protected_totp'].encode()).decode()
            counter = counter_for(secret, otp, now)
        if counter is None or counter <= row['last_totp_counter']:
            audit(conn, row['id'] if row else None, 'login_failed')
            return None, 'invalid'
        auth_sessions.sql(conn, 'UPDATE "AdminIdentity" SET last_totp_counter=? WHERE id=?', (counter,row['id']))
        token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        auth_sessions.sql(conn, 'INSERT INTO "AdminSession" (id,admin_id,csrf_hash,created_at,last_seen_at,expires_at) VALUES (?,?,?,?,?,?)',
            (digest(token),row['id'],digest(csrf),now,now,now+8*3600))
        audit(conn, row['id'], 'login_succeeded')
        return {'token':token,'csrf':csrf}, None

def resolve(conn, token):
    if not isinstance(token,str) or not 32 <= len(token) <= 128:
        return None
    row = auth_sessions.sql(conn, 'SELECT s.*,a.email,a.role FROM "AdminSession" s JOIN "AdminIdentity" a ON a.id=s.admin_id WHERE s.id=? AND s.revoked_at IS NULL AND a.enabled=1 AND s.expires_at>? AND s.last_seen_at>?',
        (digest(token),int(time.time()),int(time.time())-1800)).fetchone()
    return dict(row) if row else None
