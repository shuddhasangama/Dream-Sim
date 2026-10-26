import unittest
from restaurant_preferences import matches, provider_values, per_person_minor, CUISINES


class PreferenceTests(unittest.TestCase):
    def test_unrestricted_does_not_require_a_restaurant_tag(self):
        self.assertTrue(matches(['Thai'], ['Everything'], ['thai'], []))
        self.assertTrue(matches(['Thai'], ['Everything', 'Vegetarian'], ['thai'], ['vegetarian']))
        self.assertFalse(matches(['Thai'], ['Vegetarian'], ['Thai'], ['Everything']))

    def test_restrictions_require_explicit_suitability(self):
        for diet in ['Jain', 'Halal', 'Vegan', 'No red meat', 'Eggetarian']:
            self.assertFalse(matches(['Thai'], [diet], ['Thai'], ['Vegetarian']))
            self.assertTrue(matches(['Thai'], [diet], ['Thai'], [diet]))
        with self.assertRaises(ValueError):
            matches(['Thai'], ['unknown restriction'], ['Thai'], [])

    def test_explicit_mapping_and_missing_mapping(self):
        self.assertEqual(provider_values(['North Indian'], CUISINES, {'north_indian': 42}), [42])
        with self.assertRaises(ValueError):
            provider_values(['Levantine'], CUISINES, {'north_indian': 42})

    def test_price_basis(self):
        self.assertEqual(per_person_minor(100001, 'party_total'), 50001)
        self.assertEqual(per_person_minor(100001, 'per_person'), 100001)
        with self.assertRaises(ValueError):
            per_person_minor(100, 'unknown')
