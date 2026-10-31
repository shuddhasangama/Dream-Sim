"""Native bearer-only verification boundary: no user ID accepted from clients."""
from flask import g, request, jsonify
from api_contract import ApiError, json_object
import auth_sessions
import bgv_app

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
    @api.post('/verification')
    def verification_submit():
        uid = actor()
        request.max_content_length = 16000
        body = json_object(required={'request_id','operation','inputs','declared','consent','consent_version'})
        if not auth_sessions.throttle(get_db(), ['bgv-submit:' + uid], 6, 3600):
            raise ApiError('rate_limited', 'Too many requests. Please try later.', 429)
        bgv_app.submit(get_db(), uid, body)
        return response(uid), 202
