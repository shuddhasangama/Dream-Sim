"""Bearer-only identity flow; clients cannot supply provider request IDs."""
from flask import g, request, jsonify
from api_contract import ApiError, json_object
import digilocker_signup as service

def register(api, get_db):
    def actor():
        if not request.headers.get('Authorization','').startswith('Bearer ') or not getattr(g,'auth_session',None):
            raise ApiError('authentication_required','Sign in through the app to verify your details.',401)
        return g.api_user['user_id']
    def response(uid):
        snapshot=service.view(get_db(),uid)
        existing=snapshot.get('session') or {}
        # Adopt previously-confirmed evidence once; never repeat a provider call.
        if existing.get('state')=='complete' and existing.get('identity'):
            import json, db, auth_sessions, verified_identity
            with auth_sessions.transaction(get_db()):
                row=db.fetch_one(get_db(),'User',id=uid)
                if json.loads(row['stats_json'] or '{}').get('identity_session_id')!=existing['id']:
                    verified_identity.apply(get_db(),uid,existing['id'],existing['identity'],snapshot['environment'])
        result = jsonify(snapshot)
        result.headers['Cache-Control']='no-store'
        return result
    @api.get('/verification/payment')
    def verification_payment_read():
        import verification_payment
        result=jsonify(verification_payment.view(get_db(),actor()));result.headers['Cache-Control']='no-store';return result
    @api.post('/verification/payment/start')
    def verification_payment_start():
        import verification_payment
        uid=actor();json_object();return jsonify(verification_payment.start(get_db(),uid))
    @api.post('/verification/payment/complete')
    def verification_payment_complete():
        import verification_payment
        uid=actor();json_object();return jsonify(verification_payment.complete(get_db(),uid))
    @api.get('/verification/digilocker')
    def digilocker_read():
        return response(actor())
    @api.post('/verification/digilocker/sessions')
    def digilocker_start():
        uid=actor(); request.max_content_length=2048
        body=json_object(required={'request_id','consent','consent_version'})
        service.create(get_db(),uid,body)
        return response(uid)
    @api.post('/verification/digilocker/sessions/<sid>/complete')
    def digilocker_complete(sid):
        uid=actor(); request.max_content_length=2048
        body=json_object(required={'consent_completed'})
        service.complete(get_db(),uid,sid,body)
        return response(uid)
