"""Durable payment orchestration; provider IO never runs inside a DB transaction."""
from contextlib import contextmanager
import json
import hashlib
import time
import uuid
import db
import auth_sessions
import planning_service as planning
from api_contract import ApiError
import billing_catalog as catalog
from billing_razorpay import Razorpay, verify_webhook

sql = auth_sessions.sql


@contextmanager
def transaction(conn):
    with auth_sessions.transaction(conn):
        if db._is_postgres_connection(conn):
            sql(conn, 'LOCK TABLE "BillingPurchase" IN SHARE ROW EXCLUSIVE MODE')
        yield


def get(conn, pid, uid=None):
    row = db.fetch_one(conn, 'BillingPurchase', id=pid)
    if not row or (uid is not None and row['user_id'] != uid):
        raise ApiError('not_found', 'Payment not found.', 404)
    return row


def update(conn, pid, **fields):
    fields['updated_at'] = int(time.time())
    sql(conn, 'UPDATE "BillingPurchase" SET '+','.join('"'+key+'"=?' for key in fields)+' WHERE id=?',
        (*fields.values(), pid))


def scope(conn, uid, product, reference):
    if not db.fetch_one(conn, 'User', id=uid):
        raise ApiError('not_found', 'User not found.', 404)
    if product in ('verification', 'guru'):
        if reference not in (None, '', uid):
            raise ApiError('invalid_scope', 'This purchase belongs to the signed-in user.')
        return uid
    if product in ('date_mechanics', 'relationship_entry'):
        planning.pair(conn, uid, reference)
        return planning.availability_scope(conn, reference) if product == 'date_mechanics' else reference
    if product == 'engagement_marriage':
        couple = db.fetch_one(conn, 'Couple', id=reference)
        if not couple or uid not in (couple['partner_a_id'], couple['partner_b_id']):
            raise ApiError('not_found', 'Couple not found.', 404)
        return reference
    raise ApiError('unknown_product', 'Unknown product.')


def quote(conn, uid, product, reference, channel):
    provider = catalog.route(channel)
    price = catalog.price(uid, product)
    scoped = scope(conn, uid, product, reference)
    pid = uuid.uuid4().hex
    now = int(time.time())
    with transaction(conn):
        planning.save(conn, 'BillingPurchase', {
            'id': pid, 'user_id': uid, 'product': product, 'scope_id': scoped,
            'reference_id': reference or uid, 'mode': price['mode'], 'provider': provider,
            'amount': price['amount'], 'currency': price['currency'], 'price_json': json.dumps(price),
            'status': 'quoted', 'payment_status': 'unpaid', 'refund_status': 'none',
            'created_at': now, 'updated_at': now, 'expires_at': now+900,
        })
    return public(get(conn, pid))


def public(row):
    price = json.loads(row['price_json'])
    return {key: row[key] for key in ('id','product','scope_id','amount','currency','mode','status',
            'payment_status','refund_status','expires_at','paid_until','cancel_requested')} | {
        'label': price['label'], 'recurring': price['recurring'], 'catalog_amount': price['catalog_amount'],
        'price_version': price['version'], 'test_price': True,
        'subscription_cycles': 12 if price['recurring'] else None}


def checkout(conn, uid, pid, accept_recurring=False):
    gateway = Razorpay()  # validate credentials BEFORE reserving an attempt
    with transaction(conn):
        row = get(conn, pid, uid)
        if row['mode'] != catalog.mode():
            raise ApiError('environment_mismatch', 'Create a new quote in the current environment.', 409)
        catalog.price(uid, row['product'])
        if row['status'] != 'quoted':
            return checkout_result(row, gateway)
        if row['expires_at'] < time.time():
            raise ApiError('quote_expired', 'Refresh the payment quote.', 409)
        if scope(conn, uid, row['product'], row['reference_id']) != row['scope_id']:
            raise ApiError('scope_changed', 'The date has changed. Refresh the quote.', 409)
        if row['product'] == 'guru' and accept_recurring is not True:
            raise ApiError('recurring_consent', 'Accept monthly billing for up to 12 cycles before continuing.')
        others = db.fetch_all(conn, 'BillingPurchase', user_id=uid, product=row['product'], scope_id=row['scope_id'], mode=row['mode'])
        if any(r['id'] != pid and r['status'] not in ('quoted', 'refunded', 'cancelled', 'failed') for r in others):
            raise ApiError('purchase_exists', 'A purchase already exists for this action. Check its status.', 409)
        update(conn, pid, status='creating')
    try:
        result = gateway.create_subscription(row) if row['product'] == 'guru' else gateway.create_order(row)
        provider_id = result['id']
        if not isinstance(provider_id, str) or not provider_id.replace('_','').isalnum():
            raise ValueError('Invalid provider ID')
        with transaction(conn):
            update(conn, pid, provider_id=provider_id, status='checkout_ready')
    except Exception:
        with transaction(conn):
            update(conn, pid, status='reconciling')
        raise
    return checkout_result(get(conn, pid, uid), gateway)


