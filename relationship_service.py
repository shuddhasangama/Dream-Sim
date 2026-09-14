"""Post-Dating actions, serialized against membership and stage transitions."""
from datetime import date
import json
import db,journey,ceremony,payments,guru_relationship
import after_date_service
from evolution_service import transaction,text
from api_contract import ApiError


def couple(conn,uid,cid,exiting=False):
    row=db.fetch_one(conn,'Couple',id=cid)
    if not row or uid not in (row['partner_a_id'],row['partner_b_id']):raise ApiError('not_found','Couple not found.',404)
    user=db.fetch_one(conn,'User',id=uid)
    if not exiting and (user['journey_state']!=row['stage'] or user['bgv_status']!='verified'):
        raise ApiError('stage_unavailable','An active verified relationship is required.',403)
    return row


def role(row,uid):return 'a' if row['partner_a_id']==uid else 'b'


def event(conn,uid,cid,scope,kind,body,clock,request_id):
    rid=uid+':'+text(request_id,'request_id',80)
    payload=json.dumps(body,sort_keys=True,ensure_ascii=False)
    old=db.fetch_one(conn,'JourneyAction',id=rid)
    if old:
        if (old['couple_id'],old['scope'],old['kind'],old['payload_json'])!=(cid,scope,kind,payload):
            raise ApiError('request_conflict','Request ID has already been used with different content.',409)
        return old,False
    row={'id':rid,'couple_id':cid,'user_id':uid,'scope':scope,'kind':kind,'payload_json':payload,'created_at':str(clock)}
    db.insert_row(conn,'JourneyAction',row)
    return row,True


def stage(row,expected):
    if expected!=row['stage']:raise ApiError('stale_stage','Use the current relationship stage.',409)


def idea(conn,uid,cid,body,clock,romance=False):
    value=text(body.get('idea'),'idea')
    with transaction(conn):
        row=couple(conn,uid,cid);stage(row,body.get('stage'))
        _,fresh=event(conn,uid,cid,row['stage'],'romance' if romance else 'idea',{'idea':value},clock,body.get('request_id'))
        if not fresh:return
        playbook=db.fetch_one(conn,'Playbook',couple_id=cid,stage=row['stage'])
        if not playbook:raise ApiError('playbook_missing','Initialize the stage playbook before editing.',409)
        custom=db.load_json_field(playbook['tier_custom_json'],[])
        playbook['tier_custom_json']=db.json_field(guru_relationship.add_romance_idea(custom,'Romance idea: '+value) if romance else [*custom,value])
        db.insert_row(conn,'Playbook',playbook)


def difference(conn,uid,cid,body,clock):
    value=text(body.get('text'),'text')
    with transaction(conn):
        row=couple(conn,uid,cid);stage(row,body.get('stage'))
        receipt,fresh=event(conn,uid,cid,row['stage'],'difference',{'text':value},clock,body.get('request_id'))
        if fresh:
            data=guru_relationship.air_step1_raise_difference(cid,uid,value,row['stage_week_index'],db.fetch_all(conn,'Difference',couple_id=cid))
            db.insert_row(conn,'Difference',{'id':receipt['id'],**data})
        return receipt['id']


def difference_action(conn,uid,cid,rid,body,resolve=False):
    with transaction(conn):
        couple(conn,uid,cid)
        row=db.fetch_one(conn,'Difference',id=rid)
        if not row or row['couple_id']!=cid or (row['raised_by']!=uid and not row['consent_to_share']):raise ApiError('not_found','Difference not found.',404)
        if row['raised_by']!=uid:raise ApiError('author_required','Only the author can share or close their concern.',403)
        if resolve:row=guru_relationship.resolve_difference(row)
        else:
            if type(body.get('consent')) is not bool:raise ApiError('validation_error','consent must be boolean.')
            row=guru_relationship.air_step2_consent_to_share(row,body['consent'])
        db.insert_row(conn,'Difference',row)


def expense(conn,uid,cid,body,clock):
    if type(body.get('compliant')) is not bool:raise ApiError('validation_error','compliant must be boolean.')
    strategy=text(body.get('strategy'),'strategy',500)
    with transaction(conn):
        row=couple(conn,uid,cid);stage(row,body.get('stage'))
        if type(body.get('week')) is not int or body['week']!=row['stage_week_index']:raise ApiError('stale_week','Use the current stage week.',409)
        result=guru_relationship.expense_check(strategy,body['compliant'])
        event(conn,uid,cid,f"{row['stage']}:{row['stage_week_index']}",'expense',result,clock,body.get('request_id'))


