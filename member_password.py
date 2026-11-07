"""Member passwords. OTP-proven setup/reset; existing revocable session machinery."""
import os
import secrets
import re
import auth_delivery
import auth
import auth_sessions as sessions
import db
from flask import jsonify, request
from werkzeug.security import generate_password_hash, check_password_hash

# Equal-cost verification for unknown contacts; no contact enumeration.
DUMMY = generate_password_hash('not-a-member-password', method='scrypt')

def account_for(conn, identifier):
    channel = 'email' if isinstance(identifier,str) and '@' in identifier else 'phone'
    normalized = auth.normalize(channel, identifier)
    if not normalized:return None
    matches=[dict(a) for a in db.fetch_all(conn,'Account') if auth.normalize(channel,a.get(channel),stored=True)==normalized]
    if len(matches)!=1:return None
    a=matches[0]
    return a if a['auth_enabled'] and a['verified_'+channel] else None

def login(conn, identifier, password, kind="mobile"):
    contact=identifier if isinstance(identifier,str) else ''
    channel='email' if '@' in contact else 'phone'
    contact=auth.normalize(channel,contact) or contact.strip().lower()[:254]
    keys=[auth.key('password-ip:'+(request.remote_addr or 'unknown')),auth.key('password-contact:'+contact.strip().lower())]
    if not sessions.throttle(conn,keys,10,900):return None,auth.failure('Please wait 15 minutes before trying again.',429,'rate_limited')
    a=account_for(conn,identifier)
    value=password if isinstance(password,str) and len(password)<=128 else ''
    valid=check_password_hash((a or {}).get('password_hash') or DUMMY,value)
    if not a or not a.get('password_hash') or not valid:return None,auth.failure('Phone/email or password was not accepted. Use a code to set or reset your password.',400,'invalid_credentials')
    # Recheck under the same lock used by password reset to prevent old-password races.
    with sessions.transaction(conn):
        suffix=' FOR UPDATE' if db._is_postgres_connection(conn) else ''
        current=sessions.sql(conn,'SELECT * FROM "Account" WHERE id=?'+suffix,(a['id'],)).fetchone()
        if not current or not current['auth_enabled'] or current['password_hash']!=a['password_hash'] or not current['verified_'+channel] or auth.normalize(channel,current[channel],stored=True)!=contact:
            return None,auth.failure('Phone/email or password was not accepted.',400,'invalid_credentials')
        return sessions.issue_in_transaction(conn,a['user_id'],kind),None

