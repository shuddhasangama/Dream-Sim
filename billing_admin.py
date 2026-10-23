"""Operations CLI. No credentials or personal payment details are printed."""
import argparse
import json
import db
import billing_service as service


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['status','reconcile','refund'])
    parser.add_argument('--purchase-id',required=True)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    if args.action=='refund' and not args.apply:
        parser.error('Refund changes money. Review status first, then pass --apply.')
    conn=db.get_connection()
    try:
        db.init_db(conn)
        row=service.get(conn,args.purchase_id)
        result=(service.refund(conn,row['id']) if args.action=='refund' else
                service.reconcile(conn,row['user_id'],row['id']) if args.action=='reconcile' else service.public(row))
        print(json.dumps(result,indent=2))
    finally:
        conn.close()


if __name__=='__main__':main()
