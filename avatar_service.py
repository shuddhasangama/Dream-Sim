"""Owner-bound, one-shot avatar jobs. Original selfie never becomes public."""
import base64
import hashlib
import io
import json
import os
import urllib.request
from datetime import datetime, timezone, timedelta
from PIL import Image, ImageOps
from flask import g, request, jsonify
import auth_sessions
import db
from bgv_app import Protection
from api_contract import ApiError, json_object

VERSION='selfie-avatar-v1'
CONSENT='I consent to sending only my latest captured selfie to OpenAI to generate two fictional avatar options. My Aadhaar/PAN images and identity details will not be sent. I understand there is one generation run per account, including failed or uncertain requests. When I accept an avatar it can appear on my profile, to my matches and in comparisons, marked Verification pending. This does not prove liveness, identity or anonymity.'
PROMPT='Create one fictional adult profile avatar as a bold, polished editorial illustration. Use the supplied consenting adult selfie only for broad non-identifying inspiration. Invent facial geometry and distinctive details; do not reproduce a recognizable face, marks, text or the background. Warm cream background, friendly expression, shoulders-up, tasteful clothing, simple graphic shapes, no text. Each output should offer a distinct fictional design. Do not infer ethnicity, personality or sensitive traits. This is not identity evidence and does not guarantee anonymity.'
MODEL='gpt-image-2'

def stamp():return datetime.now(timezone.utc).isoformat()
def enabled():return os.getenv('DHASHU_AVATAR_ENABLED')=='1'
def row(conn,uid):return db.fetch_one(conn,'AvatarJob',id=uid)
def normalize(raw):
    if not raw or len(raw)>12_000_000:raise ValueError('Image too large')
    with Image.open(io.BytesIO(raw)) as im:
        if im.format not in ('JPEG','PNG','WEBP') or im.width*im.height>20_000_000 or min(im.size)<100:raise ValueError('Invalid image')
        im=ImageOps.exif_transpose(im).convert('RGB');im.thumbnail((1024,1024));out=io.BytesIO();im.save(out,'JPEG',quality=85);return out.getvalue()
def data_url(raw):return 'data:image/jpeg;base64,'+base64.b64encode(raw).decode()
def public(conn,uid):
    r=row(conn,uid)
    return {'photo':Protection().open(r['protected_selected'])['photo'],'avatar':True,'avatar_status':'Verification pending'} if r and r.get('protected_selected') else {}
def view(conn,uid):
    r=row(conn,uid) or {};options=[]
    if r.get('protected_options') and r.get('expires_at','')>stamp():
        options=Protection().open(r['protected_options'])['options']
    import liveness_secure_service as hosted
    verified_selfie=hosted.selfie(conn,uid) if hosted.enabled() and (not r or r['state']=='draft') else None
    return {'verified_selfie_preview':verified_selfie,'enabled':enabled(),'state':r.get('state','not_started'),'consent_version':VERSION,'consent_text':CONSENT,
        'options':options,'selected':r.get('selected_index'),'avatar':public(conn,uid),'verification':'pending',
        'can_capture':enabled() and r.get('state','draft')=='draft','can_generate':enabled() and r.get('state')=='draft' and bool(r.get('protected_selfie')),
        'message':{'queued':'Two avatars are queued. Refresh to check progress.','submitting':'Generating two avatars. No retry is needed.',
          'unknown':'The outcome needs support review. Another paid run is blocked.','deleted':'Images removed. The generation allowance is not reset.',
          'expired':'Private images expired. The generation allowance is not reset.'}.get(r.get('state'),'Choose one avatar after generation. Signzy verification is pending.')}
def capture(conn,uid,image):
    if not enabled():raise ApiError('avatar_disabled','Avatar generation is not enabled yet.',503)
    if not isinstance(image,str) or len(image)>2_800_000 or not image.startswith(('data:image/jpeg;base64,','data:image/png;base64,','data:image/webp;base64,')):raise ApiError('invalid_image','Use a selfie under 2 MB.')
    try:
        raw=base64.b64decode(image.split(',',1)[1],validate=True)
        if len(raw)>2_000_000:raise ValueError()
        raw=normalize(raw)
    except Exception:raise ApiError('invalid_image','Use a readable JPEG, PNG or WebP selfie under 2 MB.') from None
    with auth_sessions.transaction(conn):
        if db._is_postgres_connection(conn):auth_sessions.sql(conn,'LOCK TABLE "AvatarJob" IN SHARE ROW EXCLUSIVE MODE')
        r=row(conn,uid)
        if r and r['state']!='draft':raise ApiError('avatar_limit','Your generation run is already reserved. Another capture cannot reset it.',409)
        value={'id':uid,'state':'draft','protected_selfie':Protection().seal({'image':base64.b64encode(raw).decode()}),
            'selfie_sha256':hashlib.sha256(raw).hexdigest(),'created_at':r['created_at'] if r else stamp(),'updated_at':stamp(),
            'expires_at':(datetime.now(timezone.utc)+timedelta(days=30)).isoformat()}
        if r:value={**r,**value}
        db.insert_row(conn,'AvatarJob',value)
def queue(conn,uid,body):
    if not enabled():raise ApiError('avatar_disabled','Avatar generation is not enabled yet.',503)
    if body.get('consent') is not True or body.get('consent_version')!=VERSION:raise ApiError('consent_required','Confirm avatar consent first.')
    with auth_sessions.transaction(conn):
        r=row(conn,uid)
        if not r or not r.get('protected_selfie'):raise ApiError('selfie_required','Capture your latest selfie first.',409)
        if r['state']!='draft':raise ApiError('avatar_limit','Only one run of two avatars is allowed. Refresh to see the existing result.',409)
        changed=auth_sessions.sql(conn,'UPDATE "AvatarJob" SET state=?, consent_version=?, consent_at=?, updated_at=? WHERE id=? AND state=?',('queued',VERSION,stamp(),stamp(),uid,'draft'))
        if changed.rowcount!=1:raise ApiError('avatar_limit','Your run is already reserved.',409)