def register(app,get_db,payload):
    @app.post('/api/v1/auth/password/login')
    def password_login():
        body,error=payload(('identifier','password'))
        if error:return error
        result,error=login(get_db(),body['identifier'],body['password'])
        return error if error else jsonify(result)

    @app.get('/api/v1/auth/password/status')
    def password_status():
        if request.headers.get('Authorization') is None:return auth.failure('A bearer token is required.',401,'authentication_required')
        active=auth.resolve(get_db)
        if not active:return auth.failure('Sign in to continue.',401,'authentication_required')
        a=db.fetch_one(get_db(),'Account',user_id=active['user_id'])
        grant=sessions.sql(get_db(),'SELECT * FROM "PasswordGrant" WHERE session_id=?',(active['id'],)).fetchone()
        return jsonify(password_set=bool(a['password_hash']),can_set=bool(grant and grant['consumed_at'] is None and grant['expires_at']>sessions.now()),email_setup_enabled=os.getenv('DHASHU_EMAIL_LOGIN_ENABLED')=='1',verified_email=bool(a['verified_email']),phone=auth.normalize('phone',a['phone'],stored=True))

    @app.post('/api/v1/auth/password/set')
    def password_set():
        body,error=payload(('password',))
        if error:return error
        if request.headers.get('Authorization') is None:return auth.failure('A bearer token is required.',401,'authentication_required')
        active=auth.resolve(get_db)
        if not active:return auth.failure('Sign in to continue.',401,'authentication_required')
        password=body['password']
        if not isinstance(password,str) or not 15<=len(password)<=128:return auth.failure('Use a password of 15 to 128 characters.')
        conn=get_db()
        if not sessions.throttle(conn,[auth.key('password-set:'+active['user_id'])],5,900):return auth.failure('Please wait before trying again.',429,'rate_limited')
        hashed=generate_password_hash(password,method='scrypt')
        with sessions.transaction(conn):
            suffix=' FOR UPDATE' if db._is_postgres_connection(conn) else ''
            a=sessions.sql(conn,'SELECT * FROM "Account" WHERE user_id=?'+suffix,(active['user_id'],)).fetchone()
            if not a or not a['auth_enabled']:return auth.failure('Sign in again.',401,'authentication_required')
            live=sessions.sql(conn,'SELECT id FROM "AuthSession" WHERE id=? AND revoked_at IS NULL AND access_expires_at>?',(active['id'],sessions.now())).fetchone()
            if not live:return auth.failure('Sign in again.',401,'authentication_required')
            grant=sessions.sql(conn,'UPDATE "PasswordGrant" SET consumed_at=? WHERE session_id=? AND consumed_at IS NULL AND expires_at>? RETURNING session_id',(sessions.now(),active['id'],sessions.now())).fetchone()
            if not grant:return auth.failure('Verify a fresh phone/email code before setting or resetting your password.',403,'otp_required')
            sessions.sql(conn,'UPDATE "Account" SET password_hash=? WHERE id=?',(hashed,a['id']))
            sessions.sql(conn,'UPDATE "AuthSession" SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL',(sessions.now(),a['user_id']))
            result=sessions.issue_in_transaction(conn,a['user_id'])
        return jsonify(result)

    @app.post('/api/v1/auth/email/request')
    def email_request():
        if os.getenv('DHASHU_EMAIL_LOGIN_ENABLED')!='1':return auth.failure('Email setup is not enabled yet.',403,'email_unavailable')
        body,error=payload(('email','password'))
        if error:return error
        if request.headers.get('Authorization') is None:return auth.failure('A bearer token is required.',401,'authentication_required')
        active=auth.resolve(get_db)
        if not active:return auth.failure('Sign in to continue.',401,'authentication_required')
        conn=get_db();destination=auth.normalize('email',body['email'])
        if not destination:return auth.failure('Enter a valid email address.')
        if not sessions.throttle(conn,[auth.key('link-email:'+active['user_id']),auth.key('link-email-ip:'+(request.remote_addr or 'unknown'))],3,900):return auth.failure('Please wait before trying again.',429,'rate_limited')
        a=db.fetch_one(conn,'Account',user_id=active['user_id'])
        password=body['password']
        if not isinstance(password,str) or len(password)>128 or not a['password_hash'] or not check_password_hash(a['password_hash'],password):return auth.failure('Your current password was not accepted.')
        if any(auth.normalize('email',r['email'],stored=True)==destination and r['id']!=a['id'] for r in db.fetch_all(conn,'Account')):return auth.failure('This email cannot be added. Use another email.')
        try:sid=auth_delivery.start('email',destination)
        except auth_delivery.DeliveryUnavailable:return auth.failure('Email delivery is unavailable. Your login details have not changed.',503,'email_unavailable')
        token=secrets.token_urlsafe(32)
        with sessions.transaction(conn):
            sessions.sql(conn,'UPDATE "MemberEmailChallenge" SET consumed_at=? WHERE session_id=? AND consumed_at IS NULL',(sessions.now(),active['id']))
            sessions.sql(conn,'INSERT INTO "MemberEmailChallenge" (id,session_id,destination,provider_sid,expires_at) VALUES (?,?,?,?,?)',(sessions.digest(token),active['id'],destination,sid,sessions.now()+600))
        return jsonify(challenge_id=token)

    @app.post('/api/v1/auth/email/verify')
    def email_verify():
        body,error=payload(('challenge_id','code'))
        if error:return error
        if request.headers.get('Authorization') is None:return auth.failure('A bearer token is required.',401,'authentication_required')
        active=auth.resolve(get_db)
        if not active:return auth.failure('Sign in to continue.',401,'authentication_required')
        if not sessions.valid_token(body['challenge_id']) or not isinstance(body['code'],str) or not re.fullmatch('[0-9]{4,10}',body['code']):return auth.failure('Enter a valid code.')
        conn=get_db()
        with sessions.transaction(conn):
            row=sessions.sql(conn,'UPDATE "MemberEmailChallenge" SET attempts=attempts+1 WHERE id=? AND session_id=? AND attempts<5 AND consumed_at IS NULL AND expires_at>? RETURNING *',(sessions.digest(body['challenge_id']),active['id'],sessions.now())).fetchone()
        if not row:return auth.failure('Code invalid or expired.')
        try:approved=auth_delivery.check(row['provider_sid'],body['code'])
        except auth_delivery.DeliveryUnavailable:approved=False
        if not approved:return auth.failure('Code invalid or expired.')
        with sessions.transaction(conn):
            if db._is_postgres_connection(conn):sessions.sql(conn,'LOCK TABLE "Account" IN SHARE ROW EXCLUSIVE MODE')
            # Recheck the member session after the external call (password reset revokes it).
            live=sessions.sql(conn,'SELECT * FROM "AuthSession" WHERE id=? AND revoked_at IS NULL AND access_expires_at>?',(active['id'],sessions.now())).fetchone()
            if not live:return auth.failure('Sign in again.',401,'authentication_required')
            taken=any(auth.normalize('email',a['email'],stored=True)==row['destination'] and a['user_id']!=active['user_id'] for a in db.fetch_all(conn,'Account'))
            if taken:return auth.failure('This email cannot be added.')
            redeemed=sessions.sql(conn,'UPDATE "MemberEmailChallenge" SET consumed_at=? WHERE id=? AND consumed_at IS NULL AND expires_at>? RETURNING id',(sessions.now(),row['id'],sessions.now())).fetchone()
            if not redeemed:return auth.failure('Code invalid or expired.')
            sessions.sql(conn,'UPDATE "Account" SET email=?,verified_email=1 WHERE user_id=? AND auth_enabled=1',(row['destination'],active['user_id']))
        return jsonify(verified=True)
