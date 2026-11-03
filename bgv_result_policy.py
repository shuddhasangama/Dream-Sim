"""Product rules for individual check outcomes; never overall member approval."""
import calendar
from datetime import date
import db

def legal(conn,row,summary,protection):
    parent=db.fetch_one(conn,'BgvRequest',id=row.get('parent_request_id'),user_id=row['user_id']) if row.get('parent_request_id') else None
    mode=None
    if parent and parent['operation']=={'individual_result':'individual_search','fir_result':'fir_search'}[row['operation']] and parent['environment']==row['environment'] and parent.get('case_check_id')==row.get('case_check_id'):
        source=protection.open(parent['protected_input'])
        snapshot=protection.open(row['protected_input'])
        if snapshot.get('source_request_id')==parent['id']:
            mode=source['inputs'].get('matchType')
            if row['operation']=='individual_result' and source['inputs'].get('caseCategory')!='criminal':mode=None
    count=summary.get('cases_returned') if row['operation']=='individual_result' else summary.get('candidates_returned')
    public={'processing_complete':summary.get('processing_complete',False),'candidate_count':count,'match_type':mode}
    if summary['outcome']=='accepted_pending_confirmation':return 'pending',{**public,'message':'The provider is still processing this check.'}
    if mode!='exact':return 'not_confirmed',{**public,'message':'This was a previous possible-match search. A fresh exact search is required.'}
    if not summary.get('completion_confirmed') or type(count)is not int:
        return 'unavailable',{**public,'message':'The provider has not supplied a confirmed completed exact result. Support needs to check the response.'}
    if count>0:return 'needs_review',{**public,'message':f'Exact search returned {count} case candidate(s). Review is required before this check can be verified.'}
    if summary.get('provider_count_discrepancy'):
        return 'unavailable',{**public,'message':'The provider case counts disagree. An exact zero-case result has not been confirmed.'}
    return 'verified',{**public,'message':'Verified: completed exact search returned zero cases.'}

def parsed_date(value):
    try:return date.fromisoformat(value) if isinstance(value,str) else None
    except ValueError:return None

def duration(start,end):
    months=(end.year-start.year)*12+end.month-start.month
    def anchor(n):
        year=start.year+(start.month-1+n)//12;month=(start.month-1+n)%12+1
        return date(year,month,min(start.day,calendar.monthrange(year,month)[1]))
    if anchor(months)>end:months-=1
    years,months_left=divmod(months,12);days=(end-anchor(months)).days
    return ', '.join(f'{n} {unit}'+('s' if n!=1 else '') for n,unit in ((years,'year'),(months_left,'month'),(days,'day')) if n) or '0 days'

def employment(body,summary,comparison_state):
    if summary.get('result_code')!=200:return 'unavailable',{'message':'Employment data is unavailable from this source.'}
    data=body.get('employmentSummary',{}) if isinstance(body,dict) else {}
    recent=data.get('recent_employer_data') or {};recent=recent if isinstance(recent,dict) else {}
    name=recent.get('establishment_name');name=' '.join(name.split())[:200] if isinstance(name,str) else None
    start=parsed_date(recent.get('date_of_joining'));end=parsed_date(recent.get('date_of_exit'))
    history={'employer':name,'date_of_joining':start.isoformat() if start else None,'date_of_exit':end.isoformat() if end else None,
             'current_employment_confirmed':summary.get('is_employed') is True and comparison_state=='verified'}
    if comparison_state=='verified':return 'verified',{'employment_record':history,'message':f'Current employer confirmed by this source: {name or "declared employer"}.'}
    if name and summary.get('is_employed') is False:
        period=f' ({start:%d %b %Y} to {end:%d %b %Y}; {duration(start,end)})' if start and end and end>=start else ''
        if start and end and end>=start:history['duration_days']=(end-start).days
        return 'history_available',{'employment_record':history,'message':f'Last recorded employer: {name}{period}. This historical record does not establish your current employment status.'}
    if name and summary.get('is_employed') is True:
        return 'employment_mismatch',{'employment_record':history,'message':f'The source reports {name}; it does not confirm your declared current employer.'}
    return 'not_confirmed',{'employment_record':history,'message':'No current employer was confirmed by this source. This does not mean you are not working.'}
