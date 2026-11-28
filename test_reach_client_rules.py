"""Client answer 5: REACH filters are Stats-only and follow the member's own Stats;
unverified members see verified AND unverified, verified members see ONLY verified
(REACH counts, match lists and weekly matching share one rule)."""
import unittest

import matching
import reach_access


def member(uid, gender, status='verified', **prefs):
    return {'user_id': uid, 'gender': gender, 'city': 'Bangalore', 'bgv_status': status, 'journey_state': 'dating',
            'visions': [{'key': 'Intimacy', 'stance': ['Emotional']}], 'stats': {'age': 30, 'height_cm': 170},
            'preferences': {'fixed': {'dealbreakers': []}, 'adjustable': {}, **prefs}}


class ReachClientRuleTests(unittest.TestCase):
    def test_one_visibility_rule(self):
        verified, unverified = member('v', 'female'), member('u', 'female', 'declared')
        self.assertTrue(reach_access.visible(verified, member('v2', 'male')))
        self.assertFalse(reach_access.visible(verified, member('u2', 'male', 'pending')))
        self.assertTrue(reach_access.visible(unverified, member('v2', 'male')))
        self.assertTrue(reach_access.visible(unverified, member('u2', 'male', 'declared')))

    def test_weekly_candidates_for_a_verified_member_are_verified_only(self):
        me = member('me', 'female')
        pool = [me, member('ok', 'male'), member('no', 'male', 'pending')]
        self.assertEqual([c['user_id'] for c in matching.eligible_candidates(me, pool, set(), set())], ['ok'])

    def test_filters_are_stats_only(self):
        me = member('me', 'female', health_openness={'mode': 'specific', 'categories': ['mobility'], 'include_undisclosed': False},
                    work_verification={'categories': ['Salaried'], 'verified_only': True, 'max_age_days': 90, 'include_undisclosed': False})
        other = member('other', 'male')
        self.assertTrue(matching.fits_filters(me, other))          # health / checks no longer filter
        me['preferences']['adjustable'] = {'height_cm': [180, 190]}
        self.assertFalse(matching.fits_filters(me, other))         # a Stats filter still does

    def test_filters_follow_the_members_own_stats(self):
        got = matching.unlock_levers_for({'adjustable': {}}, {'age': 30, 'height_cm': 165})['adjustable']
        self.assertEqual(got['age'], [24, 36])
        self.assertEqual(got['height_cm'], [153, 177])
        self.assertNotIn('weight_kg', got)                         # no stat given: no filter
        kept = matching.unlock_levers_for({'adjustable': {'age': [25, 28]}}, {'age': 30})['adjustable']
        self.assertEqual(kept['age'], [25, 28])                    # never overwrites a member's own range
