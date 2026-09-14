"""Relationship/ROAD/later-stage JSON boundary. GETs never seed or advance."""
from flask import g,jsonify
from datetime import date,timedelta
import db,journey
import relationship_service as service
import road_service
from api_contract import ApiError,json_object,allowlist


def register(api,get_db,get_clock,week_to_date,derive,vision_options):
    def uid():return g.api_user['user_id']
    def monday():return week_to_date(get_clock().week)
    def today():return (date.fromisoformat(monday())+timedelta(days=get_clock().day_index)).isoformat()
    def summary(cid):
        row=service.couple(get_db(),uid(),cid);side=service.role(row,uid())
        book=db.fetch_one(get_db(),'Playbook',couple_id=cid,stage=row['stage']) or {}
        differences=[{**allowlist(d,('id','text','status','consent_to_share','week_raised')),'raised_by_me':d['raised_by']==uid()} for d in db.fetch_all(get_db(),'Difference',couple_id=cid) if d['raised_by']==uid() or d['consent_to_share']]
        report=db.fetch_one(get_db(),'WeeklyReport',couple_id=cid,stage=row['stage'],week_index=row['stage_week_index'])
        own_report=None if not report else {'week':report['week_index'],'my_view':report['view_own_'+side],'my_guru_view':report['view_guru_on_'+side],'combined_view':report['view_combined'],'pair_guru_view':report['view_guru_on_pair']}
        expenses=[{'id':e['id'],**db.load_json_field(e['payload_json'],{})} for e in db.fetch_all(get_db(),'JourneyAction',couple_id=cid,user_id=uid(),scope=f"{row['stage']}:{row['stage_week_index']}",kind='expense')]
        partner=row['partner_b_id'] if side=='a' else row['partner_a_id']
        return {'couple':allowlist(row,('id','stage','stage_week_index','start_date')),'playbook':{key:db.load_json_field(book.get(field),[]) for key,field in [('generic','tier_generic_json'),('vision','tier_vision_json'),('custom','tier_custom_json')]},
            'differences':differences,'my_expense_reports':expenses,'weekly_report':own_report,
            'checkpoint':journey.sixteen_week_checkpoint(row),'next_stage':journey.next_stage(row['stage']),
            'topics':[allowlist(t,('kind','topic_key')) for t in db.fetch_all(get_db(),'GuruTopic',couple_id=cid,stage=row['stage'])],
            'partner_disclosed_vision_changes':db.fetch_all(get_db(),'VisionChange',user_id=partner,disclosed_to_partner=1),
            'partner_disclosed_stat_changes':db.fetch_all(get_db(),'StatChange',user_id=partner,disclosed_to_partner=1),
            'guru_mode':'simulation','mediator_delivery_available':False,'clock_mode':'simulation'}

    @api.get('/couples/<cid>')
    def relationship_read(cid):return jsonify(summary(cid))

    def idea_handler(romance):
        def handle(cid):
            service.idea(get_db(),uid(),cid,json_object(required={'request_id','stage','idea'}),get_clock(),romance)
            return jsonify(summary(cid))
        return handle
    api.add_url_rule('/couples/<cid>/playbook/ideas',endpoint='playbook_idea',view_func=idea_handler(False),methods=['POST'])
    api.add_url_rule('/couples/<cid>/romance/ideas',endpoint='romance_idea',view_func=idea_handler(True),methods=['POST'])

    @api.post('/couples/<cid>/differences')
    def difference_create(cid):
        service.difference(get_db(),uid(),cid,json_object(required={'request_id','stage','text'}),get_clock())
        return jsonify(summary(cid))

    @api.post('/couples/<cid>/differences/<rid>/sharing')
    def difference_share(cid,rid):
        service.difference_action(get_db(),uid(),cid,rid,json_object(required={'consent'}))
        return jsonify(summary(cid))

    @api.post('/couples/<cid>/differences/<rid>/resolve')
    def difference_resolve(cid,rid):
        json_object();service.difference_action(get_db(),uid(),cid,rid,{},True)
        return jsonify(summary(cid))

    @api.post('/couples/<cid>/expense-reports')
    def expense_report(cid):
        service.expense(get_db(),uid(),cid,json_object(required={'request_id','stage','week','strategy','compliant'}),get_clock())
        return jsonify(summary(cid))

    @api.get('/couples/<cid>/checkpoints/<source>')
    def checkpoint_read(cid,source):return jsonify(service.checkpoint_state(get_db(),uid(),cid,source))

    @api.post('/couples/<cid>/checkpoints/<source>/steps')
    def checkpoint_step(cid,source):
        body=json_object(required={'step'},optional={'signed_name','acks'})
        if body['step']!='sign' and set(body)!={'step'}:raise ApiError('validation_error','Signature fields belong only to signing.')
        service.checkpoint_step(get_db(),uid(),cid,source,body,get_clock())
        return jsonify(service.checkpoint_state(get_db(),uid(),cid,source))

    @api.post('/couples/<cid>/checkpoints/<source>/advance')
    def checkpoint_advance(cid,source):
        json_object()
        return jsonify(service.advance(get_db(),uid(),cid,source,get_clock(),today()))

    def road_view(cid):
        row=service.couple(get_db(),uid(),cid);other=row['partner_b_id'] if row['partner_a_id']==uid() else row['partner_a_id']
        own=road_service.road(get_db(),uid(),cid)
        mine=road_service.live_shared(get_db(),uid(),cid,monday(),derive);theirs=road_service.live_shared(get_db(),other,cid,monday(),derive)
        overlap=[]
        for a in mine:
            for b in theirs:
                start,end=max(a['start'],b['start']),min(a['end'],b['end'])
                if a['day']==b['day'] and road_service.minutes(end)-road_service.minutes(start)>=30:
                    slot={'day':a['day'],'start':start,'end':end}
                    if slot not in overlap:overlap.append(slot)
        ownuser=db.fetch_one(get_db(),'User',id=uid());partner=db.fetch_one(get_db(),'User',id=other)
        obligations=db.fetch_all(get_db(),'CalendarEntry',couple_id=cid)
        return {'couple_id':cid,'week_start':monday(),'my_routine':db.load_json_field(own['routine_json'],[]),
            'my_obligations':[allowlist(e,('id','type','travel_mode','starts_at','ends_at','title','shared')) for e in obligations if e['owner_id']==uid()],
            'partner_shared_obligations':[allowlist(e,('type','travel_mode','starts_at','ends_at','title')) for e in obligations if e['owner_id']==other and e['shared']],
            'my_availability':road_service.availability(get_db(),uid(),cid,monday(),derive),'my_shared_slots':mine,'partner_shared_slots':theirs,'overlap':overlap,
            'my_vision':db.load_json_field(ownuser['vision_json'],[]),'partner_vision':db.load_json_field(partner['vision_json'],[]),'vision_options':vision_options,
            'availability_mode':'simulation_week','obligation_rule':'Dated obligations remove the entire inclusive day from availability.'}

    @api.get('/couples/<cid>/road')
    def road_read(cid):return jsonify(road_view(cid))

    @api.post('/couples/<cid>/road/routine')
    def routine_add(cid):
        road_service.block(get_db(),uid(),cid,json_object(required={'request_id','category','days','label','start','end'}),get_clock())
        return jsonify(road_view(cid))

    @api.delete('/couples/<cid>/road/routine/<rid>')
    def routine_delete(cid,rid):
        json_object();road_service.remove_block(get_db(),uid(),cid,rid)
        return jsonify(road_view(cid))

    @api.post('/couples/<cid>/road/obligations')
    def obligation_add(cid):
        road_service.obligation(get_db(),uid(),cid,json_object(required={'request_id','type','title','start_date','end_date','shared'},optional={'travel_mode'}),get_clock())
        return jsonify(road_view(cid))

    @api.delete('/couples/<cid>/road/obligations/<rid>')
    def obligation_delete(cid,rid):
        json_object();road_service.remove_obligation(get_db(),uid(),cid,rid)
        return jsonify(road_view(cid))

    @api.put('/couples/<cid>/road/sharing')
    def road_share(cid):
        road_service.share(get_db(),uid(),cid,json_object(required={'slots'})['slots'],monday(),derive)
        return jsonify(road_view(cid))

    @api.put('/couples/<cid>/road/vision')
    def road_vision(cid):
        road_service.vision_set(get_db(),uid(),cid,json_object(required={'request_id','key','stance'},optional={'disclosed_to_partner'}),get_clock(),vision_options)
        return jsonify(road_view(cid))

    @api.post('/couples/<cid>/exits')
    def exit_create(cid):
        eid=service.exit_start(get_db(),uid(),cid,json_object(required={'stage'}),get_clock())
        return jsonify(service.exit_read(get_db(),uid(),cid,eid))

    @api.get('/couples/<cid>/exits/<eid>')
    def exit_read(cid,eid):return jsonify(service.exit_read(get_db(),uid(),cid,eid))

    def exit_handler(action):
        def handle(cid,eid):
            body=json_object(required={'acknowledged'} if action=='interview' else {'declined'} if action=='feedback' else set(),optional={'text'} if action=='feedback' else set())
            service.exit_action(get_db(),uid(),cid,eid,action,body,get_clock(),today())
            return jsonify(service.exit_read(get_db(),uid(),cid,eid))
        return handle
    for action in ('interview','feedback','reentry'):
        api.add_url_rule('/couples/<cid>/exits/<eid>/'+action,endpoint='exit_'+action,view_func=exit_handler(action),methods=['POST'])