def checkpoint_scope(cid,source):return f'{cid}:{source}:{journey.next_stage(source)}'


def checkpoint_state(conn,uid,cid,source):
    row=couple(conn,uid,cid);stage(row,source)
    target=journey.next_stage(source)
    if not target:raise ApiError('final_stage','Already at the final stage.',409)
    scope=checkpoint_scope(cid,source)
    mine=db.fetch_one(conn,'Ceremony',user_id=uid,kind=ceremony.STAGE_GATE,scope_id=scope) or ceremony.new_state(uid,ceremony.STAGE_GATE,scope,'')
    other=row['partner_b_id'] if row['partner_a_id']==uid else row['partner_a_id']
    theirs=db.fetch_one(conn,'Ceremony',user_id=other,kind=ceremony.STAGE_GATE,scope_id=scope)
    return {'from_stage':source,'to_stage':target,'scope':scope,'step':ceremony.next_step(mine),'my_complete':ceremony.is_complete(mine),
        'partner_complete':bool(theirs and ceremony.is_complete(theirs)),'my_signed_name':mine['signed_name'],
        'acks':ceremony.acks_for(ceremony.STAGE_GATE),'clauses':ceremony.clauses_for(ceremony.STAGE_GATE),
        'face_mode':'simulation','face_simulation_available':after_date_service.simulation_allowed(conn,uid),
        'payment':{'enforced':payments.is_enabled(),'satisfied':not payments.is_enabled() or payments.has_paid(db.fetch_all(conn,'Payment',user_id=uid),uid,payments.STAGE_GATE,scope),
            'purpose':payments.STAGE_GATE,'scope_id':scope,'amount_inr':payments.fee(payments.STAGE_GATE)['amount_inr'],'provider_mode':'simulation','api_payment_available':False}}


def checkpoint_step(conn,uid,cid,source,body,clock):
    with transaction(conn):
        info=checkpoint_state(conn,uid,cid,source)
        if not info['payment']['satisfied']:raise ApiError('payment_required','Checkpoint payment prerequisite is not satisfied.',409)
        mine=db.fetch_one(conn,'Ceremony',user_id=uid,kind=ceremony.STAGE_GATE,scope_id=info['scope']) or ceremony.new_state(uid,ceremony.STAGE_GATE,info['scope'],str(clock))
        step=body.get('step')
        if step not in ('playbook','sign','face'):raise ApiError('validation_error','Unknown agreement step.')
        if step=='sign':
            name=text(body.get('signed_name'),'signed_name',160);acks=body.get('acks')
            if type(acks) is not list or any(not isinstance(x,str) for x in acks) or len(set(acks))!=len(acks) or set(acks)!=set(ceremony.ack_keys(ceremony.STAGE_GATE)):
                raise ApiError('validation_error','Explicitly acknowledge all terms exactly once.')
            if mine['signed_name']:
                if mine['signed_name']!=name:raise ApiError('already_signed','Signature is already recorded.',409)
                return
        if (step=='playbook' and mine['playbook_ack']) or (step=='face' and mine['face_verified']):return
        if ceremony.next_step(mine)!=step:raise ApiError('step_order','Complete the agreement in order.',409)
        if step=='playbook':mine=ceremony.ack_playbook(mine)
        elif step=='sign':mine=ceremony.sign(mine,name,acks,str(clock))
        else:
            if not info['face_simulation_available']:raise ApiError('verification_unavailable','Explicit approved-beta simulation is required.',409)
            mine=ceremony.capture_face(mine)
        db.insert_row(conn,'Ceremony',ceremony.complete(mine,str(clock)))


def advance(conn,uid,cid,source,clock,today):
    with transaction(conn):
        row=couple(conn,uid,cid)
        target=journey.next_stage(source)
        receipt=db.fetch_one(conn,'JourneyAction',id=f'{cid}:advance:{source}')
        if receipt:return {'advanced':True,'to_stage':target,'current_stage':row['stage']}
        info=checkpoint_state(conn,uid,cid,source)
        for who in (row['partner_a_id'],row['partner_b_id']):
            actor=db.fetch_one(conn,'User',id=who)
            if actor['journey_state']!=source or actor['bgv_status']!='verified':raise ApiError('stage_conflict','Both verified partners must still be in this stage.',409)
            check=checkpoint_state(conn,who,cid,source)
            if not check['my_complete'] or not check['payment']['satisfied']:raise ApiError('mutual_consent_required','Both partners must complete this checkpoint and its prerequisites.',409)
        result=journey.advance_stage(conn,cid,True,True,today=today,biometric_a=True,biometric_b=True)
        if not result['advanced']:raise ApiError('stage_conflict',result['reason'],409)
        db.insert_row(conn,'JourneyAction',{'id':f'{cid}:advance:{source}','couple_id':cid,'user_id':uid,'scope':source,'kind':'advance','payload_json':db.json_field(result),'created_at':str(clock)})
        return result


