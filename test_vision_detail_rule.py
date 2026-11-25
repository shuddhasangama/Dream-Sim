"""Owner decision (2026-11-25): "Add detail" and "Declare a change" only for items
that have detail (vision_plans.DETAIL_OPTIONS; today Intimacy). Enforced by the API
for current (v2) Vision members; older profiles keep their existing behaviour."""
import json
import unittest

import db
import test_evolution_api
import vision_plans


class VisionDetailRuleTests(unittest.TestCase):
    def setUp(self):
        self.f = test_evolution_api.EvolutionApiTests('test_marriage_preset_owned_atomic_and_retry_safe')
        self.f.setUp(); self.addCleanup(self.f.doCleanups)
        self.f.set_clock(week=1, day='Sun', hour=22)                     # Reality Check open: changes allowed
        row = db.fetch_one(self.f.conn, 'User', id='owner')
        stats = json.loads(row['stats_json']); stats['vision_schema_version'] = 2
        row['stats_json'] = json.dumps(stats)
        row['vision_json'] = json.dumps([{'key': 'Intimacy', 'stance': ['Emotional']}, {'key': 'Kids', 'stance': None},
                                         {'key': 'Cohabitate', 'stance': None}])
        db.insert_row(self.f.conn, 'User', row); self.f.conn.commit()

    def body(self, **extra):
        return {'request_id': 'r-' + '-'.join(f'{k}{v}' for k, v in extra.items()), **extra}

    def test_detail_options_are_data_driven(self):
        self.assertEqual({k for k, v in vision_plans.DETAIL_OPTIONS.items() if v}, {'Intimacy'})
        self.assertTrue(vision_plans.has_detail('Intimacy'))
        for pillar in ('Kids', 'Cohabitate', 'Travel together', 'Unknown'):
            self.assertFalse(vision_plans.has_detail(pillar), pillar)
        options = self.f.request('/profile/vision').json['data']['pillar_options']
        self.assertEqual(options, vision_plans.DETAIL_OPTIONS)

    def test_no_add_detail_or_change_for_items_without_detail(self):
        for pillar, sub in (('Kids', None), ('Kids', 'Adoption'), ('Cohabitate', 'Pets'), ('Travel together', None)):
            body = self.body(pillar=pillar, **({'sub_selection': sub} if sub else {}))
            r = self.f.post('/profile/vision/details', body)
            self.assertEqual(r.status_code, 400, (pillar, sub, r.json))
            self.assertEqual(r.json['error']['code'], 'validation_error')
        for pillar, change in (('Cohabitate', {'add': ['Pets']}), ('Kids', {'remove': ['Adoption']})):
            r = self.f.post('/profile/vision/changes', self.body(pillar=pillar, disclosed_to_partner=True, **change))
            self.assertEqual(r.status_code, 400, (pillar, r.json))
        vision = json.loads(db.fetch_one(self.f.conn, 'User', id='owner')['vision_json'])
        self.assertEqual({g['key']: g['stance'] for g in vision}, {'Intimacy': ['Emotional'], 'Kids': None, 'Cohabitate': None})

    def test_intimacy_keeps_add_detail_and_declare_change(self):
        added = self.f.post('/profile/vision/details', self.body(pillar='Intimacy', sub_selection='Physical'))
        self.assertEqual(added.status_code, 200, added.json)
        changed = self.f.post('/profile/vision/changes', self.body(pillar='Intimacy', remove=['Physical'], disclosed_to_partner=True))
        self.assertEqual(changed.status_code, 200, changed.json)


if __name__ == '__main__':
    unittest.main()
