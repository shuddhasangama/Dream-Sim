"""Client answer 6: height entered and shown in cm and feet/inches, stored once (cm),
with the same validation in both units (web pages here; the app in mobile/tests)."""
import json
import unittest

import db
import height_units as h
import onboarding
from test_segment_efg_routes import RouteTestCase


class HeightUnitTests(unittest.TestCase):
    def test_conversion_and_labels(self):
        self.assertEqual(h.ft_in_to_cm(5, 7), 170)
        self.assertEqual(h.cm_to_ft_in(170), (5, 7))
        self.assertEqual(h.label(170), '170 cm (5′ 7″)')
        self.assertEqual(h.label(None), '')
        self.assertEqual(h.ft_in_range(140, 210), ((4, 7), (6, 10)))   # 6'11" = 211 cm is outside

    def test_same_range_in_both_units(self):
        self.assertEqual(h.from_form({'height_cm': '170'}), (170, None))
        self.assertEqual(h.from_form({'height_ft': '5', 'height_in': '7'}), (170, None))
        self.assertEqual(h.from_form({'height_ft': '4', 'height_in': '7'})[0], 140)
        self.assertEqual(h.from_form({'height_ft': '6', 'height_in': '10'})[0], 208)
        for form in ({'height_cm': '139'}, {'height_cm': '211'}, {'height_ft': '4', 'height_in': '6'},
                     {'height_ft': '6', 'height_in': '11'}, {'height_ft': '5', 'height_in': '12'},
                     {'height_ft': 'five'}):
            value, error = h.from_form(form)
            self.assertIsNone(value, form)
            self.assertTrue(error, form)
        self.assertIn("4′ 7″", h.from_form({'height_cm': '139'})[1])  # the message shows both units
        self.assertEqual(h.from_form({}), (None, None))

    def test_unchanged_cm_with_changed_feet_and_inches(self):
        self.assertEqual(h.from_form({'height_cm': '170', 'height_cm_was': '170', 'height_ft': '6', 'height_in': '0'})[0], 183)
        # untouched: 171 cm shows as 5'7" (170 cm) and must stay 171
        self.assertEqual(h.from_form({'height_cm': '171', 'height_cm_was': '171', 'height_ft': '5', 'height_in': '7'})[0], 171)
        self.assertEqual(h.from_form({'height_cm': '180', 'height_cm_was': '170', 'height_ft': '5', 'height_in': '7'})[0], 180)

    def test_signup_wizard_accepts_feet_and_inches(self):
        form = {'age': '31', 'city': 'Chennai', 'gender': 'female', 'height_ft': '5', 'height_in': '7'}
        result = onboarding.validate_stats(form)
        self.assertTrue(result['ok'], result['error'])
        self.assertEqual(result['stats']['height_cm'], 170)
        self.assertFalse(onboarding.validate_stats({**form, 'height_in': '13'})['ok'])


class HeightWebPageTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.login(self.make_user('owner'))

    def height(self):
        return json.loads(db.fetch_one(self.conn, 'User', id='owner')['stats_json']).get('height_cm')

    def test_stats_page_shows_both_units_and_saves_either(self):
        page = self.client.get('/stats').get_data(as_text=True)
        self.assertIn('name="height_ft"', page)
        self.assertIn('name="height_in"', page)
        self.client.post('/stats/save', data={'height_cm': '', 'height_ft': '5', 'height_in': '7', 'height_cm_was': ''})
        self.assertEqual(self.height(), 170)
        self.client.post('/stats/save', data={'height_cm': '172', 'height_ft': '5', 'height_in': '7', 'height_cm_was': '170'})
        self.assertEqual(self.height(), 172)
        self.client.post('/stats/save', data={'height_cm': '', 'height_ft': '7', 'height_in': '2', 'height_cm_was': '172'})
        self.assertEqual(self.height(), 172)                        # out of range in feet: refused, unchanged
        self.assertIn('Height should be between', self.client.get('/stats').get_data(as_text=True))
        self.assertIn('172 cm (5′ 8″)', self.client.get('/dashboard').get_data(as_text=True))
