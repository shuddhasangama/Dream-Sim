"""Authenticated enrollment bound exclusively to the current approved account."""
from flask import current_app, g, jsonify
from api_contract import ApiError, json_object
import enrollment_service as service

def register(api, get_db):
    def uid():
        if not current_app.config.get('AUTH_ENABLED'):
            raise ApiError('secure_auth_required', 'Enrollment requires secure authentication; simulation sign-in is not accepted.', 403)
        return g.api_user['user_id']

    @api.get('/enrollment')
    def enrollment_read():
        return jsonify(**service.state(get_db(), uid()), options=service.options())

    @api.put('/enrollment/sections/<section>')
    def enrollment_section(section):
        body = json_object(required={'revision', 'values'})
        return jsonify(service.write(get_db(), uid(), body['revision'], section, body['values']))

    @api.post('/enrollment/complete')
    def enrollment_complete():
        body = json_object(required={'revision'})
        return jsonify(service.write(get_db(), uid(), body['revision']))