def accept(conn,uid,index):
    if type(index)is not int or index not in (0,1):raise ApiError('invalid_choice','Choose one of the two avatars.')
    with auth_sessions.transaction(conn):
        r=row(conn,uid)
        if not r or r['state'] not in ('ready','accepted') or not r.get('protected_options') or r['expires_at']<=stamp():raise ApiError('not_ready','Avatar options are not available.',409)
        options=Protection().open(r['protected_options'])['options']
        auth_sessions.sql(conn,'UPDATE "AvatarJob" SET state=?, selected_index=?, protected_selected=?, updated_at=? WHERE id=?',
            ('accepted',index,Protection().seal({'photo':options[index]}),stamp(),uid))
def clear(conn,uid):
    with auth_sessions.transaction(conn):
        r=row(conn,uid)
        if r and r['state'] in ('queued','submitting'):raise ApiError('in_progress','Wait for generation to finish before deleting.',409)
        if r:auth_sessions.sql(conn,'UPDATE "AvatarJob" SET state=?,protected_selfie=NULL,protected_options=NULL,protected_selected=NULL,selected_index=NULL,updated_at=? WHERE id=?',('deleted',stamp(),uid))
        import face_match_service
        face_match_service.clear_in_transaction(conn,uid)
def generate(key,selfie):
    payload={'model':MODEL,'images':[{'image_url':data_url(selfie)}],'prompt':PROMPT,'n':2,'size':'1024x1024','quality':'low','output_format':'png',
             'safety_identifier':hashlib.sha256(selfie).hexdigest()}
    req=urllib.request.Request('https://api.openai.com/v1/images/edits',data=json.dumps(payload).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'},method='POST')
    with urllib.request.urlopen(req,timeout=240) as response:body=json.loads(response.read(48_000_000))
    if len(body.get('data',[]))!=2:raise ValueError('Incomplete output')
    return [data_url(normalize(base64.b64decode(item['b64_json'],validate=True))) for item in body['data']]
def work_one(conn,provider=generate):
    # Expiry removes original and unselected images, but never removes the once-only ledger.
    with auth_sessions.transaction(conn):
        auth_sessions.sql(conn,'UPDATE "AvatarJob" SET protected_selfie=NULL,protected_options=NULL,state=CASE WHEN protected_selected IS NULL THEN ? ELSE state END WHERE expires_at<? AND state NOT IN (?,?)',('expired',stamp(),'queued','submitting'))
        cutoff=(datetime.now(timezone.utc)-timedelta(minutes=10)).isoformat()
        auth_sessions.sql(conn,'UPDATE "AvatarJob" SET state=?,updated_at=? WHERE state=? AND updated_at<?',('unknown',stamp(),'submitting',cutoff))
    if not enabled() or not os.getenv('OPENAI_API_KEY'):return False
    with auth_sessions.transaction(conn):
        r=auth_sessions.sql(conn,'SELECT * FROM "AvatarJob" WHERE state=? ORDER BY created_at LIMIT 1',('queued',)).fetchone()
        if not r:return False
        r=dict(r)
        if r['expires_at']<=stamp():auth_sessions.sql(conn,'UPDATE "AvatarJob" SET state=?,protected_selfie=NULL WHERE id=?',('expired',r['id']));return True
        changed=auth_sessions.sql(conn,'UPDATE "AvatarJob" SET state=?,updated_at=? WHERE id=? AND state=?',('submitting',stamp(),r['id'],'queued'))
        if changed.rowcount!=1:return False
    # The committed claim prevents a crash or timeout from causing a paid replay.
    try:
        selfie=base64.b64decode(Protection().open(r['protected_selfie'])['image'])
        options=provider(os.environ['OPENAI_API_KEY'],selfie)
        if len(options)!=2:raise ValueError()
        protected=Protection().seal({'options':options});state='ready'
    except Exception:protected=None;state='unknown'
    with auth_sessions.transaction(conn):
        auth_sessions.sql(conn,'UPDATE "AvatarJob" SET state=?,protected_options=?,updated_at=? WHERE id=? AND state=?',(state,protected,stamp(),r['id'],'submitting'))
    return True
def register(api,get_db):
    def uid():
        if not request.headers.get('Authorization','').startswith('Bearer ') or not getattr(g,'auth_session',None):raise ApiError('authentication_required','Sign in through the app.',401)
        return g.api_user['user_id']
    @api.get('/profile/avatar')
    def avatar_read():return jsonify(view(get_db(),uid()))
    @api.post('/profile/avatar/selfie')
    def avatar_capture():
        request.max_content_length=2_900_000;who=uid();capture(get_db(),who,json_object(required={'image'})['image']);return jsonify(view(get_db(),who))
    @api.post('/profile/avatar/generate')
    def avatar_generate():
        who=uid();queue(get_db(),who,json_object(required={'consent','consent_version'}));return jsonify(view(get_db(),who))
    @api.post('/profile/avatar/accept')
    def avatar_accept():
        who=uid();accept(get_db(),who,json_object(required={'index'})['index']);return jsonify(view(get_db(),who))
    @api.delete('/profile/avatar')
    def avatar_delete():
        who=uid();clear(get_db(),who);return jsonify(view(get_db(),who))
