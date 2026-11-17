import unittest
import auth
class PhoneCountryTests(unittest.TestCase):
    def test_india_length(self):
        self.assertEqual(auth.normalize('phone','+919876543210'),'+919876543210')
        for v in ('+91987654321','+9198765432101','+91987654abcd'):
            self.assertIsNone(auth.normalize('phone',v))
    def test_disabled_country(self):
        self.assertIsNone(auth.normalize('phone','+14155552671'))
    def test_stored_records_unchanged(self):
        self.assertEqual(auth.normalize('phone','14155552671',stored=True),'+14155552671')
