"""Persist simulator evidence separately; never grant verification entitlements."""
import json
import os
import uuid
from dataclasses import asdict
import db
import identity_capture as identity
from api_contract import ApiError
from evolution_service import transaction
from identity_verification import Simulator, Request


def available(uid):
    import auth_sessions
    import clock
    return (os.getenv('DHASHU_IDENTITY_VERIFICATION_MODE','disabled') == 'simulation'
            and identity.enabled() and clock.simulated() and auth_sessions.tester_allowed(uid))


def view(conn, uid):
    row=db.fetch_one(conn,'IdentityCapture',id=uid)
    events=db.fetch_all(conn,'IdentityEvent',user_id=uid) if row and row['status'] not in ('deleted','expired') and row['image_expires_at']>identity.stamp() else []
    items=[e for e in events if e['capture_id']==row['capture_id'] and e['action']=='verification_simulated']
    last=max(items,key=lambda e:e['created_at']) if items else None
    return {'available':available(uid), 'mode':'simulation' if available(uid) else 'disabled',
            'live_connected':False, 'latest':json.loads(last['details']) if last else None}


def simulate(conn,uid,request_id):
    if not available(uid):
        raise ApiError('verification_unavailable','Verification rehearsal is not enabled for this tester.',403)
    try:
        request_id=str(uuid.UUID(request_id))
    except (ValueError,TypeError,AttributeError):
        raise ApiError('validation_error','A UUID request ID is required.')
    with transaction(conn):
        row=db.fetch_one(conn,'IdentityCapture',id=uid)
        if (not row or row['status'] not in ('captured','submitted') or not row['image_ciphertext']
            or row['image_expires_at']<=identity.stamp()
            or row['account_binding_sha256']!=identity.account_binding(conn,uid)):
            raise ApiError('capture_required','Save a current consented identity photo first.',409)
        previous=[e for e in db.fetch_all(conn,'IdentityEvent',user_id=uid)
                  if e['capture_id']==row['capture_id'] and e['action']=='verification_simulated']
        for e in previous:
            receipt=json.loads(e['details'])
            if receipt['request_id']==request_id:
                return receipt
        result=Simulator(os.getenv('DHASHU_IDENTITY_VERIFICATION_SCENARIO','pass')).verify(
            Request('https://example.invalid/selfie','https://example.invalid/reference'))
        receipt={**asdict(result),'request_id':request_id,'mode':'simulation',
                 'capture_id':row['capture_id'],'real_identity_verified':False}
        identity.event(conn,uid,row['capture_id'],'verification_simulated',json.dumps(receipt))
        return receipt
