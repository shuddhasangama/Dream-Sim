"""Inspect/resume provider pauses only. Does not retry or alter user verification."""
import argparse,json
import db,signzy_guard
from signzy.client import Config

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('action',choices=('status','resume'));p.add_argument('--operation',default='*');p.add_argument('--reason');p.add_argument('--apply',action='store_true');a=p.parse_args()
 cfg=Config.from_env();cfg.validate();c=db.get_connection()
 try:
  if a.action=='status':
   rows=[{k:r[k] for k in ('environment','operation','error_code','active','paused_until','updated_at','resume_reason')} for r in db.fetch_all(c,'SignzyGuard') if r['id'].startswith(signzy_guard.prefix(cfg))];print(json.dumps(rows,indent=2))
  elif not a.apply:print('Dry run. Use --apply with --reason after fixing provider access/billing. No requests will be retried.')
  else:signzy_guard.resume(c,cfg,a.operation,a.reason);print('Pause cleared for this scope. Only unsent queued work may continue; failed/uncertain attempts are not retried.')
 finally:c.close()
if __name__=='__main__':main()
