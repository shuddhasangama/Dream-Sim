"""Normalize observed legal result envelopes without deciding identity or clearance."""
PENDING_MESSAGES={'processing','processing pending','process pending','in progress'}
def normalized(body):
    if not isinstance(body,dict):return {},False
    nested=body.get('result')
    if nested is not None:
        # Reject conflicting mixed envelopes rather than choosing one silently.
        if not isinstance(nested,dict) or any(k in body for k in ('cases','status','message')):return {},False
        return nested,True
    return body,True

def pending(status,data):
    message=data.get('message')
    text=message.strip().rstrip('.').casefold() if isinstance(message,str) else ''
    return status==202 or (status==200 and type(data.get('status')) is int and data['status']==0 and text in PENDING_MESSAGES) or (status==200 and text in PENDING_MESSAGES)
