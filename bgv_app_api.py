"""Native bearer-only verification boundary: no user ID accepted from clients."""
from flask import g, request, jsonify
from api_contract import ApiError, json_object
import auth_sessions
import bgv_app
import bgv_policy
import db

def register(api, get_db):
    def actor():
        if not request.headers.get('Authorization', '').startswith('Bearer ') or not getattr(g, 'auth_session', None):
            raise ApiError('authentication_required', 'Sign in through the app to manage verification.', 401)
        return g.api_user['user_id']
    def response(uid):
        result = jsonify(bgv_app.view(get_db(), uid))
        result.headers['Cache-Control'] = 'no-store'
        return result
    @api.get('/verification')
    def verification_read():
        return response(actor())
    @api.get('/verification/plan')
    def verification_plan():
        result=jsonify(bgv_policy.view(get_db(),actor()))
        result.headers['Cache-Control']='no-store'
        return result
    @api.get('/verification/liveness')
    def verification_liveness():
        uid=actor()
        import liveness_secure_service as hosted
        if hosted.enabled():
            result=jsonify(hosted.view(get_db(),uid));result.headers['Cache-Control']='no-store';return result
        rows=sorted(db.fetch_all(get_db(),'DigiLockerSession',user_id=uid),key=lambda r:r['created_at'],reverse=True)
        result=jsonify(enabled=False,state='setup_required',reference_photo_available=any(r.get('protected_photo') and r['state']=='complete' for r in rows),
            message='Passive liveness is not connected. Selfie capture and standalone face comparison are separate app steps. No liveness check has been performed.',
            required_inputs=['Signzy image upload or approved capture SDK contract','Image access/expiry requirements','Sandbox test with a consented selfie and document photo'])
        result.headers['Cache-Control']='no-store'
        return result
    @api.post('/verification/bundle')
    def verification_bundle():
        import bgv_bundle
        uid=actor(); request.max_content_length=4096
        body=json_object(required={'session_id','consent','consent_version'},optional={'employer'})
        bgv_bundle.consent(get_db(),uid,body)
        return response(uid),202
    @api.post('/verification')
    def verification_submit():
        uid = actor()
        request.max_content_length = 16000
        body = json_object(required={'request_id','operation','inputs','declared','consent','consent_version'})
        if not auth_sessions.throttle(get_db(), ['bgv-submit:' + uid], 6, 3600):
            raise ApiError('rate_limited', 'Too many requests. Please try later.', 429)
        bgv_app.submit(get_db(), uid, body)
        return response(uid), 202
    @api.post('/verification/<rid>/result')
    def verification_result(rid):
        uid=actor(); request.max_content_length=2048
        body=json_object(required={'request_id'})
        if not auth_sessions.throttle(get_db(),['bgv-result:'+uid],6,3600):
            raise ApiError('rate_limited','Too many result requests. Please try later.',429)
        bgv_app.fetch_result(get_db(),uid,rid,body['request_id'])
        return response(uid),202
    @api.post('/verification/<rid>/check-again')
    def verification_check_again(rid):
        uid=actor(); request.max_content_length=2048
        json_object()
        bgv_app.check_again(get_db(),uid,rid)
        return response(uid),202
