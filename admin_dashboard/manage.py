"""Provision admin identities privately from the service console. No email is sent."""
import argparse
import base64
import getpass
import os
from pathlib import Path
import secrets
import time
from urllib.parse import quote
import auth_sessions
import db
from . import security

def initialize(conn):
    sql=Path(__file__).with_name('schema.sql').read_text(encoding='utf-8-sig')
    if db._is_postgres_connection(conn):
        for statement in sql.split(';'):
            if statement.strip():conn.execute(statement)
        conn.commit()
    else:conn.executescript(sql)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('action',choices=['init','create','reset','disable'])
    p.add_argument('--email',default='office@shuddhasangama.org')
    p.add_argument('--role',choices=sorted(security.ROLES),default='owner')
    p.add_argument('--apply',action='store_true')
    a=p.parse_args();conn=db.get_connection(os.getenv('ADMIN_LOCAL_DB_PATH',db.DEFAULT_DB_PATH))
    try:
        if a.action=='init':
            db.init_db(conn);initialize(conn);print('Schema ready. No profiles, sessions or verification results reset.');return
        if not a.apply:print('Dry run. Add --apply to provision or disable this administrator.');return
        if a.action=='disable':
            with auth_sessions.transaction(conn):
                row=auth_sessions.sql(conn,'SELECT id FROM "AdminIdentity" WHERE email=?',(a.email.lower(),)).fetchone()
                if not row:raise ValueError('Admin not found.')
                auth_sessions.sql(conn,'UPDATE "AdminIdentity" SET enabled=0 WHERE id=?',(row['id'],))
                auth_sessions.sql(conn,'UPDATE "AdminSession" SET revoked_at=? WHERE admin_id=?',(int(time.time()),row['id']))
                security.audit(conn,row['id'],'identity_disabled')
            print('Administrator disabled; sessions revoked.');return
        password=getpass.getpass('New admin password (at least 14 characters): ')
        if password!=getpass.getpass('Repeat password: '):raise ValueError('Passwords did not match.')
        if len(password)<14:raise ValueError('Use at least 14 characters.')
        secret=base64.b32encode(secrets.token_bytes(20)).decode().rstrip('=')
        print('PRIVATE: add a time-based account in your authenticator. Do not paste this secret into chat or logs.')
        print('Account:',a.email,'Issuer: DhaShu Admin','Setup key:',secret)
        print('Manual-entry uses six digits and a 30-second period.')
        otp=getpass.getpass('Current authenticator code (hidden): ').strip()
        if a.action=='reset':
            counter=security.counter_for(secret,otp)
            if counter is None:raise ValueError('Authenticator code did not match. No changes applied.')
            with auth_sessions.transaction(conn):
                row=auth_sessions.sql(conn,'SELECT id FROM "AdminIdentity" WHERE email=?',(a.email.lower(),)).fetchone()
                if not row:raise ValueError('Admin not found.')
                auth_sessions.sql(conn,'UPDATE "AdminIdentity" SET password_hash=?,protected_totp=?,last_totp_counter=?,enabled=1 WHERE id=?',
                    (security.generate_password_hash(password),security.protection().encrypt(secret.encode()).decode(),counter,row['id']))
                auth_sessions.sql(conn,'UPDATE "AdminSession" SET revoked_at=? WHERE admin_id=?',(int(time.time()),row['id']))
                security.audit(conn,row['id'],'credentials_reset')
        else:
            security.create_identity(conn,a.email,password,secret,otp,a.role)
        print('Administrator ready. Sign in with password and the NEXT authenticator code. No email was sent.')
    except ValueError as exc:p.exit(1,str(exc)+'\n')
    finally:conn.close()
if __name__=='__main__':main()
