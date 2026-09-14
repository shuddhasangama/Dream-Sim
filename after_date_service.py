"""Owned after-date actions. Shared by HTML and API; no real messaging."""
import os
import uuid
from datetime import datetime
import db
import ceremony
import escalations
import invite_home
import next_level
import planning_service
from evolution_service import transaction, text
from api_contract import ApiError


def pair(conn,uid,lid):
    active=planning_service.pair(conn,uid,lid)
    # Historical completed encounters predate DateResolution/count receipts.
    # A real stored happened flag is sufficient; merely creating an outcome
    # or a unilateral no-show/feedback report is not.
    met = any(bool((db.fetch_one(conn,'DateOutcome',dateplan_id=p['id']) or {}).get('happened'))
              for p in db.fetch_all(conn,'DatePlan',lockin_id=lid))
    if not escalations.unlocks_available(active['dates_completed']) and not met:
        raise ApiError('after_date_locked','Complete a date together before this step.',403)
    return active


def owned(conn,uid,lid,table,rid):
    active=pair(conn,uid,lid)
    row=db.fetch_one(conn,table,id=rid)
    if not row or row['pair_id']!=lid:
        raise ApiError('not_found','Resource not found.',404)
    return active,row


def agreement_state(conn,uid,lid,kind):
    return db.fetch_one(conn,'Ceremony',user_id=uid,kind=kind,scope_id=lid) or ceremony.new_state(uid,kind,lid,'')


def complete(conn,uid,lid,kind):
    return ceremony.is_complete(agreement_state(conn,uid,lid,kind))


def require_agreement(conn,active,uid,kind,both=False):
    users=(active['user_a'],active['user_b']) if both else (uid,)
    if not all(complete(conn,u,active['id'],kind) for u in users):
        raise ApiError('agreement_required','Complete the required agreement first.',409)


def simulation_allowed(conn,uid):
    account=db.fetch_one(conn,'Account',user_id=uid)
    return os.environ.get('BETA_DATE_SIMULATION_ENABLED','0')=='1' and bool(account and account.get('auth_enabled'))


def agreement(conn,uid,lid,kind,body,clock):
    if kind not in (ceremony.CONTACT_SHARE,ceremony.HOME_INVITE,ceremony.RELATIONSHIP_ENTRY):
        raise ApiError('not_found','Agreement not found.',404)
    with transaction(conn):
        active=pair(conn,uid,lid)
        if kind==ceremony.HOME_INVITE:
            require_agreement(conn,active,uid,ceremony.CONTACT_SHARE,True)
        if kind==ceremony.RELATIONSHIP_ENTRY:
            gate=db.fetch_one(conn,'StageGate',pair_id=lid)
            if not gate or gate['status']!='open' or not (gate['confirm_a'] and gate['confirm_b']):
                raise ApiError('gate_not_ready','Both partners must confirm the open gate first.',409)
        state=agreement_state(conn,uid,lid,kind)
        step=body.get('step')
        if step not in ('playbook','sign','face'):
            raise ApiError('validation_error','Unknown agreement step.')
        if step=='sign':
            name=text(body.get('signed_name'),'signed_name',160)
            acks=body.get('acks')
            if type(acks) is not list or any(not isinstance(a,str) for a in acks) or len(set(acks))!=len(acks) or set(acks)!=set(ceremony.ack_keys(kind)):
                raise ApiError('validation_error','Explicitly acknowledge every listed term exactly once.')
            if state['signed_name']:
                if name!=state['signed_name']:
                    raise ApiError('already_signed','An existing signature cannot be replaced.',409)
                return
        completed=(step=='playbook' and state['playbook_ack']) or (step=='face' and state['face_verified'])
        if completed:
            return
        if ceremony.next_step(state)!=step:
            raise ApiError('step_order','Complete agreement steps in order.',409)
        if step=='playbook': state=ceremony.ack_playbook(state)
        elif step=='sign': state=ceremony.sign(state,name,acks,str(clock))
        else:
            if not simulation_allowed(conn,uid):
                raise ApiError('verification_unavailable','Face verification is only an explicitly enabled beta simulation.',409)
            state=ceremony.capture_face(state)
        state=ceremony.complete(state,str(clock))
        state['created_at']=state['created_at'] or str(clock)
        db.insert_row(conn,'Ceremony',state)
        if kind==ceremony.RELATIONSHIP_ENTRY and ceremony.is_complete(state):
            role='a' if active['user_a']==uid else 'b'
            db.insert_row(conn,'StageGate',{**gate,f'consent_{role}':1,f'biometric_{role}':1})


def contact_request(conn,uid,lid,channel,clock):
    if channel not in escalations.CONTACT_CHANNELS:
        raise ApiError('validation_error','Unknown contact channel.')
    with transaction(conn):
        active=pair(conn,uid,lid)
        rows=db.fetch_all(conn,'ContactRequest',pair_id=lid,channel=channel)
        old=next((r for r in rows if r['week']==active['week']),None)
        if old:
            if old['requester_id']!=uid:
                raise ApiError('request_exists','A request already exists for this channel and week.',409)
            return old['id']
        row=escalations.request_contact(lid,uid,channel,active['week'],str(clock),rows)
        rid=uuid.uuid4().hex
        db.insert_row(conn,'ContactRequest',{'id':rid,**row})
        return rid


