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
    def summary():
        return {'registrations':0,'contact_verified':0,'linked_accounts':0,
                'statuses':{},'neighbourhoods':{},'sources':{},'genders':{},'age_bands':{},
                'other_locations':{},'consent_versions':{},'survey_versions':{},
                'with_story_answers':0,'without_story_answers':0,'story_answer_count':0,
                'with_name':0,'with_email':0,'consent_recorded':0,'synthetic_test_registrations':0}
    totals=summary()
    def increment(group,key):
        group[key]=group.get(key,0)+1
    for row in rows:
        key=row['market_id']; item=counts.setdefault(key,summary())
        day=row['created_at'][:10]; daily[day]=daily.get(day,0)+1
        data=json.loads(cipher().decrypt(row['protected_data'].encode()))
        source=data.get('source','unknown'); item['sources'][source]=item['sources'].get(source,0)+1
        version=data.get('survey_version','unspecified')
        # Known deployment fixture only; do not classify ordinary users as tests
        # merely because their name or email contains the word "test".
        synthetic=source=='deployment-smoke-test'
        for group in (item,totals):
            group['registrations']+=1
            group['contact_verified']+=int(bool(row['contact_verified']))
            group['linked_accounts']+=int(bool(row.get('user_id')))
            group['synthetic_test_registrations']+=int(synthetic)
            increment(group['statuses'],row['status'])
            increment(group['genders'],data.get('gender') or 'not_recorded')
            increment(group['age_bands'],data.get('age_band') or 'not_recorded')
            increment(group['consent_versions'],data.get('consent_version') or 'not_recorded')
            increment(group['survey_versions'],version)
            if group is totals: increment(group['sources'],source)
            for n in data.get('neighbourhoods',[]): increment(group['neighbourhoods'],n)
            if data.get('other_location'): increment(group['other_locations'],data['other_location'])
            answers=data.get('answers',{})
            group['with_story_answers' if answers else 'without_story_answers']+=1
            group['story_answer_count']+=len(answers)
            group['with_name']+=int(bool(data.get('name','').strip()))
            group['with_email']+=int(bool(data.get('email')))
            group['consent_recorded']+=int(data.get('consent') is True and bool(data.get('consented_at')))
        for question,answer in data.get('answers',{}).items():
            group=surveys.setdefault(version+':'+question,{})
            group[str(answer)]=group.get(str(answer),0)+1
    states={r['id']:r['state'] for r in db.fetch_all(conn,'WaitlistMarket')}
    metadata={r['id']:r for r in markets()}
    for key,item in counts.items():
        item['city']=metadata.get(key,{}).get('city',key)
        item['launch_status']=states.get(key,'collecting')
        item['non_test_registrations']=item['registrations']-item['synthetic_test_registrations']
    return {'total_registrations':len(rows),'markets':counts,'daily_registrations_utc':daily,'survey_answers':surveys,
            'totals':totals,'non_test_registrations':len(rows)-totals['synthetic_test_registrations'],
            'synthetic_test_registrations':totals['synthetic_test_registrations'],
            'note':'Aggregate counts include test entries; non_test_registrations excludes the deployment-smoke-test source. Interest registrations, not verified people or active matching users. Age is an age band, gender is self-declared. Neighbourhood counts overlap. Names and emails are counted for completeness, not printed.'}
