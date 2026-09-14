"""Allowlisted after-date reads and explicit actions."""
from flask import g,jsonify
import db,ceremony,escalations,invite_home,next_level,gate_service
import after_date_service as service
from api_contract import ApiError,json_object,allowlist


def register(api,get_db,get_clock,week_to_date):
    def uid():return g.api_user['user_id']
    @api.get('/lock-ins/<lid>/gate')
    def gate_read(lid):
        return jsonify(gate_service.state(get_db(),uid(),lid,get_clock()))

    def gate_handler(action):
        def handle(lid):
            fields={'raise':set(),'ask':{'round','question_keys'},'answer':{'round','question_key','value'},
                'confirm':{'round'},'decline':{'round'},'exclusivity-ack':{'round','acknowledged'},'enter-relationship':{'round'}}[action]
            result=gate_service.action(get_db(),uid(),lid,action,json_object(required=fields),get_clock(),week_to_date(get_clock().week))
            return jsonify(result or gate_service.state(get_db(),uid(),lid,get_clock()))
        return handle
    for action in ('raise','ask','answer','confirm','decline','exclusivity-ack','enter-relationship'):
        api.add_url_rule('/lock-ins/<lid>/gate/'+action,endpoint='gate_'+action,view_func=gate_handler(action),methods=['POST'])
    def view(lid):
        active=service.pair(get_db(),uid(),lid)
        other=active['user_b'] if active['user_a']==uid() else active['user_a']
        role='a' if active['user_a']==uid() else 'b'
        requests=[]
        for row in db.fetch_all(get_db(),'ContactRequest',pair_id=lid):
            mine=row['requester_id']==uid()
            # Do not turn a decline/ignore into pressure from its requester.
            shown={**allowlist(row,('id','channel','week')),'sent_by_me':mine,
                'status':escalations.contact_status_for_requester(row) if mine else row['status'],'contact':None}
            if mine and row['status']=='accepted' and all(service.complete(get_db(),u,lid,ceremony.CONTACT_SHARE) for u in (uid(),other)):
                account=db.fetch_one(get_db(),'Account',user_id=other) or {}
                if row['channel'] in ('phone','whatsapp'):shown['contact']=account.get('phone')
            requests.append(shown)
        invites=[]
        for row in db.fetch_all(get_db(),'HomeInvite',pair_id=lid):
            invites.append({**allowlist(row,('id','proposed_datetime','expectation_flag','acknowledgement_version')),
                'sent_by_me':row['requester_id']==uid(),
                'status':invite_home.status_for_requester(row) if row['requester_id']==uid() else row['status'],
                'my_acknowledged':bool(row['ack_signed_'+role]),'both_acknowledged':invite_home.both_acknowledged(row)})
        return {'lock_in_id':lid,'dates_completed':active['dates_completed'],'contact_requests':requests,'home_invites':invites,
            'contact_channels':escalations.CONTACT_CHANNELS,'expectation_flags':invite_home.EXPECTATION_FLAGS,
            'invite_acknowledgement':invite_home.IMMUTABLE_ACKNOWLEDGEMENT_TEXT,
            'invite_acknowledgement_version':invite_home.ACKNOWLEDGEMENT_VERSION,
            'guidance':invite_home.INTIMACY_EXPECTED_GUIDANCE,'trusted_contact_delivery_available':False,
            'next_level':{'questions':next_level.NEXT_LEVEL_QUESTIONS,'answers':[next_level.visible_answers(t,role) for t in db.fetch_all(get_db(),'NextLevelThread',pair_id=lid)]}}

    @api.get('/lock-ins/<lid>/after-date')
    def after_date(lid):return jsonify(view(lid))

    @api.post('/lock-ins/<lid>/contact-requests')
    def contact_request(lid):
        body=json_object(required={'channel'})
        service.contact_request(get_db(),uid(),lid,body['channel'],get_clock())
        return jsonify(view(lid))

    @api.post('/lock-ins/<lid>/contact-requests/<rid>/response')
    def contact_response(lid,rid):
        service.contact_respond(get_db(),uid(),lid,rid,json_object(required={'response'})['response'],get_clock())
        return jsonify(view(lid))

    @api.post('/lock-ins/<lid>/home-invites')
    def invite_propose(lid):
        service.invite_propose(get_db(),uid(),lid,json_object(required={'request_id','proposed_datetime','expectation_flag'}),get_clock())
        return jsonify(view(lid))

    def invite_handler(action):
        def handle(lid,rid):
            fields={'response'} if action=='respond' else {'acknowledgement_version','acknowledged'} if action=='acknowledge' else set()
            service.invite_action(get_db(),uid(),lid,rid,action,json_object(required=fields),get_clock())
            return jsonify(view(lid))
        return handle
    for action in ('see-flag','respond','guidance','acknowledge','revoke'):
        api.add_url_rule('/lock-ins/<lid>/home-invites/<rid>/'+action,endpoint='invite_'+action,view_func=invite_handler(action),methods=['POST'])

    @api.post('/lock-ins/<lid>/next-level')
    def open_next(lid):
        json_object()
        service.next_level_action(get_db(),uid(),lid,{},get_clock(),True)
        return jsonify(view(lid))

    @api.post('/lock-ins/<lid>/next-level/answers')
    def answer_next(lid):
        body=json_object(required={'question_key','declined'},optional={'answer_text'})
        service.next_level_action(get_db(),uid(),lid,body,get_clock())
        return jsonify(view(lid))

    def agreement_view(lid,kind):
        active=service.pair(get_db(),uid(),lid)
        if kind not in (ceremony.CONTACT_SHARE,ceremony.HOME_INVITE,ceremony.RELATIONSHIP_ENTRY):
            raise ApiError('not_found','Agreement not found.',404)
        state=service.agreement_state(get_db(),uid(),lid,kind)
        other=active['user_b'] if active['user_a']==uid() else active['user_a']
        return {'kind':kind,'step':ceremony.next_step(state),'complete':ceremony.is_complete(state),
            'partner_complete':service.complete(get_db(),other,lid,kind),'my_signed_name':state['signed_name'],
            'acks':ceremony.acks_for(kind),'clauses':ceremony.clauses_for(kind),
            'face_mode':'simulation','face_simulation_available':service.simulation_allowed(get_db(),uid())}

    @api.get('/lock-ins/<lid>/agreements/<kind>')
    def agreement_read(lid,kind):return jsonify(agreement_view(lid,kind))

    @api.post('/lock-ins/<lid>/agreements/<kind>/steps')
    def after_date_agreement_step(lid,kind):
        body=json_object(required={'step'},optional={'signed_name','acks'})
        if body['step']!='sign' and set(body)!={'step'}:
            raise ApiError('validation_error','Signature fields belong only to the sign step.')
        service.agreement(get_db(),uid(),lid,kind,body,get_clock())
        return jsonify(agreement_view(lid,kind))
