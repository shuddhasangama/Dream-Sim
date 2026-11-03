"""Railway web/worker roles with explicit, idempotent sandbox pilot setup."""
import os
import sys

def command(role):
    if role=='web': return ['gunicorn','app:app']
    if role=='bgv-worker': return [sys.executable,'bgv_worker.py']
    raise ValueError('Unknown DHASHU_PROCESS_ROLE')

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

if __name__=='__main__':
    role=os.getenv('DHASHU_PROCESS_ROLE','web')
    argv=command(role)
    if role=='web': prepare_pilot()
    os.execvp(argv[0],argv)
