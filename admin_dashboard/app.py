"""Dedicated admin HTTP application. No member/admin route sharing or public signup."""
import hmac
import os
import time
import uuid
from urllib.parse import urlsplit
from flask import Flask, g, jsonify, render_template, request
from werkzeug.exceptions import HTTPException
import auth_sessions
import db
from . import reports, security

SECTIONS = {'overview','users','sessions','checks','marketing','audit'}
PERMISSIONS = {'owner':SECTIONS,'support':{'overview','users','sessions','checks'},'marketing':{'marketing'}}

def create_app():
    app = Flask(__name__)
    app.config.update(MAX_CONTENT_LENGTH=8192)
    app.json.sort_keys=False
    origin = os.getenv('ADMIN_PUBLIC_ORIGIN','').rstrip('/')
    parsed = urlsplit(origin)
    local = os.getenv('ADMIN_ALLOW_HTTP')=='1' and parsed.hostname in ('127.0.0.1','localhost') and parsed.scheme=='http'
    if parsed.path or parsed.query or parsed.fragment or not parsed.netloc or (parsed.scheme!='https' and not local):
        raise ValueError('Set ADMIN_PUBLIC_ORIGIN to the exact HTTPS origin; HTTP is restricted to explicit localhost development.')
    security.protection()  # Fail closed when the independent MFA encryption key is missing/invalid.
    if not local and not os.getenv('DATABASE_URL','').startswith(('postgres://','postgresql://')):
        raise ValueError('Production admin requires an explicit PostgreSQL DATABASE_URL.')
    cookie = 'dhashu_admin_local' if local else '__Host-dhashu_admin'
    csrf_cookie = cookie+'_csrf'

    def get_db():
        if 'admin_db' not in g:
            g.admin_db=db.get_connection(os.getenv('ADMIN_LOCAL_DB_PATH',db.DEFAULT_DB_PATH))
        return g.admin_db

    @app.teardown_appcontext
    def close(_error):
        conn=g.pop('admin_db',None)
        if conn is not None: conn.close()

    @app.before_request
    def guard():
        if request.path=='/healthz': return None
        if request.host != parsed.netloc: return jsonify(error='Unrecognised dashboard host.'),400
        if not local and request.headers.get('X-Forwarded-Proto',request.scheme)!='https':
            return jsonify(error='HTTPS is required.'),400
        if request.method not in ('GET','HEAD','OPTIONS') and request.headers.get('Origin')!=origin:
            return jsonify(error='Request origin rejected.'),403
        if not request.path.startswith('/api/') or request.path=='/api/login': return None
        actor=security.resolve(get_db(),request.cookies.get(cookie))
        if not actor:return jsonify(error='Sign in with your admin account.',code='authentication_required'),401
        g.admin=actor
        if request.method not in ('GET','HEAD','OPTIONS'):
            value=request.headers.get('X-CSRF-Token','')
            if not value or not hmac.compare_digest(security.digest(value),actor['csrf_hash']):
                return jsonify(error='Refresh the page and try again.'),403
        with auth_sessions.transaction(get_db()):
            auth_sessions.sql(get_db(),'UPDATE "AdminSession" SET last_seen_at=? WHERE id=?',(int(time.time()),actor['id']))

    @app.after_request
    def headers(response):
        response.headers.update({'Cache-Control':'no-store','Pragma':'no-cache','X-Content-Type-Options':'nosniff',
            'X-Frame-Options':'DENY','Referrer-Policy':'no-referrer','X-Robots-Tag':'noindex, nofollow, noarchive',
            'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"})
        if not local:response.headers['Strict-Transport-Security']='max-age=31536000'
        return response

    @app.get('/healthz')
    def health():return jsonify(status='ok',service='dhashu-admin')

    @app.get('/')
    def index():return render_template('dashboard.html')

    @app.get('/robots.txt')
    def robots():return 'User-agent: *\nDisallow: /\n',200,{'Content-Type':'text/plain'}

    @app.post('/api/login')
    def login():
        data=request.get_json(silent=True) or {}
        if type(data) is not dict:return jsonify(error='Invalid request.'),400
        values,issue=security.login(get_db(),data.get('email',''),data.get('password',''),data.get('code',''),request.remote_addr or 'unknown')
        if issue:return jsonify(error='Please wait before trying again.' if issue=='throttled' else 'Sign-in details or authenticator code were not accepted.'),429 if issue=='throttled' else 401
        response=jsonify(ok=True)
        response.set_cookie(cookie,values['token'],max_age=8*3600,secure=not local,httponly=True,samesite='Strict',path='/')
        response.set_cookie(csrf_cookie,values['csrf'],max_age=8*3600,secure=not local,httponly=False,samesite='Strict',path='/')
        return response

    @app.get('/api/session')
    def session():return jsonify(email=g.admin['email'],role=g.admin['role'],sections=sorted(PERMISSIONS.get(g.admin['role'],set())),csrf=request.cookies.get(csrf_cookie,''),expires_at=g.admin['expires_at'],demo=local and os.getenv('ADMIN_LOCAL_DEMO')=='1')

    @app.post('/api/logout')
    def logout():
        with auth_sessions.transaction(get_db()):
            auth_sessions.sql(get_db(),'UPDATE "AdminSession" SET revoked_at=? WHERE id=?',(int(time.time()),g.admin['id']))
            security.audit(get_db(),g.admin['admin_id'],'logout')
        response=jsonify(ok=True)
        for name in (cookie,csrf_cookie):response.delete_cookie(name,path='/',secure=not local,httponly=name==cookie,samesite='Strict')
        return response

    @app.get('/api/reports/<section>')
    def report(section):
        if section not in PERMISSIONS.get(g.admin['role'],set()):return jsonify(error='This section is not available for your role.'),403
        try: page=int(request.args.get('page','1'))
        except ValueError:return jsonify(error='Invalid page.'),400
        if not 1<=page<=10000:return jsonify(error='Invalid page.'),400
        with auth_sessions.transaction(get_db()):security.audit(get_db(),g.admin['admin_id'],'report_view',section)
        with reports.connection() as conn:
            if section=='users':
                if request.args.get('q'):return jsonify(error='Use the private search form.'),400
                value=reports.users(conn,'',page)
            elif section=='sessions':value=reports.sessions(conn,page)
            else:value={'overview':reports.overview,'checks':reports.checks,'marketing':reports.marketing,'audit':reports.audit_log}[section](conn)
        return jsonify({**value,'generated_at':int(time.time()),'timezone':'Asia/Kolkata'})

    @app.post('/api/search/users')
    def search_users():
        if 'users' not in PERMISSIONS.get(g.admin['role'],set()):return jsonify(error='This section is not available for your role.'),403
        body=request.get_json(silent=True) or {}
        if type(body) is not dict:return jsonify(error='Invalid search.'),400
        try:page=int(body.get('page',1))
        except (ValueError,TypeError):return jsonify(error='Invalid page.'),400
        if not 1<=page<=10000 or not isinstance(body.get('q',''),str):return jsonify(error='Invalid search.'),400
        with auth_sessions.transaction(get_db()):security.audit(get_db(),g.admin['admin_id'],'report_search','users')
        with reports.connection() as conn:value=reports.users(conn,body.get('q',''),page)
        return jsonify({**value,'generated_at':int(time.time()),'timezone':'Asia/Kolkata'})

    @app.post('/api/user-summary')
    def user_summary():
        if 'users' not in PERMISSIONS.get(g.admin['role'],set()):return jsonify(error='This section is not available for your role.'),403
        body=request.get_json(silent=True) or {}
        uid=body.get('user_id') if isinstance(body,dict) else None
        if not isinstance(uid,str) or not 1<=len(uid)<=128:return jsonify(error='Invalid account reference.'),400
        with auth_sessions.transaction(get_db()):security.audit(get_db(),g.admin['admin_id'],'user_summary_view','users')
        with reports.connection() as conn:value=reports.user_summary(conn,uid)
        if value is None:return jsonify(error='Account not found.'),404
        return jsonify({**value,'generated_at':int(time.time()),'timezone':'Asia/Kolkata'})

    @app.errorhandler(Exception)
    def error(_exception):
        if isinstance(_exception,HTTPException):return jsonify(error=_exception.name),_exception.code
        reference=uuid.uuid4().hex[:12]
        # No exception text, request values or provider/identity payloads in public responses/logs.
        app.logger.error('Admin request failed; reference=%s section=%s',reference,request.endpoint)
        return jsonify(error='Report unavailable. Check deployment/schema configuration.',reference=reference),500

    return app
