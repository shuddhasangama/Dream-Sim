"""Public interest registration; never creates accounts or opens matching."""
import hashlib
import hmac
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from cryptography.fernet import Fernet
import auth_sessions
import db
from api_contract import ApiError

CONSENT_VERSION = 'waitlist-v1'
CONSENT_TEXT = 'Save my details and optional story answers to plan the launch and email me about DhaShu early access. I can request deletion or withdraw.'

def stamp(): return datetime.now(timezone.utc).isoformat()

def cipher(): return Fernet(os.environ['WAITLIST_ENCRYPTION_KEY'].encode())

def digest(value):
    secret = os.environ['WAITLIST_HASH_KEY']
    if len(secret) < 32: raise ValueError('Waitlist hash key must have at least 32 characters')
    return hmac.new(secret.encode(),value.encode(),hashlib.sha256).hexdigest()

def markets():
    return json.loads(Path(os.getenv('WAITLIST_MARKETS_FILE') or Path(__file__).with_name('waitlist_markets.json')).read_text(encoding='utf-8'))

def configured():
    if os.getenv('DHASHU_WAITLIST_ENABLED') != '1':
        raise ApiError('waitlist_unavailable','The waitlist is temporarily unavailable. Please try later.',503)
    try: cipher(); digest('configuration-check')
    except (ValueError, KeyError):
        raise ApiError('waitlist_unavailable','The waitlist is temporarily unavailable. Please try later.',503) from None

def public_config(conn):
    configured()
    states={r['id']:r['state'] for r in db.fetch_all(conn,'WaitlistMarket')}
    return {'markets':[dict(r,launch_status=states.get(r['id'],'collecting')) for r in markets()],
            'max_neighbourhoods':3,'max_cities':1,'consent_version':CONSENT_VERSION,'consent_text':CONSENT_TEXT}

def submit(conn, body):
    configured()
    try:
        if not isinstance(body,dict) or set(body)-{'name','email','market_id','gender','age_band','neighbourhoods','answers','survey_version','source','consent','consent_version','website','other_location'}:
            raise ValueError()
        if body.get('website'): raise ValueError()
        email=body['email'].strip().casefold()
        if len(email)>254 or not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]{2,}',email): raise ValueError()
        if body.get('consent') is not True or body.get('consent_version')!=CONSENT_VERSION: raise ValueError()
        market=next(r for r in markets() if r['id']==body['market_id'])
        selected=body.get('neighbourhoods',[])
        if not isinstance(selected,list) or len(selected)>3 or any(not isinstance(x,str) for x in selected): raise ValueError()
        if len(set(selected))!=len(selected) or set(selected)-{r['id'] for r in market['neighbourhoods']}: raise ValueError()
        if body.get('gender') not in ('A woman','A man','Prefer not to say'): raise ValueError()
        if body.get('age_band') not in ('25–29','30–34','35–39','40–44','45–50','Over 50'): raise ValueError()
        for key,limit in [('name',120),('source',300),('survey_version',60),('other_location',160)]:
            if not isinstance(body.get(key,''),str) or len(body.get(key,''))>limit: raise ValueError()
        answers=body.get('answers',{})
        if not isinstance(answers,dict) or len(answers)>12: raise ValueError()
        for key,value in answers.items():
            if not re.fullmatch(r'[a-zA-Z0-9_-]{1,60}',key) or type(value) not in (str,int) or len(str(value))>100: raise ValueError()
    except (ValueError,KeyError,TypeError,AttributeError,StopIteration):
        raise ApiError('validation_error','Check your contact details, location choices and consent.') from None
    payload=dict(body,email=email,consent_text=CONSENT_TEXT,consented_at=stamp())
    payload.pop('website',None)
    with auth_sessions.transaction(conn):
        # Unconfirmed repeats must not overwrite another person's details or answers.
        auth_sessions.sql(conn,'INSERT INTO "WaitlistEntry" '
            '(id,contact_hash,market_id,status,contact_verified,protected_data,created_at) VALUES (?,?,?,?,?,?,?) '
            'ON CONFLICT (contact_hash) DO NOTHING',
            (str(uuid.uuid4()),digest('email:'+email),market['id'],'waiting',0,
             cipher().encrypt(json.dumps(payload).encode()).decode(),stamp()))
    return {'saved':True,'message':'Your interest is recorded. If you have already joined, your existing registration is kept.'}

def statistics(conn):
    rows=db.fetch_all(conn,'WaitlistEntry'); counts={}; daily={}; surveys={}
    for row in rows:
        key=row['market_id']; item=counts.setdefault(key,{'registrations':0,'contact_verified':0,'statuses':{},'neighbourhoods':{},'sources':{}})
        item['registrations']+=1; item['contact_verified']+=row['contact_verified']
        day=row['created_at'][:10]; daily[day]=daily.get(day,0)+1
        item['statuses'][row['status']]=item['statuses'].get(row['status'],0)+1
        data=json.loads(cipher().decrypt(row['protected_data'].encode()))
        for n in data.get('neighbourhoods',[]): item['neighbourhoods'][n]=item['neighbourhoods'].get(n,0)+1
        source=data.get('source','unknown'); item['sources'][source]=item['sources'].get(source,0)+1
        version=data.get('survey_version','unspecified')
        for question,answer in data.get('answers',{}).items():
            group=surveys.setdefault(version+':'+question,{})
            group[str(answer)]=group.get(str(answer),0)+1
    return {'total_registrations':len(rows),'markets':counts,'daily_registrations_utc':daily,'survey_answers':surveys,
            'note':'Interest registrations, not verified people or active matching users. Neighbourhood counts overlap.'}
