import os
import unittest
import uuid
from pathlib import Path
import psycopg
from psycopg.rows import dict_row
from psycopg import sql
import db
from tools.purge_other_users import purge

@unittest.skipUnless(os.getenv('AUTH_TEST_POSTGRES_DSN_FILE'),'Disposable PostgreSQL required')
class PurgeTests(unittest.TestCase):
    def setUp(self):
        dsn=Path(os.environ['AUTH_TEST_POSTGRES_DSN_FILE']).read_text()
        self.admin=psycopg.connect(dsn,autocommit=True)
        self.name='purge_test_'+uuid.uuid4().hex
        self.admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(self.name)))
        self.conn=psycopg.connect(dsn,dbname=self.name,row_factory=dict_row)
        self.addCleanup(self.cleanup)
        db.init_db(self.conn)
        self.protected={'+919000000001':'keep1','+919000000002':'keep2','+919000000003':'keep3'}
        for uid in [*self.protected.values(),*[f'delete{i}' for i in range(240)]]:
            self.conn.execute('INSERT INTO "User"(id,journey_state) VALUES (%s,%s)',(uid,'onboarding'))
        for number,uid in self.protected.items():
            self.conn.execute('INSERT INTO "Account"(id,user_id,phone,created_at) VALUES (%s,%s,%s,%s)',('a'+uid,uid,number,0))
        self.conn.execute('INSERT INTO "Account"(id,user_id,phone,created_at) VALUES (%s,%s,%s,%s)',('oldaccount','delete0','+919000000099',0))
        self.conn.execute('INSERT INTO "FaceImageLease"(id,user_id,protected_images,expires_at) VALUES (%s,%s,%s,%s)',('lease','delete0','encrypted','later'))
        self.conn.commit()
    def test_full_reset_removes_all_profiles_and_unlinked_otp_state(self):
        self.conn.execute('INSERT INTO "AuthChallenge"(id,channel,destination,kind,expires_at) VALUES (%s,%s,%s,%s,%s)',('orphan','phone','+919000000099','mobile',9999999999))
        self.conn.execute('INSERT INTO "AuthThrottle" VALUES (%s,%s,%s)',('throttle',1,9999999999))
        self.conn.commit()
        purge(self.conn,protected={},expected=243,apply=True)
        for table in ('User','Account','AuthChallenge','AuthThrottle','FaceImageLease'):
            self.assertEqual(self.conn.execute(sql.SQL('SELECT count(*) n FROM {}').format(sql.Identifier(table))).fetchone()['n'],0)

    def cleanup(self):
        self.conn.close()
        self.admin.execute(sql.SQL('DROP DATABASE {}').format(sql.Identifier(self.name)))
        self.admin.close()
    def test_dry_run_then_apply_preserves_three_and_removes_unconstrained_child(self):
        purge(self.conn,protected=self.protected)
        self.assertEqual(self.conn.execute('SELECT count(*) n FROM "User"').fetchone()['n'],243)
        self.conn.rollback()
        purge(self.conn,protected=self.protected,apply=True)
        self.assertEqual(self.conn.execute('SELECT count(*) n FROM "User"').fetchone()['n'],3)
        self.assertEqual(self.conn.execute('SELECT count(*) n FROM "FaceImageLease"').fetchone()['n'],0)
        self.assertEqual(self.conn.execute('SELECT count(*) n FROM "Account"').fetchone()['n'],3)
    def test_mixed_matches_removed_but_protected_pair_match_preserved(self):
        for rid,left,right,slot in [('out','keep1','delete0',1),('in','delete0','keep1',1),('keep','keep1','keep2',2)]:
            self.conn.execute('INSERT INTO "Match"(id,user_id,candidate_id,week,slot,revealed_at,window_closes_at) VALUES (%s,%s,%s,1,%s,%s,%s)',(rid,left,right,slot,'today','tomorrow'))
        self.conn.commit()
        purge(self.conn,protected=self.protected,apply=True)
        self.assertEqual([r['id'] for r in self.conn.execute('SELECT id FROM "Match"')],['keep'])
        self.assertEqual(self.conn.execute('SELECT count(*) n FROM "User"').fetchone()['n'],3)

    def test_shared_record_aborts(self):
        self.conn.execute('INSERT INTO "LockIn"(id,user_a,user_b,week,created_at,status) VALUES (%s,%s,%s,%s,%s,%s)',('mixed','keep1','delete0',1,'today','active'));self.conn.commit()
        with self.assertRaisesRegex(ValueError,'Shared protected'):purge(self.conn,protected=self.protected,apply=True)
        self.assertEqual(self.conn.execute('SELECT count(*) n FROM "User"').fetchone()['n'],243)
    def test_identity_and_count_guards(self):
        with self.assertRaisesRegex(ValueError,'mapping changed'):purge(self.conn,protected={'+919000000001':'wrong'},apply=True)
        with self.assertRaisesRegex(ValueError,'count changed'):purge(self.conn,protected=self.protected,expected=239,apply=True)
    def test_nullable_cycle_and_mandatory_cycle_rollback(self):
        self.conn.execute('CREATE TABLE "TestCycle"(id text PRIMARY KEY,user_id text REFERENCES "User"(id),peer text REFERENCES "TestCycle"(id))')
        self.conn.execute('INSERT INTO "TestCycle" VALUES (%s,%s,NULL)',('c','delete0'))
        self.conn.execute('UPDATE "TestCycle" SET peer=id');self.conn.commit()
        purge(self.conn,protected=self.protected,apply=True)
        self.assertEqual(self.conn.execute('SELECT count(*) n FROM "TestCycle"').fetchone()['n'],0)
    def test_mandatory_cycle_rolls_back(self):
        self.conn.execute('CREATE TABLE "TestCycle"(id text PRIMARY KEY,user_id text REFERENCES "User"(id),peer text NOT NULL REFERENCES "TestCycle"(id))')
        self.conn.execute('INSERT INTO "TestCycle" VALUES (%s,%s,%s)',('c','delete0','c'));self.conn.commit()
        with self.assertRaisesRegex(ValueError,'dependency cycle'):purge(self.conn,protected=self.protected,apply=True)
        self.assertEqual(self.conn.execute('SELECT count(*) n FROM "User"').fetchone()['n'],243)
