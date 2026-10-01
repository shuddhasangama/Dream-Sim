"""Explicit profile choices. No diagnosis, ethnicity filtering or inferred health state."""
import base64
import io
import json
from PIL import Image, ImageOps, UnidentifiedImageError
import db
import vision
from api_contract import ApiError

TEMPLATES = [
 {'key':'grow','label':'Grow Together','description':'Build a shared life with children in the picture.','choices':{'Intimacy':['Emotional','Physical'],'Kids':['Naturally'],'Cohabitate':['Chores split','Expenses sharing']},'kids_intent':'want'},
 {'key':'two','label':'Two Together','description':'Build a shared life without having additional children.','choices':{'Intimacy':['Emotional'],'Cohabitate':['Chores split','Expenses sharing'],'Travel together':[]},'kids_intent':'no'},
 {'key':'explore','label':'Explore Together','description':'Connection and travel; children and cohabitation remain undecided.','choices':{'Intimacy':['Emotional'],'Travel together':[]},'kids_intent':'undecided'},
 {'key':'custom','label':'BYOB — Build Your Own Base','description':'Choose your own pillars and preferences.','choices':None,'kids_intent':'undecided'},
]
HEALTH = {'mobility':'Mobility disability / wheelchair use','physical':'Other physical disability','sensory':'Sensory disability','non_visible':'Non-visible disability','diabetes':'Diabetes','cancer':'Cancer / cancer history','trauma':'Trauma / mental health history','other':'Other health or accessibility needs'}

def template_label(stats, goals):
    key=stats.get('vision_template','custom')
    item=next((t for t in TEMPLATES if t['key']==key),TEMPLATES[-1])
    current={g['key']:sorted(g.get('stance') or []) for g in goals}
    if item['choices'] is not None and current!={k:sorted(v) for k,v in item['choices'].items()}:
        return 'BYOB — customised Vision'
    return item['label']

def health_fits(a,b):
    """Only consented disclosures are considered; missing is explicitly unknown."""
    prefs=a.get('preferences',{}).get('health_openness',{})
    if prefs.get('mode')!='specific': return True
    declared=b.get('stats',{}).get('health_shared',{})
    if not declared.get('consent') or not declared.get('categories'): return prefs.get('include_undisclosed',True)
    return set(declared.get('categories',[])) <= set(prefs.get('categories',[]))

def validate(body):
    cats=body.get('categories',[])
    accepted=body.get('open_categories',[])
    for values in (cats,accepted):
        if type(values) is not list or any(type(v) is not str or v not in HEALTH for v in values) or len(values)!=len(set(values)):
            raise ApiError('validation_error','Choose listed health/accessibility categories only.')
    for key in ('share_health','include_undisclosed'):
        if type(body.get(key)) is not bool: raise ApiError('validation_error',key+' must be true or false.')
    mode=body.get('openness','any')
    if mode not in ('any','specific'): raise ApiError('validation_error','Choose an openness option.')
    note=body.get('note','')
    if type(note) is not str or len(note)>500: raise ApiError('validation_error','Use at most 500 characters for your note.')
    if not body['share_health'] and (cats or note.strip()):
        raise ApiError('validation_error','Consent to share these details, or clear them before saving.')
    return {'consent':body['share_health'],'categories':cats,'note':note.strip()}, {'mode':mode,'categories':accepted if mode=='specific' else [],'include_undisclosed':body['include_undisclosed']}

def photo(data):
    if data is None: return None
    if type(data) is not str or len(data)>2800000 or not data.startswith(('data:image/jpeg;base64,','data:image/png;base64,','data:image/webp;base64,')):
        raise ApiError('validation_error','Choose a JPEG, PNG or WebP photo up to 2 MB.')
    try:
        raw=base64.b64decode(data.split(',',1)[1],validate=True)
        if len(raw)>2000000: raise ValueError()
        with Image.open(io.BytesIO(raw)) as src:
            if src.width*src.height>20000000 or min(src.size)<160: raise ValueError()
            im=ImageOps.exif_transpose(src).convert('RGB')
            # Strip metadata and standardise dimensions. Client lets the user choose crop.
            im=ImageOps.fit(im,(480,600))
            out=io.BytesIO(); im.save(out,format='JPEG',quality=85)
        return 'data:image/jpeg;base64,'+base64.b64encode(out.getvalue()).decode()
    except (ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError):
        raise ApiError('validation_error','Photo could not be read. Use a clear image between 160 pixels and 20 megapixels.')

def public_profile(conn, user):
    stats=user['stats']; shared=stats.get('health_shared',{})
    pic=db.fetch_one(conn,'ProfilePhoto',id=user['user_id'])
    row=db.fetch_one(conn,'User',id=user['user_id'])
    skills=db.load_json_field(row.get('skills_json'),{}).get('activities',{})
    return {'vision_template':template_label(stats,user['visions']), 'kids_intent':stats.get('kids_intent','undecided'),
      'ethnicity':stats.get('ethnicity',[]), 'health':shared if shared.get('consent') else None,
      'health_labels':HEALTH,'photo':pic['data_url'] if pic else None,
      'activities':skills}
