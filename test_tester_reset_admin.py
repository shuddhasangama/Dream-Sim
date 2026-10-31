import contextlib
import io
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
import tester_reset_admin as resetter


class ResetTests(unittest.TestCase):
    def setUp(self):
        self.c=sqlite3.connect(':memory:'); self.c.row_factory=sqlite3.Row
        self.c.executescript(Path('schema.sql').read_text(encoding='utf-8'))
        self.ids=['test_blr_20260921_f06','test_blr_20260921_m06']
        for uid in self.ids+['other']:
            self.c.execute('INSERT INTO "User" (id,journey_state,bgv_status) VALUES (?, ?, ?)',(uid,'dating','verified'))
            self.c.execute('INSERT INTO "Account" (id,user_id,phone,auth_enabled,created_at) VALUES (?,?,?,1,?)',(uid,uid,'+91900000000'+str(len(uid)), 'now'))
        self.c.commit()
        self.env=patch.dict(os.environ,{'DHASHU_SIMULATED_CLOCK':'true','DHASHU_ASYNC_TEST':'true',
            'DHASHU_TESTER_NO_OTP':'true','DHASHU_TESTER_USER_IDS':','.join(self.ids),
            'DHASHU_FIXED_TEST_PAIRS':'06','DHASHU_TEST_START_WEEK':'39'})
        self.env.start()

    def tearDown(self):self.env.stop();self.c.close()

    def test_apply_and_dryrun_preserve_profiles_and_others(self):
        with contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(resetter.DryRun):resetter.reset(self.c,6)
            self.assertEqual(self.c.execute('SELECT count(*) FROM "Match"').fetchone()[0],0)
            with tempfile.TemporaryDirectory() as tmp:
                resetter.reset(self.c,6,apply=True,backup_dir=tmp)
                self.assertEqual(len(list(Path(tmp).glob('*.json'))),1)
        self.assertEqual(self.c.execute('SELECT count(*) FROM "Match"').fetchone()[0],2)
        self.assertEqual(self.c.execute('SELECT count(*) FROM "Account"').fetchone()[0],3)
        self.assertEqual(self.c.execute('SELECT journey_state FROM "User" WHERE id="other"').fetchone()[0],'dating')

    def test_refuse_other_partner_and_rollback(self):
        self.c.execute('INSERT INTO "LockIn" (id,user_a,user_b,week,status,created_at) VALUES (?,?,?,39,?,?)',('foreign',self.ids[0],'other','active','Mon:12'))
        self.c.commit()
        with self.assertRaisesRegex(ValueError,'another profile'):resetter.reset(self.c,6)
        self.assertEqual(self.c.execute('SELECT count(*) FROM "LockIn"').fetchone()[0],1)

    def test_pair_history_cleared(self):
        self.c.execute('INSERT INTO "LockIn" (id,user_a,user_b,week,status,created_at) VALUES (?,?,?,39,?,?)',('old',*self.ids,'active','Mon:12'))
        self.c.commit()
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            resetter.reset(self.c,6,apply=True,backup_dir=tmp)
        self.assertEqual(self.c.execute('SELECT count(*) FROM "LockIn"').fetchone()[0],0)

    def test_failure_after_deletion_rolls_back(self):
        self.c.execute('INSERT INTO "LockIn" (id,user_a,user_b,week,status,created_at) VALUES (?,?,?,39,?,?)',('old',*self.ids,'active','Mon:12'))
        self.c.commit()
        with patch.object(resetter.fixed_test_pairs,'assign',side_effect=ValueError('forced failure')),contextlib.redirect_stdout(io.StringIO()):
            with self.assertRaises(ValueError):resetter.reset(self.c,6)
        self.assertEqual(self.c.execute('SELECT count(*) FROM "LockIn"').fetchone()[0],1)

    def test_relationship_rows_cleared(self):
        self.c.execute('INSERT INTO "Couple" (id,partner_a_id,partner_b_id,stage,start_date,entered_via) VALUES (?,?,?,?,?,?)',('couple',*self.ids,'relationship','2026-01-01','progression'))
        self.c.execute('UPDATE "User" SET journey_state="relationship" WHERE id IN (?,?)',self.ids)
        self.c.commit()
        with tempfile.TemporaryDirectory() as tmp,contextlib.redirect_stdout(io.StringIO()):
            resetter.reset(self.c,6,apply=True,backup_dir=tmp)
        self.assertEqual(self.c.execute('SELECT count(*) FROM "Couple"').fetchone()[0],0)
        self.assertEqual(self.c.execute('SELECT journey_state FROM "User" WHERE id=?',(self.ids[0],)).fetchone()[0],'dating')
