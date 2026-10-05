"""Serialized mutual gate decisions, private answers and atomic relationship entry."""
import db,stage_gate,gate_conversation,journey,vision
import async_rehearsal
import hashlib
import ceremony
import after_date_service
from evolution_service import transaction,text,hours
from api_contract import ApiError


def questions_for(conn,lid):
    return stage_gate.STAGE_GATE_QUESTIONS + [
        {'key':a['question_key'],'text':a['custom_question'],'kind':'text','category':'custom'}
        for a in db.fetch_all(conn,'GateAsk',pair_id=lid) if a.get('custom_question')]


def state(conn,uid,lid,clock):
    pair=db.fetch_one(conn,'LockIn',id=lid)
    if not pair or uid not in (pair['user_a'],pair['user_b']):raise ApiError('not_found','Gate not found.',404)
    gate=db.fetch_one(conn,'StageGate',pair_id=lid)
    if not gate or gate['status']!='progressed':
        after_date_service.pair(conn,uid,lid)
    role='a' if uid==pair['user_a'] else 'b'
    other='b' if role=='a' else 'a'
    if not gate:return {'lock_in_id':lid,'gate':None,'questions':stage_gate.STAGE_GATE_QUESTIONS}
    asks=db.fetch_all(conn,'GateAsk',pair_id=lid)
    keys=[a['question_key'] for a in asks if a['round_no']==(gate.get('round_no') or 1)]
    rows={side:db.fetch_all(conn,'GateResponse',pair_id=lid,user_id=pair['user_'+side]) for side in ('a','b')}
    answers={side:{r['question_key']:r['readiness_scale'] or r['answer_text'] for r in rows[side]} for side in rows}
    analysis=stage_gate.analyze_gate(lid,rows['a'],rows['b'])
    # Guru prompts directed at a partner are private too.
    analysis['guru_prompts']=[p for p in analysis['guru_prompts'] if p['for']==role]
    def prerequisites(side):
        user=db.fetch_one(conn,'User',id=pair['user_'+side])
        result=vision.prerequisites_met(db.fetch_all(conn,'VisionEntry',user_id=user['id']),db.load_json_field(user['stats_json'],{}),db.fetch_all(conn,'ChemistryEntry',user_id=user['id']))
        # Signup and seeded profiles can have a valid Vision without an edit-history row.
        # Read the actual saved preferences; never manufacture an audit event.
        saved=db.load_json_field(user['vision_json'],[])
        if saved and vision.validate_pillars(vision._as_pillars(saved))['ok']:
            result['vision_met']=True
            result['met']=not result['stats_missing'] and not result['chemistry_missing']
        return result
    mine=prerequisites(role)
    questions=questions_for(conn,lid)
    lookup={q['key']:q for q in questions}
    report=gate_conversation.report(keys,answers['a'],answers['b'])
    for line in report['lines']:line['prompt']=lookup[line['key']]['text']
    test_reflection=async_rehearsal.enabled() and all(after_date_service.simulation_allowed(conn,pair['user_'+side]) for side in ('a','b'))
    now=hours(clock)
    if test_reflection and gate.get('reflection_ready_a') and gate.get('reflection_ready_b') and gate.get('answers_closed_at') is not None:
        now=max(now,gate['answers_closed_at']+gate_conversation.REFLECTION_HOURS)
    reflection=gate_conversation.reflection(gate.get('answers_closed_at'),now)
    reflection.update(test_mode=test_reflection,my_ready=bool(gate.get('reflection_ready_'+role)),partner_ready=bool(gate.get('reflection_ready_'+other)))
    return {'lock_in_id':lid,'gate':{'id':gate['id'],'status':gate['status'],'round':gate.get('round_no') or 1,
        'my_confirmed':bool(gate['confirm_'+role]),'partner_confirmed':bool(gate['confirm_'+other]),
        'my_entry_complete':after_date_service.complete(conn,uid,lid,ceremony.RELATIONSHIP_ENTRY),
        'partner_entry_complete':after_date_service.complete(conn,pair['user_'+other],lid,ceremony.RELATIONSHIP_ENTRY),
        'my_exclusivity_ack':bool(gate['exclusivity_ack_'+role]),'partner_exclusivity_ack':bool(gate['exclusivity_ack_'+other])},
        'questions':questions,'asked':[{'key':k,'prompt':lookup[k]['text'],'kind':lookup[k]['kind'],'options':lookup[k].get('options',[])} for k in keys],
        'my_questions_submitted':any(a['asked_by']==uid and a['round_no']==(gate.get('round_no') or 1) for a in asks),
        'my_answers':answers[role],'report':report,
        'analysis':analysis,'reflection':reflection,
        'may_confirm':report['complete'] and reflection['may_commit'],
        'my_prerequisites':mine,'partner_prerequisites_met':prerequisites(other)['met']}