def contact_respond(conn,uid,lid,rid,response,clock):
    if response not in ('accepted','declined','ignored'):
        raise ApiError('validation_error','Unknown response.')
    with transaction(conn):
        active,row=owned(conn,uid,lid,'ContactRequest',rid)
        if row['requester_id']==uid:
            raise ApiError('recipient_required','Only the recipient can respond.',403)
        if row['status']==response:return
        if row['status']!='pending':
            raise ApiError('response_final','Request already resolved.',409)
        if response=='accepted':
            require_agreement(conn,active,uid,ceremony.CONTACT_SHARE)
        db.insert_row(conn,'ContactRequest',escalations.respond_to_contact_request(row,response,str(clock)))


def invite_propose(conn,uid,lid,body,clock):
    request_id=text(body.get('request_id'),'request_id',80)
    when=text(body.get('proposed_datetime'),'proposed_datetime',40)
    try: datetime.fromisoformat(when)
    except ValueError: raise ApiError('validation_error','Use an ISO date and time.')
    flag=body.get('expectation_flag')
    if flag not in invite_home.EXPECTATION_FLAGS:
        raise ApiError('validation_error','Unknown expectation flag.')
    with transaction(conn):
        active=pair(conn,uid,lid)
        rid=f'{uid}:{request_id}'
        old=db.fetch_one(conn,'HomeInvite',id=rid)
        if old:
            if old['pair_id']!=lid or old['proposed_datetime']!=when or old['expectation_flag']!=flag:
                raise ApiError('request_conflict','Request ID already used.',409)
            return rid
        require_agreement(conn,active,uid,ceremony.CONTACT_SHARE,True)
        require_agreement(conn,active,uid,ceremony.HOME_INVITE)
        try: row=invite_home.propose_invite(lid,uid,when,flag,db.fetch_all(conn,'HomeInvite',pair_id=lid))
        except ValueError as exc: raise ApiError('invite_conflict',str(exc),409)
        db.insert_row(conn,'HomeInvite',{'id':rid,**row})
        return rid


def invite_action(conn,uid,lid,rid,action,body,clock):
    with transaction(conn):
        active,row=owned(conn,uid,lid,'HomeInvite',rid)
        role='a' if active['user_a']==uid else 'b'
        if action in ('see-flag','respond') and row['requester_id']==uid:
            raise ApiError('recipient_required','Only the recipient can perform this action.',403)
        if action=='revoke' and row['status']=='revoked':return
        if action=='respond' and row['status']==body.get('response'):return
        if row['status'] in ('declined','ignored','revoked'):
            raise ApiError('invite_closed','Invite is closed.',409)
        try:
            if action=='see-flag': updated=invite_home.mark_flag_seen(row,str(clock))
            elif action=='respond': updated=invite_home.respond_to_invite(row,body.get('response'))
            elif action=='guidance': updated=invite_home.show_guidance(row,role)
            elif action=='acknowledge':
                if body.get('acknowledgement_version')!=invite_home.ACKNOWLEDGEMENT_VERSION or body.get('acknowledged') is not True:
                    raise ApiError('validation_error','Explicit acknowledgement of the current text is required.')
                require_agreement(conn,active,uid,ceremony.HOME_INVITE)
                if not simulation_allowed(conn,uid):
                    raise ApiError('verification_unavailable','Face step requires explicit beta simulation.',409)
                updated=invite_home.acknowledge(row,role,True)
            elif action=='revoke': updated=invite_home.revoke(row,uid,str(clock))
            else: raise ApiError('not_found','Unknown invite action.',404)
        except ValueError as exc: raise ApiError('invite_conflict',str(exc),409)
        db.insert_row(conn,'HomeInvite',updated)


def next_level_action(conn,uid,lid,body,clock,open_only=False):
    with transaction(conn):
        active=pair(conn,uid,lid)
        if open_only:
            if not db.fetch_all(conn,'NextLevelThread',pair_id=lid):
                for row in next_level.open_conversation(lid,'user',str(clock)):
                    db.insert_row(conn,'NextLevelThread',{'id':f"{lid}:{row['question_key']}",**row})
            return
        key=body.get('question_key')
        row=db.fetch_one(conn,'NextLevelThread',pair_id=lid,question_key=key) if isinstance(key,str) else None
        if not row:raise ApiError('not_found','Open the conversation and choose a listed question.',404)
        declined=body.get('declined')
        if type(declined) is not bool:raise ApiError('validation_error','declined must be a boolean.')
        answer=None if declined else text(body.get('answer_text'),'answer_text')
        if declined and body.get('answer_text') is not None:raise ApiError('validation_error','A decline cannot contain an answer.')
        role='a' if active['user_a']==uid else 'b'
        if row[f'answered_at_{role}']:
            if bool(row[f'declined_{role}'])==declined and row[f'answer_{role}']==answer:return
            raise ApiError('answer_final','This reciprocal answer has already been recorded.',409)
        db.insert_row(conn,'NextLevelThread',next_level.submit_answer(row,role,answered_at=str(clock),answer_text=answer,declined=declined))
