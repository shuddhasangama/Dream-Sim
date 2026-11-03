"""Cache one consented original document portrait, encrypted and server-only.

File retrieval is a single bounded GET, never a new DigiLocker API submission.
No AI processing, liveness claim or public photo delivery happens here.
"""
import base64
import hashlib
import io
import urllib.request
from datetime import datetime,timezone,timedelta
from PIL import Image,UnidentifiedImageError
import auth_sessions
from bgv_app import Protection
from signzy.client import NoRedirect
from signzy.document_photo import reference
MAX_BYTES=2_000_000

def download(url):
    if not reference({'result':{'photo':url}}):raise ValueError('Unsupported document photo host')
    opener=urllib.request.build_opener(NoRedirect())
    with opener.open(urllib.request.Request(url,headers={'Accept':'image/jpeg,image/png,image/webp'}),timeout=12) as response:
        if response.status!=200:raise ValueError('Photo unavailable')
        raw=response.read(MAX_BYTES+1)
    if not raw or len(raw)>MAX_BYTES:raise ValueError('Invalid image size')
    try:
        with Image.open(io.BytesIO(raw)) as image:
            if image.format not in ('JPEG','PNG','WEBP') or image.width*image.height>20_000_000 or min(image.size)<1:raise ValueError('Unsupported image')
            fmt=image.format;image.verify()
    except (OSError,UnidentifiedImageError,Image.DecompressionBombError) as exc:raise ValueError('Invalid portrait image') from exc
    return {'image_base64':base64.b64encode(raw).decode(),'mime_type':{'JPEG':'image/jpeg','PNG':'image/png','WEBP':'image/webp'}[fmt],
            'image_sha256':hashlib.sha256(raw).hexdigest()}

def cache(conn,row):
    if row['state']!='complete' or row['consent_version'] not in ('digilocker-identity-photo-v2','digilocker-screening-v3') or not row.get('protected_photo'):return False
    protection=Protection();photo=protection.open(row['protected_photo'])
    if photo.get('download_attempted_at') or photo.get('image_base64'):return False
    if not reference({'result':{'photo':photo.get('url')}}):return False
    claimed={**photo,'download_attempted_at':datetime.now(timezone.utc).isoformat(),'download_state':'retrieving'}
    protected_claim=protection.seal(claimed)
    with auth_sessions.transaction(conn):
        changed=auth_sessions.sql(conn,'UPDATE "DigiLockerSession" SET protected_photo=? WHERE id=? AND user_id=? AND state=? AND protected_photo=?',
            (protected_claim,row['id'],row['user_id'],'complete',row['protected_photo']))
        if changed.rowcount!=1:return False
    # Claim committed before external IO. An interrupted/failed download is not replayed.
    try:result={**claimed,**download(photo['url']),'download_state':'received','image_expires_at':(datetime.now(timezone.utc)+timedelta(days=30)).isoformat()}
    except Exception:result={**claimed,'download_state':'unavailable'}
    with auth_sessions.transaction(conn):
        auth_sessions.sql(conn,'UPDATE "DigiLockerSession" SET protected_photo=? WHERE id=? AND user_id=? AND protected_photo=?',
            (protection.seal(result),row['id'],row['user_id'],protected_claim))
    return result['download_state']=='received'

def purge_expired(conn):
    import db
    protection=Protection();removed=0
    for row in db.fetch_all(conn,'DigiLockerSession'):
        if not row.get('protected_photo'):continue
        photo=protection.open(row['protected_photo'])
        if not photo.get('image_base64') or not photo.get('image_expires_at') or datetime.fromisoformat(photo['image_expires_at'])>datetime.now(timezone.utc):continue
        for key in ('image_base64','mime_type','image_sha256'):photo.pop(key,None)
        photo['download_state']='expired'
        with auth_sessions.transaction(conn):
            changed=auth_sessions.sql(conn,'UPDATE "DigiLockerSession" SET protected_photo=? WHERE id=? AND protected_photo=?',
                (protection.seal(photo),row['id'],row['protected_photo']))
            removed+=changed.rowcount
    return removed