def action(conn,uid,lid,action,body,clock,today):
    with transaction(conn):
        pair=db.fetch_one(conn,'LockIn',id=lid)
        if not pair or uid not in (pair['user_a'],pair['user_b']):raise ApiError('not_found','Gate not found.',404)
        gate=db.fetch_one(conn,'StageGate',pair_id=lid)
        cid='couple_'+'_'.join(sorted((pair['user_a'],pair['user_b'])))
        if action=='enter-relationship' and gate and gate['status']=='progressed':
            return {'couple_id':cid,'advanced':True}
        if action=='decline' and gate and gate['status']=='declined':return
        after_date_service.pair(conn,uid,lid)
        role='a' if uid==pair['user_a'] else 'b'
        if action=='raise':
            if gate:return
            db.insert_row(conn,'StageGate',{'id':'gate:'+lid,**stage_gate.open_gate(lid,'exclusivity_raised',str(clock),uid)})
            return
        if not gate or gate['status']!='open':raise ApiError('gate_closed','An open gate is required.',409)
        if type(body.get('round')) is not int or body['round']!=(gate.get('round_no') or 1):
            raise ApiError('stale_round','Use the current gate round.',409)
        view=state(conn,uid,lid,clock)
        if action=='ask':
            keys=body.get('question_keys')
            custom=body.get('custom_question')
            if custom is not None:
                custom=text(custom,'custom_question',300)
            custom_key='custom_'+hashlib.sha256((lid+uid+str(body['round'])+(custom or '')).encode()).hexdigest()[:20] if custom else None
            known={q['key'] for q in stage_gate.STAGE_GATE_QUESTIONS}
            if type(keys) is not list or any(not isinstance(k,str) or k not in known for k in keys) or len(set(keys))!=len(keys):
                raise ApiError('validation_error','Choose unique known questions.')
            asks=db.fetch_all(conn,'GateAsk',pair_id=lid)
            own=[a['question_key'] for a in asks if a['asked_by']==uid and a['round_no']==body['round']]
            if own and set(keys+([custom_key] if custom_key else []))==set(own):return
            if own or gate['confirm_a'] or gate['confirm_b']:raise ApiError('round_started','Questions in this round are already recorded.',409)
            if not 1 <= len(keys)+bool(custom) <= 3:raise ApiError('validation_error','Choose one to three topics, including your custom question.')
            result=gate_conversation.validate_asks(keys,[a['question_key'] for a in asks]) if keys else {'ok':True,'keys':[]}
            if not result['ok'] or len(result['keys'])!=len(keys):raise ApiError('validation_error',result.get('error') or 'Question already asked.')
            for key in keys:
                db.insert_row(conn,'GateAsk',{'id':f'{lid}:{body["round"]}:{key}','pair_id':lid,'round_no':body['round'],'asked_by':uid,'question_key':key,'asked_at':str(clock)})
            if custom_key:
                db.insert_row(conn,'GateAsk',{'id':f'{lid}:{body["round"]}:{custom_key}','pair_id':lid,'round_no':body['round'],'asked_by':uid,'question_key':custom_key,'custom_question':custom,'asked_at':str(clock)})
            gate['reflection_ready_a']=gate['reflection_ready_b']=0
            gate['answers_closed_at']=None
        elif action=='answer':
            key=body.get('question_key')
            question=next((q for q in questions_for(conn,lid) if q['key']==key),None)
            if not question or key not in [q['key'] for q in view['asked']]:raise ApiError('validation_error','Answer a question asked in this round.')
            value=body.get('value')
            if value is not None:
                value=text(value,'value')
                if question['kind']=='scale' and value not in question['options']:raise ApiError('validation_error','Choose a listed scale option.')
            old=db.fetch_one(conn,'GateResponse',pair_id=lid,user_id=uid,question_key=key)
            if old and (old['readiness_scale'] or old['answer_text'])==value:return
            if gate['confirm_a'] or gate['confirm_b']:raise ApiError('confirmation_frozen','Answers cannot change after confirmation.',409)
            row=stage_gate.submit_gate_response(lid,uid,'open_question' if key.startswith('custom_') else key,readiness_scale=value if question['kind']=='scale' else None,answer_text=value if question['kind']=='text' else None)
            row['question_key']=key
            db.insert_row(conn,'GateResponse',{'id':f'{lid}:{uid}:{key}',**row})
            gate['reflection_ready_a']=gate['reflection_ready_b']=0
            gate['answers_closed_at']=hours(clock) if state(conn,uid,lid,clock)['report']['complete'] else None
        elif action=='reflection-ready':
            if not view['reflection']['test_mode']:raise ApiError('test_only','This action is only available in the enabled beta rehearsal.',403)
            if not view['report']['complete']:raise ApiError('answers_required','Both partners must answer every selected question first.',409)
            gate['reflection_ready_'+role]=1
        elif action=='confirm':
            if not view['may_confirm']:raise ApiError('reflection_required','Both partners must answer and complete the reflection interval.',409)
            if stage_gate.has_unresolved_exclusivity_mismatch(view['analysis']):raise ApiError('exclusivity_mismatch','Resolve exclusivity expectations first.',409)
            gate['confirm_'+role]=1
        elif action=='decline':gate=stage_gate.resolve_gate(gate,'declined',str(clock))
        elif action=='exclusivity-ack':
            if body.get('acknowledged') is not True:raise ApiError('validation_error','Explicit acknowledgement required.')
            gate['exclusivity_ack_'+role]=1
        elif action=='enter-relationship':
            if not gate['confirm_a'] or not gate['confirm_b'] or not view['may_confirm']:
                raise ApiError('mutual_confirmation_required','Both partners must confirm the reflected gate.',409)
            if not all(gate[k] for k in ('exclusivity_ack_a','exclusivity_ack_b','consent_a','consent_b','biometric_a','biometric_b')):
                raise ApiError('agreement_required','Both partners must acknowledge exclusivity and complete entry agreements.',409)
            for user in (pair['user_a'],pair['user_b']):
                if db.fetch_one(conn,'User',id=user)['journey_state']!='dating' or db.fetch_one(conn,'User',id=user)['bgv_status']!='verified':
                    raise ApiError('stage_conflict','Both verified partners must still be Dating.',409)
            if db.fetch_one(conn,'Couple',id=cid):raise ApiError('existing_couple','An existing couple requires its re-entry flow.',409)
            result=journey.enter_relationship(conn,cid,pair['user_a'],pair['user_b'],lockin_id=lid,gate=gate,
                gate_analysis=view['analysis'],prerequisites={'met':view['my_prerequisites']['met'] and view['partner_prerequisites_met']},
                exclusivity_ack_a=True,exclusivity_ack_b=True,consent_a=True,consent_b=True,biometric_a=True,biometric_b=True,
                vision_entries_for_couple=db.fetch_all(conn,'VisionEntry',user_id=pair['user_a'])+db.fetch_all(conn,'VisionEntry',user_id=pair['user_b']),today=today)
            if not result['advanced']:raise ApiError('entry_prerequisites',result['reason'],409)
            db.insert_row(conn,'StageGate',stage_gate.resolve_gate(gate,'progressed',str(clock)))
            return result
        else:raise ApiError('not_found','Unknown gate action.',404)
        db.insert_row(conn,'StageGate',gate)
