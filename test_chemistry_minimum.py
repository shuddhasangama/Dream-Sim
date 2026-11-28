"""Client answer 4: Chemistry needs at least 4 activities, from the catalogue or the
member's own; members can add their own. Enforced on the server for the app (API)
and the old web page."""
import json

import db
from test_segment_efg_routes import RouteTestCase


class ChemistryMinimumTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.login(self.make_user('owner'))

    def skills(self):
        return json.loads(db.fetch_one(self.conn, 'User', id='owner')['skills_json'] or '{}')

    def api_put(self, body):
        return self.client.put('/api/v1/profile/chemistry/activities', json=body)

    def test_api_refuses_three_and_counts_own_activities(self):
        r = self.api_put({'activities': {'Cooking': 'good', 'Hiking': 'good', 'Yoga': 'maybe'}, 'custom_activities': [], 'partner_any': []})
        self.assertEqual(r.status_code, 400)
        self.assertIn('at least 4', r.json['error']['message'])
        r = self.api_put({'activities': {'Cooking': 'good', 'Hiking': 'good', 'Yoga': 'maybe', 'Kite flying': 'good'},
                          'custom_activities': ['Kite flying'], 'partner_any': []})
        self.assertEqual(r.status_code, 200, r.json)
        read = self.client.get('/api/v1/profile/chemistry').json['data']
        self.assertEqual(read['min_activities'], 4)
        self.assertIn('Kite flying', read['custom_activities'])

    def test_web_page_adds_own_activity_keeps_it_and_refuses_fewer_than_four(self):
        page = self.client.get('/chemistry').get_data(as_text=True)
        self.assertIn('name="new_activity"', page)
        self.assertIn('at least 4 activities', page)
        form = {'act__Cooking': 'good', 'act__Hiking': 'good', 'act__Yoga': 'maybe',
                'new_activity': 'Kite flying', 'new_activity_bucket': 'good'}
        self.assertEqual(self.client.post('/chemistry/activities', data=form).status_code, 302)
        self.assertEqual(self.skills()['custom_activities'], ['Kite flying'])
        self.assertEqual(len(self.skills()['activities']), 4)
        # Saving again from the web page keeps the member's own activity (it used to be dropped).
        page = self.client.get('/chemistry').get_data(as_text=True)
        self.assertIn('Kite flying', page)
        again = {'act__Cooking': 'improve', 'act__Hiking': 'good', 'act__Yoga': 'maybe', 'act__Kite flying': 'good'}
        self.client.post('/chemistry/activities', data=again)
        self.assertEqual(self.skills()['custom_activities'], ['Kite flying'])
        self.assertEqual(self.skills()['activities']['Cooking'], 'improve')
        # Three is refused and nothing changes.
        before = self.skills()
        self.client.post('/chemistry/activities', data={'act__Cooking': 'good', 'act__Hiking': 'good', 'act__Yoga': 'maybe'})
        self.assertEqual(self.skills(), before)
        self.assertIn('at least 4', self.client.get('/chemistry').get_data(as_text=True))