def exit_read(conn,uid,cid,eid):
    row=couple(conn,uid,cid,True);side=role(row,uid)
    record=db.fetch_one(conn,'Exit',id=eid)
    if not record or record['couple_id']!=cid:raise ApiError('not_found','Exit not found.',404)
    return {'id':eid,'status':record['status'],'stage_at_exit':record['stage_at_exit'],'cooloff_ends':record['cooloff_ends'],
        'my_feedback':record['feedback_'+side+'_raw'],'my_reflection':record['guru_synthesis_for_'+side],'guru_mode':'simulation',
        'my_interview_complete':bool(db.fetch_one(conn,'JourneyAction',id=eid+':interview:'+uid)),
        'my_reentry_complete':bool(db.fetch_one(conn,'JourneyAction',id=eid+':reentry:'+uid))}


def exit_start(conn,uid,cid,body,clock):
    with transaction(conn):
        row=couple(conn,uid,cid,True)
        existing=db.fetch_all(conn,'Exit',couple_id=cid)
        if existing:return existing[-1]['id']
        couple(conn,uid,cid);stage(row,body.get('stage'))
        eid=cid+':exit'
        journey.initiate_exit(conn,eid,cid,uid)
        return eid


def exit_action(conn,uid,cid,eid,action,body,clock,today):
    with transaction(conn):
        pair=couple(conn,uid,cid,True);exit_read(conn,uid,cid,eid)
        record=db.fetch_one(conn,'Exit',id=eid)
        rid=eid+':'+action+':'+uid
        side=role(pair,uid)
        if action=='interview' and body.get('acknowledged') is not True:raise ApiError('validation_error','Explicit interview acknowledgement required.')
        if action=='feedback':
            if type(body.get('declined')) is not bool:raise ApiError('validation_error','declined must be boolean.')
            proposed='' if body['declined'] else text(body.get('text'),'text')
            if body['declined'] and body.get('text') is not None:raise ApiError('validation_error','A decline cannot include feedback.')
        if db.fetch_one(conn,'JourneyAction',id=rid):
            if action=='feedback' and record['feedback_'+side+'_raw']!=proposed:raise ApiError('feedback_final','Feedback is already recorded.',409)
            return
        if action=='interview':
            if body.get('acknowledged') is not True:raise ApiError('validation_error','Explicit interview acknowledgement required.')
            if record['status']!='interview':raise ApiError('exit_state','Interview step is closed.',409)
        elif action=='feedback':
            if record['status']!='feedback':raise ApiError('exit_state','Both interview acknowledgements are required first.',409)
            if type(body.get('declined')) is not bool:raise ApiError('validation_error','declined must be boolean.')
            value='' if body['declined'] else text(body.get('text'),'text')
            if body['declined'] and body.get('text') is not None:raise ApiError('validation_error','A decline cannot include feedback.')
            journey.submit_feedback(conn,eid,**{'feedback_'+side+'_raw':value})
        elif action=='reentry':
            if not journey.check_cooloff(conn,eid,today)['cooloff_over']:raise ApiError('cooloff_active','Wait until the recorded cool-off ends.',409)
            user=db.fetch_one(conn,'User',id=uid)
            if user['journey_state'] not in ('cooloff','re-entry') or user['bgv_status']!='verified':raise ApiError('reentry_unavailable','Re-entry requires your verified, closed exit.',409)
            # Never move the other partner back into matching on this request.
            user['journey_state']='dating';db.insert_row(conn,'User',user)
        else:raise ApiError('not_found','Unknown exit action.',404)
        db.insert_row(conn,'JourneyAction',{'id':rid,'couple_id':cid,'user_id':uid,'scope':eid,'kind':action,'payload_json':'{}','created_at':str(clock)})
        both=all(db.fetch_one(conn,'JourneyAction',id=eid+':'+action+':'+who) for who in (pair['partner_a_id'],pair['partner_b_id']))
        if both and action=='interview':journey.complete_exit_interview(conn,eid)
        if both and action=='feedback':journey.synthesize_guru_feedback(conn,eid,today)
