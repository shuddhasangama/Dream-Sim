"""One-shot sandbox face comparison; never grants liveness or dating eligibility."""
import hashlib
import json
import os
import secrets
from datetime import datetime,timezone,timedelta
from flask import g,request,jsonify
import auth_sessions
import db
from bgv_app import Protection
from api_contract import ApiError,json_object
from signzy.client import Client,Config

VERSION='selfie-aadhaar-face-match-v1'
CONSENT='I consent to sharing my latest saved original selfie and Aadhaar portrait with Signzy for face comparison. No generated avatar is used. This sandbox comparison does not establish liveness or overall account approval. One comparison is allowed; uncertain results require support review.'
def stamp():return datetime.now(timezone.utc).isoformat()
def enabled():return os.getenv('DHASHU_FACE_MATCH_ENABLED')=='1' and os.getenv('SIGNZY_ENV','preproduction')=='preproduction'
def sources(conn,uid):
 selfie=db.fetch_one(conn,'AvatarJob',id=uid)
 if not selfie or not selfie.get('protected_selfie') or selfie['expires_at']<=stamp():selfie=None
 rows=db.fetch_all(conn,'DigiLockerSession',user_id=uid)
 rows=[r for r in rows if r['environment']=='preproduction']
 latest=max(rows,key=lambda r:r['created_at']) if rows else None
 if not latest or latest['state']!='complete' or not latest.get('protected_photo'):return selfie,None
 photo=Protection().open(latest['protected_photo'])
 if not photo.get('image_base64') or photo.get('image_expires_at','')<=stamp():return selfie,None
 return selfie,(latest,photo)
def view(conn,uid):
 r=db.fetch_one(conn,'FaceMatchJob',id=uid);selfie,reference=sources(conn,uid)
 result=Protection().open(r['protected_result']).get('summary',{}) if r and r.get('protected_result') else {}
 state=r['state'] if r else 'not_started'
 return {'enabled':enabled(),'state':state,'provider':'signzy','operation':'face_match','threshold':0.5,
  'face_match_passed':result.get('face_match_passed'),'match_percentage':result.get('match_percentage'),
  'liveness':'not_checked','sandbox':True,'reference_ready':bool(reference),'selfie_ready':bool(selfie),
  'can_request':enabled() and not r and bool(selfie and reference) and selfie['state']!='draft',
  'consent_version':VERSION,'consent_text':CONSENT,
  'message':{'not_started':'Face comparison has not been requested.','queued':'Face comparison queued.','submitting':'Comparing the original selfie with Aadhaar.',
   'matched':'Face matched · Liveness not checked.','not_matched':'Face did not match · Liveness not checked.',
   'unknown':'Comparison unavailable or outcome uncertain. Support review is needed; another paid call is blocked.',
   'deleted':'Face evidence removed. The comparison allowance is not reset.'}.get(state,'Face comparison pending.')}
def queue(conn,uid,body):
 if not enabled():raise ApiError('face_match_unavailable','Sandbox face comparison is not enabled.',503)
 if body.get('consent') is not True or body.get('consent_version')!=VERSION:raise ApiError('consent_required','Confirm Signzy face-comparison consent.')
 with auth_sessions.transaction(conn):
  if db._is_postgres_connection(conn):auth_sessions.sql(conn,'LOCK TABLE "FaceMatchJob" IN SHARE ROW EXCLUSIVE MODE')
  if db.fetch_one(conn,'FaceMatchJob',id=uid):raise ApiError('face_match_limit','Your comparison is already reserved. Refresh to see its result.',409)
  selfie,reference=sources(conn,uid)
  if not selfie or not reference or selfie['state']=='draft':raise ApiError('images_required','Reserve your avatar generation from the latest selfie and complete DigiLocker first.',409)
  session,photo=reference;original=Protection().open(selfie['protected_selfie'])['image']
  snapshot={'selfie':{'base64':original,'mime':'image/jpeg'},'aadhaar':{'base64':photo['image_base64'],'mime':photo['mime_type']}}
  db.insert_row(conn,'FaceMatchJob',{'id':uid,'state':'queued','protected_input':Protection().seal(snapshot),'protected_result':None,
   'selfie_sha256':selfie['selfie_sha256'],'digilocker_session_id':session['id'],'consent_version':VERSION,'consent_at':stamp(),
   'created_at':stamp(),'updated_at':stamp(),'expires_at':min(selfie['expires_at'],photo['image_expires_at'])})
