"""gzip for JSON responses (c-scale-budget).

DHASHU_GZIP=1 enables it (default 0: Railway's edge may already compress; turn
it on only if measurement shows uncompressed JSON reaching clients). Only
successful JSON bodies larger than 1 KB are compressed, only when the client
sends Accept-Encoding: gzip, and never twice. Register FIRST so that Flask (which
runs after_request hooks in reverse order) runs it LAST, after the API envelope.
"""
import gzip
import os

from flask import request

MIN_BYTES = 1024


def enabled():
    return os.environ.get('DHASHU_GZIP', '0') == '1'


def register(app):
    @app.after_request
    def gzip_json(response):
        if not enabled() or response.direct_passthrough or response.status_code != 200:
            return response
        if response.mimetype != 'application/json' or response.headers.get('Content-Encoding'):
            return response
        if 'gzip' not in request.headers.get('Accept-Encoding', '').lower():
            return response
        body = response.get_data()
        if len(body) < MIN_BYTES:
            return response
        response.set_data(gzip.compress(body, compresslevel=5))
        response.headers['Content-Encoding'] = 'gzip'
        response.headers['Content-Length'] = str(len(response.get_data()))
        vary = response.headers.get('Vary')
        if not vary or 'accept-encoding' not in vary.lower():
            response.headers['Vary'] = (vary + ', ' if vary else '') + 'Accept-Encoding'
        return response
