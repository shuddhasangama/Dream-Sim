"""Client answer 3: date preferences (neighbourhood, diet, cuisine, budget) are optional
at signup and mandatory before a match is accepted or a date is planned, with a clear
prompt at that point (app: 409 date_preferences_required; web: the preferences page)."""
import json

import date_preferences
import db
import onboarding
import test_week_api


class DatePreferencesTests(test_week_api.WeekApiTests):
    # Reuse the fixture only, not the inherited week tests.
    locals().update({name: None for name in dir(test_week_api.WeekApiTests) if name.startswith('test_')})

    def clear(self, uid, *fields):
        stats = json.loads(db.fetch_one(self.conn, 'User', id=uid)['stats_json'])
        for field in fields:
            stats.pop(field, None)
        self.conn.execute('UPDATE User SET stats_json=? WHERE id=?', (json.dumps(stats), uid))
        self.conn.commit()

    def stats(self, uid='owner'):
        return json.loads(db.fetch_one(self.conn, 'User', id=uid)['stats_json'])

    def test_missing_rule(self):
        full = {'city': 'Bangalore', 'neighbourhoods': ['indiranagar'], 'diet': 'Vegan', 'cuisine': ['Thai'], 'budget': ['x']}
        self.assertEqual(date_preferences.missing(full), [])
        self.assertEqual(date_preferences.missing({'city': 'Bangalore'}), ['neighbourhoods', 'diet', 'cuisine', 'budget'])
        # A city with no neighbourhood list cannot ask for one.
        self.assertEqual(date_preferences.missing({**full, 'city': 'Atlantis', 'neighbourhoods': []}), [])

    def test_accepting_a_match_needs_them_with_a_clear_prompt(self):
        self.clear('owner', 'cuisine', 'neighbourhoods')
        mid = self.match('owner', 'partner')
        r = self.request('/matches/'+mid+'/actions', method='POST', body={'action': 'interest'})
        self.assertEqual(r.status_code, 409, r.json)
        self.assertEqual(r.json['error']['code'], 'date_preferences_required')
        self.assertIn('Before you accept a match, complete your date preferences: Neighbourhood, Cuisine.', r.json['error']['message'])
        self.assertEqual(db.fetch_one(self.conn, 'Match', id=mid)['action'], 'none')        # nothing recorded
        # Passing never needs them.
        self.assertEqual(self.request('/matches/'+mid+'/actions', method='POST', body={'action': 'pass'}).status_code, 200)

    def test_fill_them_in_then_accept(self):
        self.clear('owner', 'cuisine', 'budget', 'neighbourhoods', 'diet')
        read = self.request('/profile/date-preferences').json['data']
        self.assertEqual(read['missing'], ['neighbourhoods', 'diet', 'cuisine', 'budget'])
        self.assertTrue(read['options']['neighbourhoods'])
        body = {'neighbourhoods': ['indiranagar'], 'diet': 'Vegan', 'cuisine': ['Thai'], 'budget': [onboarding.STAT_OPTIONS['budget'][0]]}
        saved = self.request('/profile/date-preferences', method='PUT', body=body)
        self.assertEqual(saved.status_code, 200, saved.json)
        self.assertEqual(saved.json['data']['missing'], [])
        self.assertEqual(self.stats()['cuisine'], ['Thai'])
        mid = self.match('owner', 'partner')
        self.assertEqual(self.request('/matches/'+mid+'/actions', method='POST', body={'action': 'interest'}).status_code, 200)

    def test_save_validates_and_never_changes_a_set_diet(self):
        bad = [{'cuisine': ['Martian']}, {'budget': ['free']}, {'neighbourhoods': ['nowhere']}, {'diet': 'Fruitarian'},
               {'unknown': 1}, {'neighbourhoods': ['indiranagar', 'koramangala', 'mg-road', 'whitefield']}]
        for body in bad:
            self.assertEqual(self.request('/profile/date-preferences', method='PUT', body=body).status_code, 400, body)
        r = self.request('/profile/date-preferences', method='PUT', body={'diet': 'Vegan'})   # fixture diet is set
        self.assertEqual(r.status_code, 400)
        self.assertIn('Stats', r.json['error']['message'])

    def test_planning_a_date_needs_them(self):
        self.make_lockin('owner', 'partner')
        self.clear('owner', 'budget')
        r = self.request('/lock-ins/lock-1/availability', method='PUT', body={'slots': [{'day': 'Sat', 'meal_slot': 'dinner'}]})
        self.assertEqual(r.status_code, 409, r.json)
        self.assertEqual(r.json['error']['code'], 'date_preferences_required')
        self.assertIn('Before you plan a date', r.json['error']['message'])
        self.assertEqual(db.fetch_all(self.conn, 'Availability'), [])

    def test_web_pages_prompt_and_come_back(self):
        self.clear('owner', 'cuisine')
        mid = self.match('owner', 'partner')
        with self.client.session_transaction() as sess:
            sess['user_id'] = 'owner'
        from test_segment_efg_routes import app_module
        import unittest.mock as mock
        with mock.patch.dict(app_module.app.config, {'AUTH_ENABLED': False}):
            r = self.client.post('/week/act', data={'match_id': mid, 'action': 'interest'})
            self.assertEqual(r.headers['Location'], '/date-preferences')
            page = self.client.get('/date-preferences').get_data(as_text=True)
            self.assertIn('Before you accept a match, complete your date preferences: Cuisine.', page)
            current = self.stats()   # the browser submits every ticked box on the page
            r = self.client.post('/date-preferences', data={'cuisine': ['Thai'], 'neighbourhoods': current['neighbourhoods'],
                                                             'budget': current['budget']})
            self.assertEqual(r.status_code, 302)
            self.assertEqual(r.headers['Location'], '/week')
        self.assertEqual(self.stats()['cuisine'], ['Thai'])

    def test_signup_still_allows_them_to_be_skipped(self):
        # Optional at signup: the modern signup body needs no date preferences.
        import self_signup
        self.assertNotIn('neighbourhoods', {'age', 'gender', 'city', 'fields', 'health'})
        self.assertIn('neighbourhoods', self_signup.FIELDS)          # accepted, never required
