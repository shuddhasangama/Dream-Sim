"""Dedicated admin HTTP application. No member/admin route sharing or public signup."""
import client_ip
import hmac
import os
import time
import uuid
from urllib.parse import urlsplit
from flask import Flask, g, jsonify, render_template, request
from werkzeug.exceptions import HTTPException
import auth_sessions
import billing_catalog
import db
from . import reports, security

SECTIONS = {'overview','users','sessions','checks','marketing','audit','activities','markets'}
PERMISSIONS = {'owner':SECTIONS,'support':{'overview','users','sessions','checks'},'marketing':{'marketing'}}

def create_app():
    billing_catalog.validate_bypass()   # same bypass rule as the member service
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
        values,issue=security.login(get_db(),data.get('email',''),data.get('password',''),data.get('code',''),client_ip.client_ip(request))
        if issue:return jsonify(error='Please wait before trying again.' if issue=='throttled' else 'Sign-in details or authenticator code were not accepted.'),429 if issue=='throttled' else 401
        response=jsonify(ok=True)
        response.set_cookie(cookie,values['token'],max_age=8*3600,secure=not local,httponly=True,samesite='Strict',path='/')
        response.set_cookie(csrf_cookie,values['csrf'],max_age=8*3600,secure=not local,httponly=False,samesite='Strict',path='/')
        return response

    @app.get('/api/session')
    def session():return jsonify(email=g.admin['email'],role=g.admin['role'],sections=sorted(PERMISSIONS.get(g.admin['role'],set())),csrf=request.cookies.get(csrf_cookie,''),expires_at=g.admin['expires_at'],demo=local and os.getenv('ADMIN_LOCAL_DEMO')=='1',payment_bypass=billing_catalog.payment_bypass())

    @app.post('/api/logout')
    def logout():
        with auth_sessions.transaction(get_db()):
            auth_sessions.sql(get_db(),'UPDATE "AdminSession" SET revoked_at=? WHERE id=?',(int(time.time()),g.admin['id']))
            security.audit(get_db(),g.admin['admin_id'],'logout')
        response=jsonify(ok=True)
        for name in (cookie,csrf_cookie):response.delete_cookie(name,path='/',secure=not local,httponly=name==cookie,samesite='Strict')
        return response

    @app.get('/api/reports/markets')
    def discovery_markets():
        if g.admin['role']!='owner':return jsonify(error='Owner access required.'),403
        with auth_sessions.transaction(get_db()):security.audit(get_db(),g.admin['admin_id'],'report_view','markets')
        import discovery,launch_cities
        return jsonify(markets=[dict(name=c['name'],**discovery.market(get_db(),c['name'])) for c in launch_cities.CITIES],generated_at=int(time.time()))

    @app.post('/api/markets/readiness')
    def discovery_market_update():
        if g.admin['role']!='owner':return jsonify(error='Owner access required.'),403
        from api_contract import ApiError
        import discovery
        body=request.get_json(silent=True)
        if type(body) is not dict or set(body)!={'code','values'}:return jsonify(error='Provide city and readiness.'),400
        try:
            discovery.configure_market(get_db(),body['code'],body['values'])
            with auth_sessions.transaction(get_db()):security.audit(get_db(),g.admin['admin_id'],'market_readiness',str(body['code']))
        except ApiError as exc:return jsonify(error=exc.message),exc.status
        return jsonify(ok=True)

    @app.get('/api/reports/activities')
    def activity_report():
        if g.admin['role']!='owner':return jsonify(error='Owner access required.'),403
        with auth_sessions.transaction(get_db()):security.audit(get_db(),g.admin['admin_id'],'report_view','activities')
        import activity_catalog,onboarding
        return jsonify(suggestions=db.fetch_all(get_db(),'ActivitySuggestion'),activity_options=onboarding.ACTIVITIES,generated_at=int(time.time()))

    @app.post('/api/activities/review')
    def activity_review():
        if g.admin['role']!='owner':return jsonify(error='Owner access required.'),403
        from api_contract import ApiError
        import activity_catalog
        body=request.get_json(silent=True)
        if type(body) is not dict or set(body)!={'name','canonical'}:return jsonify(error='Provide suggestion and canonical activity.'),400
        try:
            activity_catalog.review(get_db(),body['name'],body['canonical'],g.admin['admin_id'])
            with auth_sessions.transaction(get_db()):
                security.audit(get_db(),g.admin['admin_id'],'activity_alias_review',body['name'])
        except ApiError as exc:return jsonify(error=exc.message),exc.status
        return jsonify(ok=True)

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
                filter_name=request.args.get('filter','')
                if filter_name:
                    try:reports.cohort(conn,filter_name)
                    except ValueError:return jsonify(error='Invalid account filter.'),400
                value=reports.users(conn,'',page,filter_name)
            elif section=='sessions':value=reports.sessions(conn,page)
            else:value={'overview':reports.overview,'checks':reports.checks,'marketing':reports.marketing,'audit':reports.audit_log}[section](conn)
        return jsonify({**value,'generated_at':int(time.time()),'timezone':'Asia/Kolkata'})

    @app.get('/api/check-records')
    def check_records():
        if 'checks' not in PERMISSIONS.get(g.admin['role'],set()):return jsonify(error='This section is not available for your role.'),403
        try:page=int(request.args.get('page','1'))
        except ValueError:return jsonify(error='Invalid page.'),400
        values=[request.args.get(k,'') for k in ('operation','environment','state')]
        if not 1<=page<=10000 or any(not 1<=len(v)<=100 for v in values):return jsonify(error='Invalid filter.'),400
        with auth_sessions.transaction(get_db()):security.audit(get_db(),g.admin['admin_id'],'report_view','checks')
        with reports.connection() as conn:
            try:value=reports.check_records(conn,*values,page)
            except ValueError:return jsonify(error='Invalid filter.'),400
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
        return jsonify({**value,'can_lock':g.admin['role']=='owner','generated_at':int(time.time()),'timezone':'Asia/Kolkata'})

    def member_lock_change(action):
        # feat-lock: owner only, reason required, revokes sessions on lock, audited.
        if g.admin['role'] != 'owner':
            return jsonify(error='Owner access required.'), 403
        import member_lock
        body = request.get_json(silent=True)
        if type(body) is not dict or set(body) != {'user_id', 'reason'} or not isinstance(body['user_id'], str) or not 1 <= len(body['user_id']) <= 128:
            return jsonify(error='Provide the member and a reason.'), 400
        try:
            (member_lock.lock if action == 'lock' else member_lock.unlock)(get_db(), body['user_id'], g.admin['admin_id'], body['reason'])
        except LookupError as exc:
            return jsonify(error=str(exc)), 404
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        with auth_sessions.transaction(get_db()):
            security.audit(get_db(), g.admin['admin_id'], 'member_' + action, 'users')
        return jsonify(ok=True, locked=action == 'lock')

    @app.get('/api/reports/deletions')
    def pending_deletions():
        # feat-delete: owner only, audited; ids and dates only.
        if g.admin['role'] != 'owner':
            return jsonify(error='Owner access required.'), 403
        rows = auth_sessions.sql(get_db(), '''SELECT user_id, deletion_requested_at, deletion_due_at FROM "Account"
            WHERE deletion_due_at IS NOT NULL ORDER BY deletion_due_at''').fetchall()
        with auth_sessions.transaction(get_db()):
            security.audit(get_db(), g.admin['admin_id'], 'report_view', 'deletions')
        return jsonify(rows=[{'user_id': r['user_id'], 'requested_at': r['deletion_requested_at'], 'due_at': r['deletion_due_at']} for r in rows],
                       generated_at=int(time.time()))

    @app.post('/api/members/lock')
    def member_lock_route():
        return member_lock_change('lock')

    @app.post('/api/members/unlock')
    def member_unlock_route():
        return member_lock_change('unlock')

    @app.errorhandler(Exception)
    def error(_exception):
        if isinstance(_exception,HTTPException):return jsonify(error=_exception.name),_exception.code
        reference=uuid.uuid4().hex[:12]
        # No exception text, request values or provider/identity payloads in public responses/logs.
        app.logger.error('Admin request failed; reference=%s section=%s',reference,request.endpoint)
        return jsonify(error='Report unavailable. Check deployment/schema configuration.',reference=reference),500

    return app
