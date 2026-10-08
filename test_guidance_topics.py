import disclosure as d
from journey_api import topic_stage

def test_topics_follow_actions_not_historical_date_milestone():
    reached={d.VERIFIED,d.MATCHED,d.DATE_SET,d.FIRST_DATE}
    assert topic_stage(reached, {'has_current_plan':False,'dates_completed':1})=='repeat_planning'
    assert topic_stage(reached, {'debrief_open':True})=='debrief'
    assert topic_stage(reached, {'debrief_open':True,'decision_made':True})=='post_debrief'
    assert topic_stage(reached, {'gate_open':True})=='relationship'
    assert topic_stage(reached, {'date_confirmed':True})=='before_date'
