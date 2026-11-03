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
        result = jsonify(service.view(get_db(),uid))
        result.headers['Cache-Control']='no-store'
        return result
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
