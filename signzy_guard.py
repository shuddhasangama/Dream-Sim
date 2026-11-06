"""Durable, credential/environment-scoped provider pauses; never retries paid work."""
import hashlib,time,uuid
import db,auth_sessions
from api_contract import ApiError
from signzy.errors import action
GLOBAL={'credits_unavailable','payment_required','authentication_failed'}
TIMED={'rate_limited':60,'provider_unavailable':300}

def prefix(cfg):return cfg.environment+':'+hashlib.sha256(cfg.token.encode()).hexdigest()[:24]+':'
def blocked(conn,cfg,operation):
 now=int(time.time())
 for scope in ('*',operation):
  r=db.fetch_one(conn,'SignzyGuard',id=prefix(cfg)+scope)
  if r and r['active'] and (r['paused_until']==0 or r['paused_until']>now):return r
 return None

def require_available(conn,cfg,operation):
 r=blocked(conn,cfg,operation)
 if r:raise ApiError('provider_paused',action(r['error_code'])['user_message'],503)

def record(conn,cfg,operation,summary):
 kind=summary.get('error_code')
 if kind not in GLOBAL|{'access_denied'}|set(TIMED):return
 scope='*' if kind in GLOBAL else operation;now=int(time.time())
 with auth_sessions.transaction(conn):
  auth_sessions.sql(conn,'INSERT INTO "SignzyGuard" (id,environment,operation,error_code,paused_until,active,updated_at) VALUES (?,?,?,?,?,1,?) ON CONFLICT (id) DO UPDATE SET error_code=excluded.error_code,paused_until=excluded.paused_until,active=1,updated_at=excluded.updated_at,resume_reason=NULL',
    (prefix(cfg)+scope,cfg.environment,scope,kind,now+TIMED[kind] if kind in TIMED else 0,now))

def execute(conn,cfg,client,operation,values,**kwargs):
 r=blocked(conn,cfg,operation)
 if r:
  # A race may pause between claim and send. Return explicit local evidence,
  # never pretend a provider request was sent or a provider response received.
  summary={**action(r['error_code']),'http_status':None,'outcome':'provider_paused','provider_request_sent':False}
  sink=kwargs.get('evidence_sink')
  if sink:sink({'receipt_id':uuid.uuid4().hex,'operation':operation,'environment':cfg.environment,'provider_response':None,'wrapper_summary':summary,'provider_request_sent':False})
  return summary
 result=client.execute(operation,values,**kwargs)
 record(conn,cfg,operation,result)
 return result

def resume(conn,cfg,operation,reason):
 if not isinstance(reason,str) or not 1<=len(reason.strip())<=200:raise ValueError('Provide a short non-personal recovery reason.')
 with auth_sessions.transaction(conn):
  auth_sessions.sql(conn,'UPDATE "SignzyGuard" SET active=0,updated_at=?,resume_reason=? WHERE id=?',(int(time.time()),reason.strip(),prefix(cfg)+operation))


def public_pause(conn,cfg,operation):
 r=blocked(conn,cfg,operation)
 if not r:return {}
 issue=action(r['error_code'])
 return {'error_code':issue['error_code'],'user_message':issue['user_message'],'provider_paused':True}
