import unittest
import matching
import profile_choices
from date_readiness import describe


class ConsistencyTests(unittest.TestCase):
    def user(self, accepted, declared=()):
        return {'preferences':{'fixed':{'dealbreakers':[]},'adjustable':{},
                    'health_openness':{'mode':'specific','categories':accepted,'include_undisclosed':False}},
                'stats':{'health_shared':{'consent':True,'categories':list(declared)}}}

    def test_broad_and_specific_are_not_interchangeable(self):
        self.assertTrue(profile_choices.health_fits(self.user(['sensory']),self.user([],['hearing'])))
        self.assertFalse(profile_choices.health_fits(self.user(['hearing']),self.user([],['sensory'])))
        self.assertFalse(profile_choices.health_fits(self.user(['trauma']),self.user([],['mental_health'])))
        self.assertFalse(profile_choices.health_fits(self.user(['hearing']),self.user([],['hearing','mobility'])))

    def test_show_all_and_restore_preserve_private_choices(self):
        a,b=self.user(['hearing']),self.user([],['mobility'])
        widened=matching.set_ignored_all(a,True)
        self.assertTrue(profile_choices.health_fits(widened,b))
        self.assertEqual(widened['preferences']['health_openness'],a['preferences']['health_openness'])
        self.assertFalse(profile_choices.health_fits(matching.set_ignored_all(widened,False),b))

    def test_date_readiness_is_not_inferred_from_time_or_one_signature(self):
        self.assertEqual(describe({'status':'pending_signatures'})['state'],'proposed')
        self.assertEqual(describe({'status':'pending_signatures'},True)['state'],'awaiting_partner')
        self.assertEqual(describe({'status':'confirmed'})['state'],'confirmed')
        self.assertEqual(describe({'status':'confirmed'},awaiting_next=True)['state'],'completed')
        for state in ('cancelled','no_show_reported'):
            self.assertEqual(describe({'status':state})['state'],state)