def clear_in_transaction(conn,uid):
 import liveness_secure_service
 liveness_secure_service.clear(conn,uid)
 auth_sessions.sql(conn,'UPDATE "FaceMatchJob" SET state=?,protected_input=NULL,protected_result=NULL,updated_at=? WHERE id=?',('deleted',stamp(),uid))
 auth_sessions.sql(conn,'UPDATE "FaceImageLease" SET revoked=1,protected_images=? WHERE user_id=?',('',uid))

def clear(conn,uid):
 with auth_sessions.transaction(conn):
  clear_in_transaction(conn,uid)
def work_one(conn,client_factory=Client):
 cutoff=(datetime.now(timezone.utc)-timedelta(minutes=5)).isoformat()
 with auth_sessions.transaction(conn):
  auth_sessions.sql(conn,'UPDATE "FaceMatchJob" SET state=?,updated_at=? WHERE state=? AND updated_at<?',('unknown',stamp(),'submitting',cutoff))
  auth_sessions.sql(conn,'UPDATE "FaceMatchJob" SET protected_input=NULL WHERE expires_at<? AND state<>?',(stamp(),'submitting'))
 if not enabled():return False
 with auth_sessions.transaction(conn):
  r=auth_sessions.sql(conn,'SELECT * FROM "FaceMatchJob" WHERE state=? ORDER BY created_at LIMIT 1',('queued',)).fetchone()
  if not r:return False
  r=dict(r)
  if r['expires_at']<=stamp():auth_sessions.sql(conn,'UPDATE "FaceMatchJob" SET state=? WHERE id=?',('unknown',r['id']));return True
  claim=auth_sessions.sql(conn,'UPDATE "FaceMatchJob" SET state=?,updated_at=? WHERE id=? AND state=?',('submitting',stamp(),r['id'],'queued'))
  if claim.rowcount!=1:return False
 token=secrets.token_hex(32);lease_id=hashlib.sha256(token.encode()).hexdigest();evidence=None;summary={};state='unknown'
 try:
  images=Protection().open(r['protected_input'])
  with auth_sessions.transaction(conn):db.insert_row(conn,'FaceImageLease',{'id':lease_id,'user_id':r['id'],'protected_images':Protection().seal(images),'expires_at':(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat(),'revoked':0})
  origin=os.getenv('DHASHU_PUBLIC_API_ORIGIN','https://dream-sim-production.up.railway.app').rstrip('/')
  if origin!='https://dream-sim-production.up.railway.app':raise ValueError('Unapproved private-image origin')
  base=origin+'/sandbox/face-image/'+token+'/'
  def sink(value):
   nonlocal evidence
   evidence=value
  summary=client_factory(Config.from_env()).execute('face_match',{'firstImage':base+'selfie','secondImage':base+'aadhaar','threshold':0.5,'detectMask':[base+'selfie']},consent_confirmed=True,evidence_sink=sink)
  if summary.get('face_match_passed') is True:state='matched'
  elif summary.get('face_match_passed') is False:state='not_matched'
 except Exception:state='unknown'
 finally:
  with auth_sessions.transaction(conn):
   auth_sessions.sql(conn,'UPDATE "FaceImageLease" SET revoked=1,protected_images=? WHERE id=?',('',lease_id))
   auth_sessions.sql(conn,'UPDATE "FaceMatchJob" SET state=?,protected_result=?,updated_at=? WHERE id=? AND state=?',(state,Protection().seal({'summary':summary,'evidence':evidence}),stamp(),r['id'],'submitting'))
 return True
def register(api,get_db):
 def actor():
  if not request.headers.get('Authorization','').startswith('Bearer ') or not getattr(g,'auth_session',None):raise ApiError('authentication_required','Sign in through the app.',401)
  return g.api_user['user_id']
 @api.get('/profile/face-match')
 def face_match_read():return jsonify(view(get_db(),actor()))
 @api.post('/profile/face-match')
 def face_match_request():
  uid=actor();queue(get_db(),uid,json_object(required={'consent','consent_version'}));return jsonify(view(get_db(),uid))
 @api.get('/profile/liveness')
 def hosted_face_read():
  import liveness_secure_service as hosted
  return jsonify(hosted.view(get_db(),actor()))
 @api.post('/profile/liveness')
 def hosted_face_request():
  import liveness_secure_service as hosted
  uid=actor();hosted.queue_create(get_db(),uid,json_object(required={'consent','consent_version'}));return jsonify(hosted.view(get_db(),uid))
 @api.post('/profile/liveness/complete')
 def hosted_face_complete():
  import liveness_secure_service as hosted
  uid=actor();body=json_object(required={'session_id'})
  hosted.queue_get(get_db(),uid,body['session_id']);return jsonify(hosted.view(get_db(),uid))
