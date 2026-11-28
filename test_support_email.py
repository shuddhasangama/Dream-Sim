"""Client answer 8 (2026-11-27): hello@dhashu.com is the one support contact, on the
web pages, in the app, and on the public /delete-account page."""
import re
import unittest
from pathlib import Path

import brand
import member_lock
from test_segment_efg_routes import RouteTestCase, app_module

ROOT = Path(__file__).parent
SUPPORT = 'hello@dhashu.com'


class SupportEmailTests(unittest.TestCase):
    def test_one_constant(self):
        self.assertEqual(brand.SUPPORT_EMAIL, SUPPORT)
        self.assertIn(SUPPORT, member_lock.MESSAGE)
        self.assertIn(f"SUPPORT_EMAIL = '{SUPPORT}'", (ROOT / 'mobile/src/config.js').read_text(encoding='utf-8'))

    def test_public_delete_account_page_shows_it_and_the_retention(self):
        body = app_module.app.test_client().get('/delete-account').get_data(as_text=True)
        self.assertIn(f'mailto:{SUPPORT}', body)
        self.assertIn('2 years', body)
        self.assertNotIn("from the app's Settings page", body)

    def test_no_other_support_address_is_shown(self):
        pattern = re.compile(r'(?:support|help|hello|contact|care)@[a-z0-9.-]+', re.I)
        files = list(ROOT.glob('templates/*.html')) + list((ROOT / 'mobile/src').rglob('*.js')) + [ROOT / 'brand.py']
        found = {m.group(0).lower() for f in files for m in pattern.finditer(f.read_text(encoding='utf-8'))}
        self.assertEqual(found, {SUPPORT})


class SupportOnWebPagesTests(RouteTestCase):
    def test_signed_in_pages_show_the_support_footer(self):
        self.login(self.make_user('owner'))
        for path in ('/dashboard', '/account/delete'):
            body = self.client.get(path).get_data(as_text=True)
            self.assertIn(f'mailto:{SUPPORT}', body, path)


if __name__ == '__main__':
    unittest.main()