def checkout_result(row, gateway):
    result = public(row)
    if row['status'] == 'checkout_ready':
        options = {'key': gateway.key, 'name': 'DhaShu', 'description': json.loads(row['price_json'])['label']}
        if row['product'] == 'guru':
            options['subscription_id'] = row['provider_id']
        else:
            options.update(order_id=row['provider_id'], amount=row['amount'], currency=row['currency'])
        result['checkout'] = options
    return result


def grant(conn, row):
    expires = row['paid_until'] if row['product'] == 'guru' else None
    planning.save(conn, 'BillingEntitlement', {'id':row['id'], 'purchase_id':row['id'],
        'user_id':row['user_id'], 'product':row['product'], 'scope_id':row['scope_id'],
        'mode':row['mode'], 'active':1, 'expires_at':expires})


def entitled(conn, uid, product, scoped=None):
    if catalog.mode() == 'disabled':
        return False
    rows = db.fetch_all(conn, 'BillingEntitlement', user_id=uid, product=product, mode=catalog.mode())
    return any(r['active'] and (scoped is None or r['scope_id'] == scoped)
               and (r['expires_at'] is None or r['expires_at'] > time.time()) for r in rows)


def legacy_entitled(conn, uid, purpose, scoped):
    """Bridge old stage gates to the new ledger, never to simulated payments."""
    if purpose == 'availability':
        return entitled(conn,uid,'date_mechanics',scoped)
    if purpose == 'agreement':
        plan=db.fetch_one(conn,'DatePlan',id=scoped)
        if not plan:
            return False
        # The active planning cycle is the same one bought before availability.
        return entitled(conn,uid,'date_mechanics',planning.availability_scope(conn,plan['lockin_id']))
    if purpose == 'stage_gate':
        return entitled(conn,uid,'relationship_entry',scoped)
    if purpose == 'guru':
        return entitled(conn,uid,'guru',uid)
    return False


def apply_payment(conn, row, payment, paid_until=None):
    if payment.get('status') != 'captured':
        return
    if (payment.get('amount'), payment.get('currency')) != (row['amount'], row['currency']):
        raise ApiError('payment_mismatch', 'Payment does not match the saved purchase.', 409)
    if not payment.get('id'):
        raise ApiError('payment_mismatch', 'Missing payment reference.', 409)
    if payment.get('amount_refunded',0):
        # Reconcile dashboard refunds even if the refund webhook was missed.
        # Partial refunds need an explicit entitlement policy: conservatively suspend access.
        update(conn,row['id'],status='refunded',refund_status='processed',payment_id=payment['id'])
        sql(conn,'UPDATE "BillingEntitlement" SET active=0 WHERE purchase_id=?',(row['id'],))
        return
    if row['refund_status'] != 'none':
        return  # late capture notifications never restore refunded access
    if row['product'] == 'guru' and (not isinstance(paid_until, int) or paid_until <= 0):
        raise ApiError('subscription_period_missing', 'No verified paid subscription period.', 409)
    expiry = max(row['paid_until'] or 0, paid_until or 0) or None
    if row['product'] == 'guru' and (row['paid_until'] or 0) > (paid_until or 0):
        return
    status = 'cancelled' if row['status']=='cancelled' else 'paid'
    update(conn, row['id'], status=status, payment_status='captured', payment_id=payment['id'], paid_until=expiry)
    grant(conn, get(conn, row['id']))


def reconcile(conn, uid, pid):
    row = get(conn, pid, uid)
    if row['mode'] != catalog.mode():
        raise ApiError('environment_mismatch', 'Use the original billing environment.', 409)
    if not row['provider_id']:
        return public(row)  # ambiguous create: operations must locate the receipt; NEVER retry create
    gateway = Razorpay()
    if row['refund_id']:
        result = gateway.call('GET', 'refunds/'+row['refund_id'])
        with transaction(conn):
            apply_refund(conn, get(conn,pid), result)
    elif row['product'] != 'guru':
        result = gateway.call('GET', 'orders/'+row['provider_id']+'/payments')
        captured = [p for p in result.get('items', []) if p.get('status') == 'captured' and p.get('order_id') == row['provider_id']]
        with transaction(conn):
            for payment in captured:
                apply_payment(conn, get(conn, pid), payment)
    else:
        subscription = gateway.call('GET','subscriptions/'+row['provider_id'])
        invoices = gateway.call('GET','invoices?subscription_id='+row['provider_id']+'&count=100')
        for invoice in sorted(invoices.get('items',[]),key=lambda x:x.get('billing_end') or 0):
            if invoice.get('subscription_id') != row['provider_id'] or invoice.get('status') != 'paid' or not invoice.get('payment_id'):
                continue
            payment=gateway.call('GET','payments/'+invoice['payment_id'])
            if payment.get('invoice_id') != invoice.get('id'):
                continue
            with transaction(conn):
                apply_payment(conn,get(conn,pid),payment,invoice.get('billing_end'))
        if subscription.get('status') in ('cancelled','completed','expired'):
            with transaction(conn):
                update(conn,pid,status='cancelled')
    return public(get(conn, pid, uid))


