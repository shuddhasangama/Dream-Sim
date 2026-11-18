"""Inspect one user's employment; --run schedules a missing request and runs it once.

Never retries completed, failed or uncertain requests. Prints no PAN or receipt body.
"""
import argparse
import json
import db
import auth
import bgv_app
import bgv_bundle
import signzy_guard

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phone',required=True)
    parser.add_argument('--run',action='store_true')
    args=parser.parse_args()
    conn=db.get_connection()
    try:
        phone=auth.normalize('phone',args.phone)
        accounts=[dict(a) for a in db.fetch_all(conn,'Account') if auth.normalize('phone',a.get('phone'),stored=True)==phone]
        if len(accounts)!=1:raise ValueError('Expected exactly one account; no work submitted.')
        uid=accounts[0]['user_id'];cfg=bgv_app.config()
        status=bgv_bundle.view(conn,uid)
        print('User:',uid)
        print(json.dumps({k:status.get(k) for k in ('consented','pan_state','pan_source','employment_identifier_available','employment_blocker')},indent=2))
        if args.run:
            if not status.get('consented') or not status.get('employment_identifier_available') or status.get('employment_blocker'):
                raise ValueError('Employment prerequisites are incomplete; no provider request sent.')
            bgv_bundle.schedule(conn,user_id=uid,employment_only=True)
        rows=db.fetch_all(conn,'BgvRequest',user_id=uid,operation='current_employer',environment=cfg.environment)
        if not rows:print('No employment request. Check worker deployment and identity-session/active-plan linkage.')
        for row in rows:
            if args.run and row['state']=='queued':
                source=bgv_app.Protection().open(row['protected_input'])
                operation=source.get('provider_operation',row['operation'])
                if signzy_guard.blocked(conn,cfg,operation):
                    print('Provider is paused. No request sent; resolve the provider issue first.')
                else:bgv_app.work_one(conn,request_id=row['id'])
                row=db.fetch_one(conn,'BgvRequest',id=row['id'])
            print(json.dumps({k:row.get(k) for k in ('id','operation','environment','state','created_at','updated_at')},default=str))
        print('Existing outcomes were not reset or replayed.' if args.run else 'READ ONLY: no provider requests sent.')
    finally:conn.close()

if __name__=='__main__':main()
