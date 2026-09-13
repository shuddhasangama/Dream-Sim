"""Shared JSON boundary helpers; no Flask app or persistence at import time."""
from flask import request


class ApiError(Exception):
    def __init__(self, code, message, status=400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def json_object(*, required=(), optional=()):
    """Reject ambiguous bodies/unknown fields before any service mutation."""
    if not request.is_json:
        raise ApiError('unsupported_media_type', 'Use application/json.', 415)
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise ApiError('validation_error', 'Body must be a JSON object.')
    if not set(required) <= body.keys() or body.keys() - set(required) - set(optional):
        raise ApiError('validation_error', 'Expected required fields: ' +
                       ', '.join(sorted(required)) + '; optional fields: ' +
                       ', '.join(sorted(optional)))
    return body


def allowlist(row, fields):
    """Never serialize an entire database row across the JSON boundary."""
    return None if row is None else {key: row[key] for key in fields}
