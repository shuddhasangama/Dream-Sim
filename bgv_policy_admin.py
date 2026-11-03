"""Explicit private operator setup. Never calls vendors or approves accounts."""
import argparse
import json
import db
import bgv_policy

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    sub.add_parser('seed')
    assign=sub.add_parser('assign')
    assign.add_argument('--user-id',required=True)
    assign.add_argument('--country',required=True)
    assign.add_argument('--city',required=True)
    assign.add_argument('--reason',required=True)
    status=sub.add_parser('status'); status.add_argument('--user-id',required=True)
    review=sub.add_parser('review')
    review.add_argument('--check-id',required=True)
    review.add_argument('--source-id')
    review.add_argument('--decision',required=True,choices=['satisfied','needs_review','not_satisfied','waived'])
    review.add_argument('--reason',required=True)
    review.add_argument('--reviewer',required=True)
    args=parser.parse_args(); conn=db.get_connection()
    try:
        db.init_db(conn)
        if args.command=='seed': result=bgv_policy.seed(conn)
        elif args.command=='assign': result={'case_id':bgv_policy.assign(conn,args.user_id,args.country,args.city,args.reason)}
        elif args.command=='review': result=bgv_policy.review(conn,args.check_id,args.source_id,args.decision,args.reason,args.reviewer)
        else:
            result=bgv_policy.view(conn,args.user_id)
            # Operator-only source references; no private identity values are printed.
            checks=db.fetch_all(conn,'BgvCaseCheck',case_id=result['case_id']) if result.get('assigned') else []
            result['operator_check_references']=[{'check_id':c['id'],'key':c['check_definition_id'],
                'request_ids':[r['id'] for r in db.fetch_all(conn,'BgvRequest',case_check_id=c['id'])],
                'attempt_ids':[a['id'] for r in db.fetch_all(conn,'BgvRequest',case_check_id=c['id']) for a in db.fetch_all(conn,'BgvAttempt',request_id=r['id'])],
                'digilocker_session_ids':[r['id'] for r in db.fetch_all(conn,'DigiLockerSession',case_check_id=c['id'])]} for c in checks]
        print(json.dumps(result,indent=2))
    finally: conn.close()
