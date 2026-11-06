"""Employment-history evidence for the app's existing employment check slot."""
from datetime import date,datetime
import re
import db
from signzy.verification import normalized

def inputs(conn,uid,identity,details):
    if details and details.get('pan') and normalized(details.get('name') or '')==normalized(identity['name']):
        return {'pan':details['pan']}
    account=db.fetch_one(conn,'Account',user_id=uid)
    if account and account.get('auth_enabled') and account.get('verified_phone'):
        phone=str(account.get('phone') or '')
        mobile=phone[3:] if phone.startswith('+91') else phone
        if re.fullmatch(r'[6-9][0-9]{9}',mobile):return {'mobile':mobile}
    return None

def parsed(value):
    if not isinstance(value,str) or not value.strip():return None
    for fmt in ('%d-%b-%Y','%Y-%m-%d'):
        try:return datetime.strptime(value.strip(),fmt).date()
        except ValueError:pass
    return None

def assess(body,declared):
    records=body.get('result') if isinstance(body,dict) else None
    if not isinstance(records,list) or any(not isinstance(r,dict) for r in records):
        return 'unavailable',{'message':'Employment response could not be interpreted.'}
    if not records:return 'not_confirmed',{'message':'No employment records returned. This does not establish unemployment.'}
    expected=declared.get('name')
    if not expected or any(not isinstance(r.get('name'),str) or normalized(r['name'])!=normalized(expected) for r in records):
        return 'employment_mismatch',{'fields':{'employer':'unverified'},'message':'Employment records could not be linked to your Aadhaar name. No employer is confirmed.'}
    # Never match fatherOrHusbandName to the member's identity.
    if any(not isinstance(r.get('establishmentName'),str) or not r['establishmentName'].strip() for r in records):
        return 'unavailable',{'message':'Employment records are incomplete.'}
    starts=[parsed(r.get('dateOfJoining')) for r in records]
    if any(d is None or d>date.today() for d in starts):
        return 'needs_review',{'message':'Employment record dates need review.'}
    recent=records[max(range(len(records)),key=lambda i:starts[i])]
    start=parsed(recent.get('dateOfJoining'));raw_exit=recent.get('dateOfExit');end=parsed(raw_exit)
    if raw_exit and (not end or end<start or end>date.today()):
        return 'needs_review',{'message':'Employment record dates need review.'}
    employer=' '.join(recent['establishmentName'].split())[:200]
    record={'employer':employer,'date_of_joining':start.isoformat(),'date_of_exit':end.isoformat() if end else None,'current_employment_confirmed':False}
    expected_employer=declared.get('employer') or ''
    if expected_employer and normalized(expected_employer)!=normalized(employer):
        return 'employment_mismatch',{'employment_record':record,'fields':{'employer':'unverified'},'message':f'Latest recorded employer: {employer}. It differs from your declared employer; current employment is not confirmed.'}
    if end:
        from bgv_result_policy import duration
        record['duration_days']=(end-start).days
        message=f'Last recorded employer: {employer} ({start:%d %b %Y} to {end:%d %b %Y}; {duration(start,end)}). This does not establish your current employment status.'
    else:
        message=f'Employment record found: {employer}, joined {start:%d %b %Y}. No exit is recorded; current employment is not independently confirmed.'
    return 'history_available',{'employment_record':record,'fields':{'employer':'unverified'},'message':message}
