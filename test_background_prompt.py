"""Ethnicity-restore fallback: one-time 'Please confirm your background details'
prompt behind DHASHU_ETHNICITY_PROMPT (default off)."""
import json
import os
import unittest
from unittest import mock

import background_prompt
import db
import test_evolution_api

ON = {'DHASHU_ETHNICITY_PROMPT': '1'}


class ShouldShowTests(unittest.TestCase):
    def test_rules(self):
        empty = {'journey_state': 'dating', 'stats': {'ethnicity': []}}
        self.assertFalse(background_prompt.should_show(empty))                            # default off
        with mock.patch.dict(os.environ, ON):
            self.assertTrue(background_prompt.should_show(empty))
            self.assertTrue(background_prompt.should_show({'journey_state': 'dating', 'stats': {}}))
            self.assertFalse(background_prompt.should_show({'journey_state': 'dating', 'stats': {'ethnicity': ['Indian']}}))
            self.assertFalse(background_prompt.should_show({'journey_state': 'onboarding', 'stats': {}}))
            self.assertFalse(background_prompt.should_show({'journey_state': 'dating', 'stats': {background_prompt.DONE: True}}))
            self.assertFalse(background_prompt.should_show(None))


class PromptApiTests(unittest.TestCase):
    def setUp(self):
        self.f = test_evolution_api.EvolutionApiTests('test_marriage_preset_owned_atomic_and_retry_safe')
        self.f.setUp(); self.addCleanup(self.f.doCleanups)

    def status(self, uid='owner'):
        return self.f.request('/journey/status', uid=uid).json['data']

    def stats(self, uid='owner'):
        return json.loads(db.fetch_one(self.f.conn, 'User', id=uid)['stats_json'])

    def test_off_by_default_the_field_is_absent(self):
        self.assertNotIn('background_prompt', self.status())

    def test_shown_once_then_gone_after_not_now_or_after_saving_ethnicity(self):
        with mock.patch.dict(os.environ, ON):
            self.assertTrue(self.status()['background_prompt'])
            r = self.f.post('/profile/background-prompt/dismiss', {})
            self.assertEqual((r.status_code, r.json['data']), (200, {'background_prompt': False}))
            self.assertFalse(self.status()['background_prompt'])
            self.assertTrue(self.stats()[background_prompt.DONE])
            self.assertEqual(self.f.post('/profile/background-prompt/dismiss', {}).status_code, 200)   # idempotent
            # another member: saving an ethnicity ends it without dismissing
            self.assertTrue(self.status('partner')['background_prompt'])
            row = db.fetch_one(self.f.conn, 'User', id='partner')
            stats = json.loads(row['stats_json']); stats['ethnicity'] = ['Indian']
            row['stats_json'] = json.dumps(stats); db.insert_row(self.f.conn, 'User', row); self.f.conn.commit()
            self.assertFalse(self.status('partner')['background_prompt'])
            self.assertNotIn(background_prompt.DONE, self.stats('partner'))

    def test_dismiss_is_owner_only_and_needs_sign_in(self):
        with mock.patch.dict(os.environ, ON):
            self.f.post('/profile/background-prompt/dismiss', {}, uid='owner')
            self.assertTrue(self.status('partner')['background_prompt'])                # the partner is unaffected
            r = self.f.client.post('/api/v1/profile/background-prompt/dismiss', json={})
            self.assertIn(r.status_code, (401, 403))   # refused before anything else (security suite rule)
            self.assertEqual(self.f.post('/profile/background-prompt/dismiss', {'x': 1}).status_code, 400)


if __name__ == '__main__':
    unittest.main()
