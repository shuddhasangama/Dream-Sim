"""Consent-first Guru conversations. Structured guidance with opt-in private AI narration.

Private notes never enter a shared discussion. Every read rechecks membership
and account binding; reassigned beta profiles cannot inherit previous notes.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
import uuid
import time
import guru_provider
from flask import g, jsonify, request
import db
from auth_sessions import sql, transaction
from planning_service import save
from identity_capture import account_binding
from api_contract import ApiError, json_object

TOPICS = {
    'intentions': ('Agree on your next step', ['What would another date help you understand?', 'What pace feels comfortable to each of you?', 'Discussing is not acceptance. Return to Debrief to choose another date or end the pairing.']),
    'values': ('What matters to you?', ['Which value matters most to you?', 'What would that look like in everyday life?', 'What would you like to ask a potential match?']),
    'matching': ('How matching works', ['Matching uses reciprocal preferences. Only mutual interest creates a pair. What would you like to understand?', 'Which preference would you like to review?']),
    'match': ('Get to know this match', ['What would you like to learn about this person?', 'How could you ask that without assuming their answer?']),
    'planning': ('Plan your date together', ['What time, budget or setting would feel comfortable?', 'What flexibility would you like to offer?']),
    'agreement': ('Know what you’re agreeing to', ['Which part of the date plan would you like to clarify?', 'What would you like to ask before signing?']),
    'prepare': ('Prepare for your date', ['What shared interest would you enjoy talking about?', 'What boundary or practical detail would help you feel comfortable?']),
    'reflect': ('Reflect on your date', ['What felt good, and what gave you pause?', 'What would you like to do next, at your own pace?']),
    'build': ('Build on your last date', ['What would you like to repeat or change?', 'What would you like to ask your partner about another date?']),
    'next': ('Talk about what matters next', ['What does the next stage mean to you?', 'What would you like to understand about your partner’s expectations?']),
    'pace': ('Take your next step at your pace', ['What pace feels comfortable to you?', 'What would you need before making a decision?']),
    'sharing': ('Share at your pace', ['What are you considering sharing: phone, socials or a home invitation?', 'Each needs separate consent. What boundary would you like to communicate?']),
    'differences': ('Air and resolve differences', ['What happened, from your perspective?', 'How did it affect you?', 'What specific change would you like to ask for?']),
    'mediate': ('Talk it through together', ['What would you like each other to understand?', 'Would you like to invite your partner to a shared conversation?']),
    'expenses': ('Manage expenses', ['What spending or saving decision would you like to discuss?', 'What feels affordable and fair to you?', 'What arrangement would you like to propose?']),
    'romance': ('Keep romance alive', ['What helps you feel connected?', 'What small shared activity would you enjoy?', 'What would you like to invite your partner to try?']),
}
STAGES = {
    'matching': ['values', 'matching'], 'match_available': ['match', 'matching'],
    'planning': ['planning', 'sharing'], 'repeat_planning': ['build', 'planning', 'sharing'],
    'agreement': ['agreement', 'sharing'], 'before_date': ['prepare', 'agreement', 'sharing'],
    'debrief': ['reflect', 'sharing'], 'post_debrief': ['build', 'pace', 'sharing'],
    'next_step_agreement': ['intentions','sharing'],
    'gate': ['next','pace','sharing'],
    'relationship': ['differences', 'mediate', 'expenses', 'romance', 'next', 'sharing'],
}
SHARED_TOPICS = {'intentions', 'planning', 'sharing', 'build', 'next', 'differences', 'mediate', 'expenses', 'romance'}


def cipher():
    from cryptography.fernet import Fernet
    try:
        return Fernet(os.environ.get('DHASHU_GURU_ENCRYPTION_KEY', '').encode('ascii'))
    except (ValueError, UnicodeError):
        raise ApiError('guru_unavailable', 'Secure Guru storage is not configured.', 503) from None


def pack(value):
    return cipher().encrypt(json.dumps(value, ensure_ascii=False).encode('utf-8')).decode('ascii')


def unpack(value):
    from cryptography.fernet import InvalidToken
    try:
        return json.loads(cipher().decrypt(value.encode('ascii')))
    except (InvalidToken, ValueError):
        raise ApiError('guru_unavailable', 'Guru history cannot be opened. Contact support.', 503) from None


def enabled():
    return os.environ.get('DHASHU_GURU_ENABLED', '0').lower() in ('1', 'true')


def text(value, limit=800):
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit or any(ord(c)<32 and c not in '\n\t' for c in value):
        raise ApiError('validation_error', f'Enter 1–{limit} characters.')
    return value.strip()


def stamp():
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def write(conn):
    with transaction(conn):
        if db._is_postgres_connection(conn):
            # Same membership locks as planning; serialize confirmations and edits.
            sql(conn, 'LOCK TABLE "User", "LockIn", "Couple", "Exit", "Account", "GuruPrivate", "GuruDiscussion" IN SHARE ROW EXCLUSIVE MODE')
        yield


def private(conn, uid):
    row = db.fetch_one(conn, 'GuruPrivate', id=uid)
    if row and row['binding'] == account_binding(conn, uid):
        return unpack(row['payload'])
    return {'history': [], 'memories': [], 'remember': False, 'receipts': []}


def save_private(conn, uid, value):
    save(conn, 'GuruPrivate', {'id':uid, 'binding':account_binding(conn, uid), 'payload':pack(value)})


def active_scope(conn, uid):
    user = db.fetch_one(conn, 'User', id=uid)
    if not user or user['bgv_status'] != 'verified':
        return None
    if user['journey_state'] == 'dating':
        rows = sql(conn, 'SELECT * FROM "LockIn" WHERE (user_a=? OR user_b=?) AND status=?', (uid,uid,'active')).fetchall()
        return ('dating', dict(rows[0]), 'user_a', 'user_b') if len(rows)==1 else None
    rows = sql(conn, 'SELECT * FROM "Couple" WHERE partner_a_id=? OR partner_b_id=?', (uid,uid)).fetchall()
    rows = [dict(r) for r in rows if r['stage']==user['journey_state'] and not db.fetch_all(conn,'Exit',couple_id=r['id'])]
    return ('couple', rows[0], 'partner_a_id', 'partner_b_id') if len(rows)==1 else None


def allowed_discussion(conn, uid, row):
    if not row or uid not in (row['user_a'],row['user_b']):
        return False
    if any(row['binding_'+role]!=account_binding(conn,row['user_'+role]) for role in ('a','b')):
        return False
    # Recheck BOTH participants: exit/release/reassignment cuts off sharing.
    for member in (row['user_a'],row['user_b']):
        scope=active_scope(conn,member)
        if not scope or scope[0]!=row['scope_kind'] or scope[1]['id']!=row['scope_id']:
            return False
    return True


def shared_view(row, value, uid):
    role='a' if row['user_a']==uid else 'b'
    return {'id':row['id'], 'topic':value['topic'], 'title':TOPICS[value['topic']][0],
        'status':value['status'], 'revision':value['revision'],
        'prompt':('What can each of you offer, and what would you like to try together?' if all(value['perspectives'].get(row['user_'+r]) for r in ('a','b')) else TOPICS[value['topic']][1][0]), 'invited_by_me':value['inviter']==uid,
        'my_perspective':value['perspectives'].get(uid,''),
        'partner_perspective':value['perspectives'].get(row['user_b' if role=='a' else 'user_a'],''),
        'proposal':value.get('proposal',''), 'my_confirmed':uid in value.get('confirmed',[]),
        'partner_confirmed':any(x!=uid for x in value.get('confirmed',[])),
        'both_responded':all(value['perspectives'].get(row['user_'+r]) for r in ('a','b'))}


def state(conn, uid, guidance):
    value=private(conn,uid)
    discussions=[]
    for row in sql(conn,'SELECT * FROM "GuruDiscussion" WHERE user_a=? OR user_b=?',(uid,uid)).fetchall():
        row=dict(row)
        if allowed_discussion(conn,uid,row):
            discussions.append(shared_view(row,unpack(row['payload']),uid))
    stage=guidance.get('topic_stage','matching')
    topics=STAGES.get(stage,STAGES['matching'])
    scope=active_scope(conn,uid)
    # Memory appears only in private space, never in any shared view or summary.
    return {'enabled':True, 'mode':'ai' if value.get('ai_consent') and guru_provider.available() else 'guided',
        'ai_available':guru_provider.available(), 'ai_consent':value.get('ai_consent',False), 'history':value['history'], 'memories':value['memories'],
        'remember':value['remember'], 'topics':[{'id':t,'label':TOPICS[t][0]} for t in topics],
        'shared_topics':[{'id':t,'label':TOPICS[t][0]} for t in topics if t in SHARED_TOPICS] if scope else [],
        'discussions':discussions}


def stage_guidance(user, guidance):
    result=dict(guidance)
    if user.get('journey_state') in ('relationship','engaged','married'):
        result['topic_stage']='relationship'
    elif result.get('topic_stage')=='relationship':
        result['topic_stage']='gate'
    return result


def respond(message, topic, history, guidance):
    # No claims about partner intent, inferred health/culture, or unperformed actions.
    lower=message.lower()
    if any(w in lower for w in ('unsafe','afraid','threat','violence','forced','hurt myself','suicide')):
        return 'Your safety comes first. You do not have to negotiate or share this. If there is immediate danger, contact local emergency help or someone you trust. Would you like to pause here?'
    if any(w in lower for w in ('what next','next step','what now','waiting','status')):
        return ' '.join(filter(None,(guidance.get('headline'),guidance.get('body')))) or 'Check Home for your current step.'
    prompts=TOPICS[topic][1]
    count=sum(x.get('role')=='user' and x.get('topic')==topic for x in history)
    if count>=len(prompts):
        return 'Your notes are saved here. You can revise them, take time, or choose what to discuss with your partner. Nothing is shared automatically.'
    return prompts[count]


def send_message(conn,uid,guidance,body,refresh_guidance=None):
    message=text(body.get('text'));topic=body.get('topic');rid=text(body.get('request_id'),80)
    if not isinstance(topic,str) or topic not in STAGES.get(guidance.get('topic_stage','matching'),STAGES['matching']):
        raise ApiError('stale_stage','Choose a topic available at your current stage.',409)
    with write(conn):
        value=private(conn,uid)
        previous=next((x for x in value['receipts'] if x['id']==rid),None)
        if previous:
            if (previous['text'],previous['topic'])!=(message,topic):
                raise ApiError('request_conflict','This request was already used.',409)
            return
        now=time.time()
        if value.get('pending',{}).get('until',0)>now:
            raise ApiError('busy','Guru is answering your previous message. Try shortly.',409)
        usage=[x for x in value.get('usage',[]) if x>now-86400]
        if len(usage)>=100 or sum(x>now-60 for x in usage)>=10:
            raise ApiError('rate_limited','Please pause before sending more messages.',429)
        value['usage']=usage+[now]
        token=uuid.uuid4().hex
        value['pending']={'id':token,'until':now+30}
        binding=account_binding(conn,uid)
        save_private(conn,uid,value)
    # Never hold a database transaction/lock during an external request.
    answer=respond(message,topic,value['history'],guidance)
    mode='guided'
    sensitive=any(w in message.lower() for w in ('unsafe','afraid','threat','violence','forced','hurt myself','suicide'))
    status_question=any(w in message.lower() for w in ('what next','next step','what now','waiting','status'))
    if value.get('ai_consent') and not sensitive and not status_question:
        generated=guru_provider.reply(message,topic,value['history'],value['memories'] if value['remember'] else [],guidance)
        if generated: answer=generated;mode='ai'
    if refresh_guidance:
        fresh=refresh_guidance()
        if any(fresh.get(k)!=guidance.get(k) for k in ('topic_stage','headline','body')):
            answer='Your next step changed. '+respond('what next',topic,[],fresh)
            mode='guided'
    with write(conn):
        current=private(conn,uid)
        if account_binding(conn,uid)!=binding or current.get('pending',{}).get('id')!=token:
            raise ApiError('state_conflict','Your privacy settings or conversation changed. The answer was not saved.',409)
        current.pop('pending',None)
        current['history']=(current['history']+[
            {'role':'user','text':message,'topic':topic,'at':stamp()},
            {'role':'guru','text':answer,'topic':topic,'at':stamp(),'mode':mode}])[-100:]
        current['receipts']=(current['receipts']+[{'id':rid,'text':message,'topic':topic}])[-50:]
        save_private(conn,uid,current)


def register(api,get_db,journey_state):
    @api.after_request
    def guru_cache(response):
        if request.path.startswith('/api/v1/guru/'):
            response.headers['Cache-Control']='no-store'
        return response

    def context():
        if not enabled():
            raise ApiError('guru_disabled','Guru conversations are not enabled yet.',503)
        cipher()
        guidance=journey_state(g.api_user)
        if 'verified' not in guidance['milestones']:
            raise ApiError('verification_required','Complete verification first.',403)
        return get_db(),g.api_user['user_id'],stage_guidance(g.api_user,guidance['next_action'])

    @api.get('/guru/state')
    def guru_state():
        if not enabled(): return jsonify(enabled=False)
        conn,uid,guidance=context()
        return jsonify(state(conn,uid,guidance))

    @api.post('/guru/private')
    def guru_private():
        body=json_object(required=('action',),optional=('text','topic','request_id','memory_id','enabled'))
        conn,uid,guidance=context()
        if body['action']=='message':
            send_message(conn,uid,guidance,body,lambda:stage_guidance(g.api_user,journey_state(g.api_user)['next_action']))
            return jsonify(state(conn,uid,guidance))
        with write(conn):
            value=private(conn,uid)
            value.pop('pending',None)  # A deletion/consent edit invalidates any in-flight answer.
            action=body['action']
            if action=='clear_history':
                value['history']=[];value['receipts']=[]
            elif action=='ai_setting':
                if type(body.get('enabled')) is not bool: raise ApiError('validation_error','Choose an AI setting.')
                if body['enabled'] and not guru_provider.available(): raise ApiError('unavailable','AI responses are not configured.',409)
                value['ai_consent']=body['enabled']
            elif action=='memory_setting':
                if type(body.get('enabled')) is not bool: raise ApiError('validation_error','Choose a memory setting.')
                value['remember']=body['enabled']
                if not value['remember']: value['memories']=[]
            elif action=='save_memory':
                if not value['remember']: raise ApiError('consent_required','Enable saved memory first.',409)
                note=text(body.get('text'),240)
                mid=body.get('memory_id')
                if mid:
                    item=next((x for x in value['memories'] if x['id']==mid),None)
                    if not item: raise ApiError('not_found','Memory not found.',404)
                    item['text']=note
                else:
                    if len(value['memories'])>=10: raise ApiError('limit_reached','Edit or remove a saved memory first.',409)
                    value['memories'].append({'id':uuid.uuid4().hex,'text':note})
            elif action=='delete_memory':
                value['memories']=[x for x in value['memories'] if x['id']!=body.get('memory_id')]
            elif action=='delete_private':
                value={'history':[],'memories':[],'remember':False,'receipts':[],'usage':value.get('usage',[]),'ai_consent':False}
            else: raise ApiError('validation_error','Unknown action.')
            save_private(conn,uid,value)
        return jsonify(state(conn,uid,guidance))

    @api.post('/guru/discussions')
    def guru_invite():
        body=json_object(required=('topic',))
        conn,uid,guidance=context()
        with write(conn):
            scope=active_scope(conn,uid)
            topic=body['topic']
            if not scope or not isinstance(topic,str) or topic not in SHARED_TOPICS or topic not in STAGES.get(guidance.get('topic_stage'),[]):
                raise ApiError('unavailable','This shared topic is not available now.',409)
            kind,pair,akey,bkey=scope
            a,b=pair[akey],pair[bkey]
            # One active conversation per pair: repeated invitation taps are safe.
            existing=db.fetch_all(conn,'GuruDiscussion',scope_id=pair['id'],scope_kind=kind)
            if len(existing)>=100: raise ApiError('limit_reached','Conversation limit reached for this pairing.',409)
            for old in existing:
                if allowed_discussion(conn,uid,old) and unpack(old['payload'])['status'] not in ('closed','agreed'):
                    raise ApiError('conversation_open','Finish or leave the existing conversation first.',409)
            row={'id':uuid.uuid4().hex,'scope_id':pair['id'],'scope_kind':kind,'user_a':a,'user_b':b,
                'binding_a':account_binding(conn,a),'binding_b':account_binding(conn,b)}
            if not allowed_discussion(conn,uid,row): raise ApiError('unavailable','Both partners must be eligible.',409)
            row['payload']=pack({'topic':topic,'inviter':uid,'status':'invited','revision':1,'perspectives':{},'proposal':'','confirmed':[]})
            save(conn,'GuruDiscussion',row)
        return jsonify(state(conn,uid,guidance))

    @api.post('/guru/discussions/<did>')
    def guru_discussion_action(did):
        body=json_object(required=('action','revision'),optional=('text',))
        conn,uid,guidance=context()
        with write(conn):
            row=db.fetch_one(conn,'GuruDiscussion',id=did)
            if not allowed_discussion(conn,uid,row): raise ApiError('not_found','Conversation not found.',404)
            value=unpack(row['payload'])
            if type(body['revision']) is not int or body['revision']!=value['revision']:
                raise ApiError('stale_conversation','Conversation changed. Refresh before continuing.',409)
            action=body['action'];status=value['status']
            if action=='leave':
                value.update(status='closed',perspectives={},proposal='',confirmed=[])
            elif action=='accept' and status=='invited' and uid!=value['inviter']:
                value['status']='active'
            elif action=='pause' and status=='active':
                value.update(status='paused',confirmed=[],resume=[])
            elif action=='resume' and status=='paused':
                value['resume']=list(set(value.get('resume',[])+[uid]))
                if len(value['resume'])==2: value['status']='active'
            elif action in ('perspective','propose') and status=='active':
                content=text(body.get('text'))
                if action=='perspective':
                    value['perspectives'][uid]=content
                    value['proposal']=''
                else:
                    if not all(value['perspectives'].get(x) for x in (row['user_a'],row['user_b'])):
                        raise ApiError('waiting','Both partners need to share their perspective first.',409)
                    value['proposal']=content
                value['confirmed']=[]
            elif action=='confirm' and status=='active' and value['proposal']:
                value['confirmed']=list(set(value['confirmed']+[uid]))
                if len(value['confirmed'])==2: value['status']='agreed'
            else: raise ApiError('state_conflict','This action is not available now.',409)
            value['revision']+=1
            row['payload']=pack(value);save(conn,'GuruDiscussion',row)
        return jsonify(state(conn,uid,guidance))
