"""vis-chem: server validation of the Chemistry save (chemistry_choices.validate)."""
import unittest

import onboarding
from api_contract import ApiError
from chemistry_choices import validate

FOUR = {name: 'good' for name in onboarding.ACTIVITIES[:onboarding.MIN_SORTED]}


class ValidateTests(unittest.TestCase):
    def rejects(self, *args):
        with self.assertRaises(ApiError):
            validate(*args)

    def test_a_valid_save(self):
        acts = {**FOUR, 'Marathon running': 'improve'}
        out = validate(acts, ['Marathon running'], ['Cooking'])
        self.assertEqual(out['custom_activities'], ['Marathon running'])
        self.assertEqual(out['partner_any'], ['Cooking'])

    def test_minimum_answers_required(self):
        self.rejects(dict(list(FOUR.items())[:onboarding.MIN_SORTED - 1]), [], [])

    def test_custom_activity_rules(self):
        five = [f'Custom {n}' for n in range(5)]
        self.rejects({**FOUR, **{n: 'good' for n in five}}, five, [])                 # at most four
        for bad in (' padded', 'x' * 61, '', 'tab\there', 'Cooking', 'cooking', 'ＣＯＯＫＩＮＧ'):
            self.rejects({**FOUR, bad: 'good'}, [bad], [])                           # trimmed, length, control, duplicates
        self.rejects({**FOUR, 'Chess': 'good', 'chess': 'good'}, ['Chess', 'chess'], [])
        self.rejects({**FOUR}, ['Chess'], [])                                         # a custom activity needs an answer

    def test_answers_and_partner_flag_rules(self):
        self.rejects({**FOUR, 'Cooking': 'excellent'}, [], [])                         # only listed answers
        self.rejects({**FOUR, 'Unknown thing': 'good'}, [], [])                       # only listed or custom activities
        self.rejects(FOUR, [], ['Hiking'] if 'Hiking' not in FOUR else ['Unknown'])   # partner flag only on answered items
        self.rejects(FOUR, [], ['Cooking', 'Cooking'])                                # no duplicates


if __name__ == '__main__':
    unittest.main()