def apply_refund(conn, row, refund):
    if refund.get('payment_id') != row['payment_id'] or refund.get('amount') != row['amount']:
        raise ApiError('refund_mismatch', 'Refund does not match this purchase.', 409)
    status = refund.get('status')
    if status == 'processed':
        update(conn, row['id'], status='refunded', refund_status='processed', refund_id=refund['id'])
        sql(conn, 'UPDATE "BillingEntitlement" SET active=0 WHERE purchase_id=?', (row['id'],))
    elif status in ('pending', 'failed') and row['refund_status'] != 'processed':
        update(conn, row['id'], refund_status=status, refund_id=refund['id'])


def refund(conn, pid):
    """Operations-only entry point. Full one-time refunds; never exposed to an ordinary user."""
    gateway = Razorpay()
    with transaction(conn):
        row = get(conn,pid)
        if row['mode'] != catalog.mode() or row['product'] == 'guru':
            raise ApiError('refund_unavailable', 'Use provider operations for subscription refunds.', 409)
        if row['payment_status'] != 'captured' or row['refund_status'] != 'none':
            raise ApiError('refund_unavailable', 'Refund is unavailable or already requested.', 409)
        update(conn,pid,refund_status='requested')
    try:
        result = gateway.call('POST','payments/'+row['payment_id']+'/refund', {'amount':row['amount'], 'notes':{'purchase_id':pid}})
        with transaction(conn):
            apply_refund(conn,get(conn,pid),result)
    except Exception:
        # Requested remains durable; operations must reconcile, not submit another refund.
        raise
    return public(get(conn,pid))


def cancel_subscription(conn, uid, pid):
    row=get(conn,pid,uid)
    if row['product'] != 'guru' or not row['provider_id'] or row['mode'] != catalog.mode():
        raise ApiError('subscription_unavailable','Subscription unavailable.',409)
    with transaction(conn):
        if get(conn,pid)['cancel_requested']:
            return public(get(conn,pid))
        update(conn,pid,cancel_requested=1)
    Razorpay().call('POST','subscriptions/'+row['provider_id']+'/cancel',{'cancel_at_cycle_end':1})
    return public(get(conn,pid))


def webhook(conn, raw, signature):
    verify_webhook(raw, signature)
    if catalog.mode() == 'disabled':
        raise ApiError('billing_disabled','Billing is disabled.',503)
    try:
        event=json.loads(raw)
        payload=event['payload']
        kind=event['event']
        if not isinstance(payload,dict):
            raise ValueError()
    except (ValueError,KeyError,TypeError):
        raise ApiError('invalid_event','Invalid payment event.') from None
    payment=payload.get('payment',{}).get('entity',{})
    subscription=payload.get('subscription',{}).get('entity',{})
    refund_entity=payload.get('refund',{}).get('entity',{})
    provider_id=subscription.get('id') or payment.get('order_id')
    event_id=hashlib.sha256(raw).hexdigest()
    with transaction(conn):
        if db.fetch_one(conn,'BillingEvent',id=event_id):
            return
        rows=db.fetch_all(conn,'BillingPurchase',mode=catalog.mode())
        row=next((r for r in rows if (provider_id and r['provider_id']==provider_id) or
                  (refund_entity.get('payment_id') and r['payment_id']==refund_entity['payment_id'])),None)
        if row is None:
            # A notification can race create_order's response; retry delivery later.
            if kind in ('payment.captured','subscription.charged','refund.processed','refund.failed'):
                raise ApiError('purchase_not_ready','Purchase mapping not ready.',503)
            return
        if kind == 'payment.captured' and row['product'] != 'guru':
            apply_payment(conn,row,payment)
        elif kind == 'subscription.charged' and row['product']=='guru':
            apply_payment(conn,row,payment,subscription.get('current_end'))
        elif kind in ('refund.processed','refund.failed'):
            apply_refund(conn,row,refund_entity)
        elif kind in ('subscription.cancelled','subscription.completed'):
            update(conn,row['id'],status='cancelled')
        planning.save(conn,'BillingEvent',{'id':event_id,'purchase_id':row['id'],
            'kind':kind,'received_at':int(time.time())})
        # Failures/authorized mandates never grant access or overwrite a captured payment.
