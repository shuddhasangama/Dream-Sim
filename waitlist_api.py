"""Unauthenticated, bounded write endpoint; no public waitlist read/export."""
import os
from flask import request,jsonify
import auth_sessions
from api_contract import ApiError
import waitlist_service as service

def register(app,get_db):
    @app.route('/public/waitlist/config',methods=['GET','OPTIONS'])
    @app.route('/public/waitlist',methods=['POST','OPTIONS'])
    def waitlist():
        allowed=set(os.getenv('WAITLIST_ALLOWED_ORIGINS','https://dhashu.com,https://www.dhashu.com').split(','))
        origin=request.headers.get('Origin','')
        def reply(data,status=200):
            result=jsonify(data); result.status_code=status
            result.headers['Cache-Control']='no-store'; result.headers['Vary']='Origin'
            if origin in allowed:
                result.headers['Access-Control-Allow-Origin']=origin
                result.headers['Access-Control-Allow-Methods']='GET, POST, OPTIONS'
                result.headers['Access-Control-Allow-Headers']='Content-Type'
            return result
        if origin not in allowed: return reply({'error':'Origin not allowed'},403)
        if request.method=='OPTIONS': return reply({},204)
        try:
            service.configured()
            if request.method=='GET': return reply(service.public_config(get_db()))
            request.max_content_length=16000
            if not request.is_json: return reply({'error':'JSON required'},415)
            # Never trust a caller-supplied forwarding header for rate limits.
            key=service.digest('ip:'+(request.remote_addr or 'unknown'))
            if not auth_sessions.throttle(get_db(),['waitlist:'+key],20,3600):
                return reply({'error':'Too many attempts. Please try later.'},429)
            return reply(service.submit(get_db(),request.get_json()),201)
        except ApiError as exc: return reply({'error':exc.message,'code':exc.code},exc.status)
