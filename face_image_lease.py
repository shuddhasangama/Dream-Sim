"""Sandbox-only, operator-created expiring image links. No upload/mint API."""
import base64
import hashlib
import io
import os
from datetime import datetime, timezone
from flask import send_file, abort
import db
import auth_sessions
from bgv_app import Protection

def purge(conn):
 with auth_sessions.transaction(conn):
  auth_sessions.sql(conn,'UPDATE "FaceImageLease" SET protected_images=?,revoked=1 WHERE expires_at<? AND protected_images<>?',('',datetime.now(timezone.utc).isoformat(),''))

def register(app,get_db):
 @app.get('/sandbox/face-image/<token>/<kind>')
 def sandbox_face_image(token,kind):
  if os.getenv('SIGNZY_ENV','preproduction')!='preproduction' or len(token)!=64 or any(c not in '0123456789abcdef' for c in token) or kind not in ('selfie','aadhaar','avatar'):abort(404)
  lease=db.fetch_one(get_db(),'FaceImageLease',id=hashlib.sha256(token.encode()).hexdigest())
  if not lease or lease['revoked'] or lease['expires_at']<=datetime.now(timezone.utc).isoformat():abort(404)
  image=Protection().open(lease['protected_images']).get(kind)
  if not image:abort(404)
  response=send_file(io.BytesIO(base64.b64decode(image['base64'],validate=True)),mimetype=image['mime'],max_age=0)
  response.headers['Cache-Control']='no-store, private';response.headers['X-Content-Type-Options']='nosniff';response.headers['Referrer-Policy']='no-referrer'
  return response
