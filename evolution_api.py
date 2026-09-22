"""Own-profile resources with explicit disclosure and editing constraints."""
from flask import g, jsonify
import db
import chemistry
import expectations
import onboarding
import stats_edit
import vision
import evolution_service as service
from api_contract import ApiError, json_object, allowlist


def register(api,get_db,get_clock,stats_situation,milestones):
    def uid(): return g.api_user['user_id']
    def guard(key):
        reached=milestones(g.api_user)
        if key=='physical_boundary':
            ready='date_set' in reached or 'first_date' in reached or 'relationship' in reached
        else:
            ready='first_date' in reached or 'relationship' in reached
        if not ready:
            raise ApiError('disclosure_locked','This question is not available at your current stage.',403)
        # Chemistry required at entry must be answerable before entry, unlike
        # the old Vibes navigation which created a circular prerequisite.
        if key in (*expectations.FOLLOWS_PACE, expectations.HEALTH):
            rows=db.fetch_all(get_db(),'ChemistryEntry',user_id=uid())
            answers={r['key']:r['value'] for r in rows}
            pace=next((r for r in rows if r['key']==expectations.PACE),{})
            if key not in expectations.visible_keys(answers,pace.get('updated_at_hours'),service.hours(get_clock())):
                raise ApiError('question_not_open','Answer pace first and allow the reflection interval.',409)

    @api.get('/profile/stats')
    def stats_editor():
        verified_fields=stats_edit.verified_field_set(db.fetch_all(get_db(),'Verification',user_id=uid()))
        return jsonify(rows=stats_edit.rows(g.api_user['stats'],stats_situation(g.api_user),verified_fields),
            options=onboarding.STAT_OPTIONS,ranges=onboarding.STAT_RANGES,
            changes=db.fetch_all(get_db(),'StatChange',user_id=uid()))

    @api.patch('/profile/stats')
    def stats_update():
        body=json_object(required={'fields'})
        return jsonify(service.save_stats(get_db(),uid(),body['fields'],lambda:stats_situation(g.api_user),get_clock(),strict=True))

    @api.post('/profile/stats/reverification')
    def reverification():
        body=json_object(required={'fields'})
        fields=body['fields']
        if type(fields) is not list or not fields or any(not isinstance(k,str) or k not in stats_edit.VERIFIED for k in fields):
            raise ApiError('validation_error','Select verified fields only.')
        with service.transaction(get_db()):
            for field in set(fields):
                key=stats_edit.bgv_field(field)
                old=db.fetch_one(get_db(),'Verification',user_id=uid(),field=key)
                db.insert_row(get_db(),'Verification',{**(old or {'id':f'{uid()}:{key}'}),'user_id':uid(),'field':key,'status':'in_review','note':'Re-check requested by the user.','updated_at':str(get_clock())})
        return jsonify(status='in_review',provider_mode='manual_review_required',verification_granted=False)

    @api.get('/profile/vision')
    def vision_read():
        # round3-fixes-spec.md §7: pillar_options carries the real
        # sub-selection lists (empty for Travel together) so a client
        # never hardcodes them, plus the explanatory copy §7.1 asks to
        # show next to the picker, and whether RC is open right now
        # (declare_change()'s own gate — surfaced ahead of time so the
        # UI can show why it's locked rather than just disabling it).
        return jsonify(goals=g.api_user['visions'],element_keys=vision.VISION_ELEMENT_KEYS,
            presets=[{'key':'marriage','label':'Marriage','choices':vision.marriage_choices()}],
            pillar_options={k:list(v) for k,v in vision.PILLAR_OPTIONS.items()},
            detail_explanation=vision.VISION_DETAIL_EXPLANATION,
            rc_open=vision.rc_open(get_clock()),
            entries=db.fetch_all(get_db(),'VisionEntry',user_id=uid()),changes=db.fetch_all(get_db(),'VisionChange',user_id=uid()))

    @api.post('/profile/vision/details')
    def vision_detail():
        body=json_object(required={'request_id','pillar'},optional={'sub_selection'})
        return jsonify(service.add_vision_detail(get_db(),uid(),body,get_clock()))

    @api.post('/profile/vision/presets')
    def vision_preset():
        body=json_object(required={'request_id','preset'})
        return jsonify(service.apply_vision_preset(get_db(),uid(),body,get_clock()))

    @api.post('/profile/vision/changes')
    def vision_change():
        body=json_object(required={'request_id','pillar','disclosed_to_partner'},optional={'add','remove'})
        return jsonify(service.declare_vision_change(get_db(),uid(),body,get_clock()))

    @api.get('/profile/chemistry')
    def chemistry_read():
        rows=db.fetch_all(get_db(),'ChemistryEntry',user_id=uid())
        answers={r['key']:r['value'] for r in rows}
        pace=next((r for r in rows if r['key']==expectations.PACE),{})
        # skills_json is {"activities": {...flat map...}, "by_bucket": {...}}
        # (onboarding.build_skills's own shape) — the flat map is what a
        # client actually renders per-activity, same as chemistry_view()'s
        # own chosen = skills.get('activities', {}). Forwarding the raw
        # blob here made every save look like it hadn't persisted: the
        # response's `activities` never matched an ACTIVITIES key, so no
        # radio ever came back checked.
        skills=db.load_json_field(db.fetch_one(get_db(),'User',id=uid())['skills_json'],{})
        return jsonify(activities=skills.get('activities',{}),
            activity_options=onboarding.ACTIVITIES,buckets=onboarding.BUCKETS,
            answers=answers,entry_keys=(*chemistry.MANDATORY_KEYS,*chemistry.INTIMACY_MANDATORY_KEYS),
            options={'physical_boundary':chemistry.PHYSICAL_BOUNDARY_OPTIONS,'intimacy_pace':chemistry.INTIMACY_PACE_OPTIONS,'health_openness':chemistry.HEALTH_OPENNESS_OPTIONS},
            pacing=expectations.state(answers,pace.get('updated_at_hours'),service.hours(get_clock())))

    @api.put('/profile/chemistry/activities')
    def activities_update():
        service.save_activities(get_db(),uid(),json_object(required={'activities'})['activities'])
        return chemistry_read()

    @api.put('/profile/chemistry/entries/<key>')
    def entry_update(key):
        service.save_entry(get_db(),uid(),key,json_object(required={'value'})['value'],get_clock(),guard)
        return chemistry_read()
