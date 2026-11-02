"""Private operator commands. No public admin endpoints or automatic invitations."""
import argparse
import json
import uuid
import db
import auth_sessions
import waitlist_service as service

def set_status(conn,entry,status,actor):
    transitions={'waiting':{'invited','withdrawn'},'invited':{'accepted','invitation_expired','withdrawn'},
                 'invitation_expired':{'waiting','withdrawn'},'accepted':{'withdrawn'},'withdrawn':set()}
    with auth_sessions.transaction(conn):
        row=db.fetch_one(conn,'WaitlistEntry',id=entry)
        if not row or status not in transitions.get(row['status'],set()) or not actor.strip():
            raise ValueError('Invalid status transition or operator')
        auth_sessions.sql(conn,'UPDATE "WaitlistEntry" SET status=? WHERE id=?',(status,entry))
        auth_sessions.sql(conn,'INSERT INTO "WaitlistAudit" (id,target_id,action,actor,created_at) VALUES (?,?,?,?,?)',
            (str(uuid.uuid4()),entry,'status:'+status,actor,service.stamp()))

def set_launch(conn,market,state,actor):
    if market not in {r['id'] for r in service.markets()} or state not in ('collecting','preparing','pilot','open','paused') or not actor.strip():
        raise ValueError('Valid market, state and operator name required')
    with auth_sessions.transaction(conn):
        auth_sessions.sql(conn,'INSERT INTO "WaitlistMarket" (id,state,updated_at) VALUES (?,?,?) '
            'ON CONFLICT (id) DO UPDATE SET state=excluded.state,updated_at=excluded.updated_at',(market,state,service.stamp()))
        auth_sessions.sql(conn,'INSERT INTO "WaitlistAudit" (id,target_id,action,actor,created_at) VALUES (?,?,?,?,?)',
            (str(uuid.uuid4()),market,'launch:'+state,actor,service.stamp()))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('stats')
    launch=sub.add_parser('launch');launch.add_argument('market');launch.add_argument('state');launch.add_argument('--actor',required=True)
    status=sub.add_parser('status');status.add_argument('entry');status.add_argument('state');status.add_argument('--actor',required=True)
    args=parser.parse_args();conn=db.get_connection()
    try:
        if args.command=='stats':print(json.dumps(service.statistics(conn),indent=2))
        elif args.command=='launch':set_launch(conn,args.market,args.state,args.actor);print('Launch status saved. No invitations sent; no users activated.')
        else:set_status(conn,args.entry,args.state,args.actor);print('Status recorded. No email sent and no account activated.')
    finally:conn.close()
