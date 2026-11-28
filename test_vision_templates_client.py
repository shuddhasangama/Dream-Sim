"""Client answer 1: four pillars - Intimacy (Physical, Emotional), Kids, Cohabitate, Travel.
Family = all 4; Together = all except Kids; Travel together = Emotional intimacy + Travel;
Custom = the member defines their own pillars (up to four of their own)."""
import json

import db
import vision_plans
from test_segment_efg_routes import RouteTestCase


class VisionTemplateTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.login(self.make_user('owner'))

    def put(self, body):
        return self.client.put('/api/v1/profile/vision/template', json={'schema_version': 2, **body})

    def stats(self):
        return json.loads(db.fetch_one(self.conn, 'User', id='owner')['stats_json'])

    def test_templates_are_the_clients(self):
        self.assertEqual(vision_plans.OPTIONS['Intimacy'], ['Emotional', 'Physical'])
        self.assertEqual(set(vision_plans.OPTIONS), {'Intimacy', 'Kids', 'Cohabitate', 'Travel together'})
        presets = {p['key']: p for p in vision_plans.PRESETS}
        self.assertEqual(set(presets['grow']['choices']), set(vision_plans.OPTIONS))
        self.assertEqual(set(presets['two']['choices']), {'Intimacy', 'Cohabitate', 'Travel together'})
        self.assertEqual(presets['explore']['choices'], {'Intimacy': ['Emotional'], 'Travel together': []})
        self.assertEqual([vision_plans.LABELS[k] for k in ('grow', 'two', 'explore', 'custom')],
                         ['Family', 'Together', 'Travel together', 'Custom'])

    def test_custom_plan_takes_the_members_own_pillars(self):
        r = self.put({'template': 'custom', 'pillars': {'Intimacy': ['Emotional'], 'Kids': []}, 'custom_pillars': ['Faith', '  Music  ']})
        self.assertEqual(r.status_code, 200, r.json)
        self.assertEqual(r.json['data']['custom_pillars'], ['Faith', 'Music'])
        self.assertEqual(self.stats()['vision_custom_pillars'], ['Faith', 'Music'])
        # A standard pillar set plus own pillars is still the Custom plan.
        r = self.put({'template': 'custom', 'pillars': {'Intimacy': ['Emotional'], 'Travel together': []}, 'custom_pillars': ['Faith']})
        self.assertEqual(r.status_code, 200, r.json)
        # Choosing a standard plan clears them; matching keys stay the four.
        r = self.put({'template': 'explore', 'pillars': {'Intimacy': ['Emotional'], 'Travel together': []}})
        self.assertEqual(r.status_code, 200, r.json)
        self.assertNotIn('vision_custom_pillars', self.stats())
        keys = {g['key'] for g in json.loads(db.fetch_one(self.conn, 'User', id='owner')['vision_json'])}
        self.assertLessEqual(keys, set(vision_plans.OPTIONS))

    def test_own_pillars_are_validated(self):
        base = {'template': 'custom', 'pillars': {'Intimacy': ['Emotional'], 'Kids': []}}
        for bad in (['Kids'], ['Travel'], ['a', 'A'], [''], ['x' * 41], ['1', '2', '3', '4', '5'], 'Faith'):
            self.assertEqual(self.put({**base, 'custom_pillars': bad}).status_code, 400, bad)
        self.assertEqual(self.put({'template': 'grow', 'pillars': {k: (['Emotional'] if k == 'Intimacy' else []) for k in vision_plans.OPTIONS},
                                   'custom_pillars': ['Faith']}).status_code, 400)

    def test_old_web_vision_page_shows_and_edits_own_pillars(self):
        self.put({'template': 'custom', 'pillars': {'Intimacy': ['Emotional'], 'Kids': []}, 'custom_pillars': ['Faith']})
        page = self.client.get('/vision').get_data(as_text=True)
        self.assertIn('Your own pillars', page)
        self.assertIn('Faith', page)
        self.client.post('/vision/own-pillars', data={'add': 'Music', 'remove': ['Faith']})
        self.assertEqual(self.stats()['vision_custom_pillars'], ['Music'])
        self.put({'template': 'explore', 'pillars': {'Intimacy': ['Emotional'], 'Travel together': []}})
        self.client.post('/vision/own-pillars', data={'add': 'Music'})
        self.assertNotIn('vision_custom_pillars', self.stats())          # only on the Custom plan
