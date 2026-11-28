"""Railway web/worker roles with explicit, idempotent sandbox pilot setup."""
import os
import sys

import prod_guard

def _setting(env, name, default, low, high):
    try:
        value = int(env.get(name, default))
    except (TypeError, ValueError):
        value = default
    return max(low, min(high, value))

def web_command(env=None):
    """gunicorn for the member API (perf-threads). Every default equals gunicorn's own
    default, so an unconfigured deploy starts exactly as `gunicorn app:app` did:
    1 sync worker, timeout 30 s, graceful 30 s, keep-alive 2 s, no recycling.
    Scale with WEB_CONCURRENCY (processes) and GUNICORN_THREADS (>1 => gthread);
    keep workers x threads x replicas inside the connection budget (docs/SCALING.md)."""
    env = os.environ if env is None else env
    workers = _setting(env, 'WEB_CONCURRENCY', 1, 1, 32)
    threads = _setting(env, 'GUNICORN_THREADS', 1, 1, 64)
    args = ['gunicorn', 'app:app',
            '--workers', str(workers),
            '--worker-class', 'gthread' if threads > 1 else 'sync',
            '--timeout', str(_setting(env, 'GUNICORN_TIMEOUT', 30, 5, 300)),
            '--graceful-timeout', str(_setting(env, 'GUNICORN_GRACEFUL_TIMEOUT', 30, 1, 300)),
            '--keep-alive', str(_setting(env, 'GUNICORN_KEEPALIVE', 2, 1, 75))]
    if threads > 1:
        args += ['--threads', str(threads)]
    max_requests = _setting(env, 'GUNICORN_MAX_REQUESTS', 0, 0, 1_000_000)
    if max_requests:
        args += ['--max-requests', str(max_requests),
                 '--max-requests-jitter', str(_setting(env, 'GUNICORN_MAX_REQUESTS_JITTER', max_requests // 10, 0, max_requests))]
    return args

def command(role):
    if role=='web': return web_command()
    if role=='admin': return ['gunicorn','--bind','0.0.0.0:'+os.getenv('PORT','8080'),'--workers','2','--timeout','30','admin_dashboard.wsgi:app']
    if role=='bgv-worker': return [sys.executable,'bgv_worker.py']
    raise ValueError('Unknown DHASHU_PROCESS_ROLE')

def init_schema():
    """Run schema initialisation once at process start (perf-init), so requests
    never run DDL. DHASHU_INIT_DB_ON_START=0 skips it (default: on)."""
    if os.getenv('DHASHU_INIT_DB_ON_START', '1') != '1':
        return False
    import db
    conn = db.get_connection()
    try:
        db.init_db(conn)
    finally:
        conn.close()
    print('Schema initialised at startup; requests run no DDL.', flush=True)
    return True

def prepare_pilot():
    uid=os.getenv('DHASHU_BGV_BOOTSTRAP_USER_ID')
    if not uid: return
    if os.getenv('SIGNZY_ENV')!='preproduction' or os.getenv('SIGNZY_PRODUCTION_ENABLED','0')!='0':
        raise ValueError('BGV pilot bootstrap is sandbox-only')
    import db
    import bgv_policy
    conn=db.get_connection()
    try:
        db.init_db(conn)
        user=db.fetch_one(conn,'User',id=uid)
        if not user: raise ValueError('Configured BGV pilot account does not exist')
        bgv_policy.seed(conn)
        if user.get('active_bgv_case_id'):
            case=db.fetch_one(conn,'BgvCase',id=user['active_bgv_case_id'])
            if not case or case['user_id']!=uid or case['policy_id']!=bgv_policy.POLICY_ID or case['environment']!='preproduction':
                raise ValueError('Existing pilot case needs operator review; not overwriting it')
        else:
            bgv_policy.assign(conn,uid,'IN','BLR','User-authorized direct app Signzy sandbox pilot, 3 November 2026')
        import bgv_app
        repaired=bgv_app.reproject_saved(conn,uid) if os.getenv('DHASHU_BGV_APP_ENABLED')=='1' else 0
        print(f'BGV sandbox saved-result projections refreshed: {repaired}; no provider calls.',flush=True)
        print('BGV sandbox pilot schema and account policy ready; public profile and overall BGV unchanged.',flush=True)
    finally: conn.close()

def main():
    prod_guard.assert_safe_startup()
    import security_config
    security_config.require_secret_key()
    role=os.getenv('DHASHU_PROCESS_ROLE','web')
    argv=command(role)
    if role=='web':
        init_schema()
        prepare_pilot()
    if role=='admin':
        import db
        from admin_dashboard.manage import initialize
        conn=db.get_connection()
        try:
            db.init_db(conn)
            initialize(conn)
        finally: conn.close()
    os.execvp(argv[0],argv)

if __name__=='__main__':
    try:
        main()
    except RuntimeError as exc:
        raise SystemExit(f'Startup refused: {exc}') from None
