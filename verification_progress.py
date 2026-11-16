"""Read-only progress metadata. A transport success is never a verification date."""
import json
from datetime import datetime, timezone


def stalled(row, now=None):
    if row.get('state') not in ('processing','creating','retrieving'):
        return False
    try:
        updated=datetime.fromisoformat(row['updated_at'])
        if updated.tzinfo is None:updated=updated.replace(tzinfo=timezone.utc)
        return ((now or datetime.now(timezone.utc))-updated).total_seconds()>600
    except (ValueError,TypeError,KeyError):
        return False


def request_progress(row, protection):
    public=json.loads(row.get('summary_json') or '{}')
    evidence=protection.open(row['protected_result']) if row.get('protected_result') else {}
    received=evidence.get('finished_at_utc')
    verified=public.get('verified_at') if row['state']=='verified' else None
    field_states=public.get('fields') or {}
    fields={key:{'status':state,'received_at':received,
                 'verified_at':public.get('field_verified_at',{}).get(key) if state=='verified' else None}
            for key,state in field_states.items()}
    result={'received_at':received,'verified_at':verified,'field_verifications':fields,
            'recovery_required':stalled(row),'can_resubmit':False}
    if result['recovery_required']:
        result['message']='This check was interrupted. Saved progress is retained; support must reconcile the provider result before retrying.'
    elif row['state']=='outcome_unknown':
        result['recovery_required']=True
        result['message']='The provider outcome is uncertain. Support must check it before another request is sent.'
    return result


def record_dates(public,state,when):
    """Called when an outcome is evaluated, not whenever a page is refreshed."""
    if state=='verified':public.setdefault('verified_at',when)
    else:public.pop('verified_at',None)
    public['field_verified_at']={key:public.get('field_verified_at',{}).get(key,when)
        for key,value in public.get('fields',{}).items() if value=='verified'}
