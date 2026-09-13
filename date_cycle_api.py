"""Date-scoped JSON debrief. Only the actor's private feedback is returned."""
from flask import g, jsonify
import db
import guru_dating
import dateplan
import payments
import date_cycle_service as service
from api_contract import json_object


def register(api,get_db,get_clock,epoch):
    def view(pid):
        uid=g.api_user['user_id']
        pair,plan=service.owned(get_db(),uid,pid)
        mine=service.submission(get_db(),uid,pid)
        done=service.receipt(get_db(),pid)
        times=service.timing(plan,get_clock(),epoch)
        row=service.outcome(get_db(),pid)
        role='a' if pair['user_a']==uid else 'b'
        peer='b' if role=='a' else 'a'
        other=pair['user_b'] if role=='a' else pair['user_a']
        their=service.submission(get_db(),other,pid)
        eligible=plan['status']=='confirmed' and pair['status']=='active' and not done and g.api_user['bgv_status']=='verified' and g.api_user['journey_state']=='dating'
        return {'plan_id':pid,'status':plan['status'],'clock_mode':'simulation','opens_at':times['opens_at'],
            'feedback_open':eligible and times['open'] and not times['closed'], 'cancellable':eligible and not times['started'],
            'cancellation':dateplan.cancellation(times['notice_hours'],payments.fee(payments.CANCELLATION)['amount_inr']),
            'my_feedback':{'green_flags':row.get(role+'_green_flags',[]),'red_flags':row.get(role+'_red_flags',[]),
                'decision':row.get(role+'_decision'),'reason':row.get(role+'_reason'),
                'photo_consent':{k:mine.get('flags',{}).get(k,False) for k in ('together_photo','bill_photo')},
                'no_show_reported':mine.get('no_show_reported',False)},
            'partner_submitted':bool(row.get(peer+'_decision')),
            'mutual_photo_consent':{k:bool(mine.get('flags',{}).get(k,False) and their.get('flags',{}).get(k,False)) for k in ('together_photo','bill_photo')},
            'resolution':done['kind'] if done else 'pending',
            'no_show_is_confirmed':False,
            'green_flag_options':guru_dating.GREEN_FLAGS,'red_flag_options':guru_dating.RED_FLAGS,
            'decision_options':['continue','relationship','pass']}

    @api.get('/date-plans/<pid>/debrief')
    def get_debrief(pid):
        return jsonify(view(pid))

    @api.put('/date-plans/<pid>/feedback/flags')
    def flags(pid):
        body=json_object(required={'green_flags','red_flags'},optional={'together_photo','bill_photo'})
        service.flags(get_db(),g.api_user['user_id'],pid,body,get_clock(),epoch)
        return jsonify(view(pid))

    @api.post('/date-plans/<pid>/feedback/decision')
    def decision(pid):
        body=json_object(required={'decision'},optional={'reason'})
        service.decide(get_db(),g.api_user['user_id'],pid,body,get_clock(),epoch)
        return jsonify(view(pid))

    @api.post('/date-plans/<pid>/cancel')
    def cancel(pid):
        json_object()
        service.cancel(get_db(),g.api_user['user_id'],pid,get_clock(),epoch)
        return jsonify(view(pid))

    @api.post('/date-plans/<pid>/no-show')
    def no_show(pid):
        json_object()
        service.no_show(get_db(),g.api_user['user_id'],pid,get_clock(),epoch)
        return jsonify(view(pid))

    @api.post('/date-plans/<pid>/feedback/reconcile')
    def reconcile(pid):
        json_object()
        service.reconcile(get_db(),g.api_user['user_id'],pid,get_clock(),epoch)
        return jsonify(view(pid))
