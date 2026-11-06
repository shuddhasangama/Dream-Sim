"""Stable public classifications. Provider text belongs only in encrypted evidence."""
ACTIONS={
 'credits_unavailable':('operator','Top up the Signzy wallet, check failed-call billing, then explicitly resume the guard.','Verification is temporarily unavailable. Please contact support; your details have not failed verification.'),
 'payment_required':('operator','Check Signzy account billing and entitlement; confirm the cause before resuming.','Verification is temporarily unavailable. Please contact support.'),
 'authentication_failed':('operator','Check credentials and sandbox/production environment, then resume after correction.','Verification is temporarily unavailable. Please contact support.'),
 'access_denied':('operator','Ask Signzy to enable this product for the configured environment, then resume this API.','This verification service is not available yet. Please contact support.'),
 'rate_limited':('operator','Respect the provider cooldown. Do not replay the attempted request automatically.','The verification provider is busy. Please wait; avoid starting another check.'),
 'invalid_input':('user_or_support','Review the encrypted validation response and correct the source input before a new approved attempt.','Some details could not be accepted. Review your details or contact support.'),
 'no_records_found':('user_or_support','Review source coverage and identity linkage. No record does not prove unemployment or legal clearance.','No matching records were returned. This check has not confirmed your details.'),
 'provider_unavailable':('operator','Check the provider incident and request logs before deciding whether another attempt is safe.','The verification provider is temporarily unavailable. Your check has not been marked failed.'),
 'network_error_outcome_unknown':('operator','Reconcile the request with Signzy logs and billing before any approved retry.','The result could not be confirmed. Please contact support before starting another check.'),
 'invalid_provider_response':('operator','Inspect encrypted evidence and confirm the response contract; do not replay automatically.','The result could not be interpreted. Please contact support before starting another check.'),
 'provider_error':('operator','Inspect the encrypted provider response and request reference; do not automatically resubmit.','The verification could not be completed. Please contact support.')
}
def action(kind):
 owner,next_action,message=ACTIONS.get(kind,ACTIONS['provider_error'])
 return {'error_code':kind,'action_owner':owner,'next_action':next_action,'user_message':message,'retry_automatically':False,'automatic_verification':False}

def classify(status,body):
 body=body if isinstance(body,dict) else {}
 raw_error=body.get('error');error=raw_error if isinstance(raw_error,dict) else {}
 text=' '.join(str(v) for v in (error.get('reason',''),error.get('message',''),raw_error if isinstance(raw_error,str) else '',body.get('reason',''),body.get('message',''))).casefold()
 try:code=int(error.get('statusCode',error.get('status',status)))
 except (ValueError,TypeError):code=status
 kind=None
 if any(w in text for w in ('wallet','credit','balance','funds')) and any(w in text for w in ('exhaust','insufficient','empty','not enough','zero','low balance')):kind='credits_unavailable'
 elif 'no api key' in text or 'authentication credentials' in text or status==401 or code==401:kind='authentication_failed'
 elif status==402 or code==402:kind='payment_required'
 elif status==403 or code==403:kind='access_denied'
 elif status==429 or code==429:kind='rate_limited'
 elif code==404 and any(w in text for w in ('no record','no matching record','records not found')):kind='no_records_found'
 elif code==400:kind='invalid_input'
 elif code==409 and 'upstream' in text:kind='provider_unavailable'
 elif status and status>=500 or isinstance(code,int) and code>=500:kind='provider_unavailable'
 elif raw_error or status and status>=400:kind='provider_error'
 return {**action(kind),'outcome':'request_failed'} if kind else {}
