"""Sandbox notification acknowledgement only, not an identity approval endpoint.

The private tester retrieves results by requestId after human consent. No callback
payload, URL parameter or notification is trusted as identity/consent evidence.
"""
import os
import re
from flask import jsonify,request

def register(app):
    @app.route('/public/signzy/digilocker/callback/<nonce>',methods=['GET','POST'])
    def signzy_digilocker_callback(nonce):
        if (os.getenv('SIGNZY_DIGILOCKER_SANDBOX_CALLBACK_ENABLED')!='1'
                or os.getenv('SIGNZY_ENV','preproduction')!='preproduction'
                or not re.fullmatch(r'[a-f0-9]{32}',nonce)):
            return jsonify(error='Not found'),404
        if request.content_length and request.content_length>1024*1024:
            return jsonify(error='Notification too large'),413
        # Deliberately do not parse, echo, persist or act on provider data here.
        response=jsonify(received=True)
        response.headers['Cache-Control']='no-store'
        return response
