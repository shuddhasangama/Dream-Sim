"""Authenticated billing endpoints and isolated, signature-authenticated webhook."""
import secrets
from flask import g, jsonify, request, session, render_template, redirect
import auth
import billing_catalog as catalog
import billing_service as service
from api_contract import ApiError, json_object


def guard(get_db):
    if not auth.enabled() or not auth.resolve(get_db):
        raise ApiError('authentication_required', 'A verified login session is required for payments.', 401)
    # Do not trust a request body's platform claim. Native bearer sessions are blocked.
    if g.auth_session['kind'] != 'web':
        catalog.route('android')
    if request.method != 'GET':
        expected=session.get('billing_csrf')
        actual=request.headers.get('X-Billing-CSRF','')
        if not expected or not secrets.compare_digest(expected,actual):
            raise ApiError('csrf_failed','Refresh the checkout page.',403)


def register(api,get_db):
    @api.get('/billing/config')
    def billing_config():
        guard(get_db)
        session.setdefault('billing_csrf',secrets.token_urlsafe(32))
        return jsonify(mode=catalog.mode(),csrf=session['billing_csrf'],products=catalog.PRODUCTS)

    @api.post('/billing/quotes')
    def billing_quote():
        guard(get_db)
        body=json_object(required={'product'},optional={'reference'})
        if not isinstance(body['product'],str) or (body.get('reference') is not None and not isinstance(body['reference'],str)):
            raise ApiError('validation_error','Product and reference must be strings.')
        return jsonify(service.quote(get_db(),g.api_user['user_id'],body['product'],body.get('reference'),'web'))

    @api.post('/billing/purchases/<pid>/checkout')
    def billing_checkout(pid):
        guard(get_db)
        body=json_object(optional={'accept_recurring'})
        return jsonify(service.checkout(get_db(),g.api_user['user_id'],pid,body.get('accept_recurring',False)))

    @api.get('/billing/purchases/<pid>')
    def billing_status(pid):
        guard(get_db)
        return jsonify(service.public(service.get(get_db(),pid,g.api_user['user_id'])))

    @api.post('/billing/purchases/<pid>/refresh')
    def billing_refresh(pid):
        guard(get_db); json_object()
        return jsonify(service.reconcile(get_db(),g.api_user['user_id'],pid))

    @api.post('/billing/purchases/<pid>/cancel-subscription')
    def billing_cancel_subscription(pid):
        guard(get_db); json_object()
        return jsonify(service.cancel_subscription(get_db(),g.api_user['user_id'],pid))


def register_web(app,get_db,current_user):
    @app.get('/billing')
    def billing_page():
        if not current_user():
            return redirect('/signup')
        if catalog.mode() == 'disabled':
            return 'Payment pilot is not enabled.',503
        return render_template('billing.html')

    @app.post('/billing/webhooks/razorpay')
    def billing_webhook():
        if request.content_length and request.content_length > 262144:
            return jsonify(error='Notification too large'),413
        try:
            service.webhook(get_db(),request.get_data(),request.headers.get('X-Razorpay-Signature',''))
            return jsonify(received=True)
        except ApiError as exc:
            return jsonify(code=exc.code,error=exc.message),exc.status
