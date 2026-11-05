"""Account-bound sandbox checkout. Never authorizes live native billing or BGV approval."""
import json
import time
import uuid
from urllib.parse import urlparse
import db
import billing_catalog as catalog
import billing_service as billing
import planning_service as planning
from billing_razorpay import Razorpay
from api_contract import ApiError

PROVIDER='razorpay_verification_test_link'

def latest(conn,uid):
    rows=db.fetch_all(conn,'BillingPurchase',user_id=uid,product='verification',mode='sandbox',provider=PROVIDER)
    return max(rows,key=lambda r:r['created_at']) if rows else None

def view(conn,uid):
    mode=catalog.mode()
    if mode=='disabled':return {'required':False,'enabled':False,'can_begin':True}
    if mode!='sandbox':return {'required':True,'enabled':False,'can_begin':False,'state':'unavailable','message':'Sandbox checkout is unavailable in this billing mode.'}
    row=latest(conn,uid)
    paid=billing.entitled(conn,uid,'verification',uid)
    price=json.loads(row['price_json']) if row else {}
    test_access=bool(price.get('sandbox_bgv_access'))
    return {'required':True,'enabled':True,'can_begin':paid or test_access,'state':'test_access' if test_access and not paid else 'paid' if paid else row['status'] if row else 'not_started',
            'purchase_id':row['id'] if row else None,'checkout_url':price.get('checkout_url') if row and row['status']=='pending' and not paid else None,
            'amount':100,'currency':'INR','real_amount':0,'mode':'sandbox',
            'message':'Test payment only — ₹0 real money deducted. Razorpay shows a simulated ₹1 payment.'}

def require_paid(conn,uid):
    if not view(conn,uid)['can_begin']:
        raise ApiError('verification_payment_required','Complete the test payment before beginning verification.',402)

def start(conn,uid):
    if catalog.mode()!='sandbox':raise ApiError('sandbox_only','This checkout is available only in Razorpay test mode.',409)
    gateway=Razorpay()
    if not gateway.key.startswith('rzp_test_'):raise ApiError('sandbox_only','A Razorpay test key is required.',503)
    now=int(time.time())
    with billing.transaction(conn):
        if billing.entitled(conn,uid,'verification',uid):return view(conn,uid)
        row=latest(conn,uid)
        if row and row['status'] not in ('expired','cancelled'):
            return view(conn,uid)  # Includes uncertain submissions: never duplicate.
        if row:now=max(now,row['created_at']+1)
        pid=uuid.uuid4().hex
        price={'label':'Verification test payment','recurring':False,'catalog_amount':100,'version':'verification-sandbox-v1'}
        planning.save(conn,'BillingPurchase',{'id':pid,'user_id':uid,'product':'verification','scope_id':uid,'reference_id':uid,
            'mode':'sandbox','provider':PROVIDER,'amount':100,'currency':'INR','price_json':json.dumps(price),'status':'creating',
            'payment_status':'unpaid','refund_status':'none','created_at':now,'updated_at':now,'expires_at':now+1800})
    try:
        link=gateway.call('POST','payment_links',{'amount':100,'currency':'INR','accept_partial':False,'reference_id':pid,
            'description':'DhaShu verification — test payment only','expire_by':now+1800,
            'notify':{'sms':False,'email':False},'reminder_enable':False,'notes':{'purchase_id':pid}})
        url=urlparse(link.get('short_url',''))
        if not str(link.get('id','')).startswith('plink_') or url.scheme!='https' or url.hostname not in ('rzp.io','rzp.in') or url.username or url.password:
            raise ApiError('provider_response_invalid','Checkout could not be confirmed. Contact support before trying again.',503)
        if link.get('amount')!=100 or link.get('currency')!='INR' or link.get('reference_id')!=pid:
            raise ApiError('provider_response_invalid','Checkout details do not match the saved purchase.',503)
        price['checkout_url']=link['short_url']
        if link.get('order_id'):price['order_id']=link['order_id']
        with billing.transaction(conn):billing.update(conn,pid,provider_id=link['id'],status='pending',price_json=json.dumps(price))
    except Exception:
        with billing.transaction(conn):billing.update(conn,pid,status='outcome_unknown')
        raise
    return view(conn,uid)

def complete(conn,uid):
    if catalog.mode()!='sandbox':raise ApiError('sandbox_only','Only sandbox payments can be checked here.',409)
    row=latest(conn,uid)
    if not row:raise ApiError('not_found','No verification test payment found.',404)
    # Private tester rollout: failed/unavailable sandbox checkout must not block
    # BGV. Record access separately; never fabricate paid/captured evidence or
    # grant a billing entitlement. Live modes are rejected above.
    with billing.transaction(conn):
        current=billing.get(conn,row['id'],uid)
        price=json.loads(current['price_json'])
        price['sandbox_bgv_access']=True
        price['sandbox_bgv_access_at']=int(time.time())
        billing.update(conn,row['id'],price_json=json.dumps(price))
    return view(conn,uid)


def confirm_provider_payment(conn,uid):
    if catalog.mode()!='sandbox':raise ApiError('sandbox_only','Only sandbox payments can be checked here.',409)
    row=latest(conn,uid)
    if not row:raise ApiError('not_found','No verification test payment found.',404)
    if row['status']=='paid':return view(conn,uid)
    if not row['provider_id']:raise ApiError('outcome_unknown','Checkout creation could not be confirmed. Contact support.',409)
    gateway=Razorpay()
    if not gateway.key.startswith('rzp_test_'):raise ApiError('sandbox_only','A test key is required.',503)
    link=gateway.call('GET','payment_links/'+row['provider_id'])
    if (link.get('id'),link.get('reference_id'),link.get('amount'),link.get('currency'))!=(row['provider_id'],row['id'],100,'INR'):
        raise ApiError('payment_mismatch','Provider payment does not match this account checkout.',409)
    if link.get('status') in ('expired','cancelled'):
        with billing.transaction(conn):billing.update(conn,row['id'],status=link['status'])
    elif link.get('status')=='paid' and link.get('amount_paid')==100:
        payments=[p for p in link.get('payments',[]) if p.get('status')=='captured' and p.get('amount')==100]
        if len(payments)!=1:raise ApiError('payment_unconfirmed','A captured payment could not be confirmed.',409)
        pid=payments[0].get('payment_id')
        if not isinstance(pid,str) or not pid.startswith('pay_'):raise ApiError('payment_unconfirmed','Payment reference missing.',409)
        payment=gateway.call('GET','payments/'+pid)
        if payment.get('id')!=pid or payment.get('order_id')!=link.get('order_id') or not link.get('order_id'):
            raise ApiError('payment_mismatch','Captured payment is not bound to this checkout.',409)
        with billing.transaction(conn):
            price=json.loads(row['price_json']);price['order_id']=link['order_id']
            billing.update(conn,row['id'],price_json=json.dumps(price))
            billing.apply_payment(conn,billing.get(conn,row['id'],uid),payment)
    return view(conn,uid)
