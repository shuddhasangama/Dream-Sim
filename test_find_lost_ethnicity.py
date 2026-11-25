"""tools/find_lost_ethnicity.py on local SQLite copies only."""
import json
import tempfile
import unittest
from pathlib import Path

import db
from tools import find_lost_ethnicity as tool

from datetime import datetime, timezone
SINCE = int(datetime(2026, 11, 17, tzinfo=timezone.utc).timestamp())   # the bug's start
SECRET = 'South Asian'      # an ethnicity value: must never be printed


def make_db(path, users, activity):
    conn = db.get_connection(path)
    db.init_db(conn)
    for uid, ethnicity in users.items():
        stats = {'city': 'Bangalore'} | ({'ethnicity': ethnicity} if ethnicity is not None else {})
        db.insert_row(conn, 'User', {'id': uid, 'journey_state': 'dating', 'stats_json': json.dumps(stats)})
    for uid, seen in activity.items():
        conn.execute('INSERT INTO "UserActivity" (user_id, first_seen_at, last_seen_at, platform, auth_kind) VALUES (?, ?, ?, ?, ?)',
                     (uid, seen, seen, 'app', 'mobile'))
    conn.commit(); conn.close()


class FindLostEthnicityTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.backup, self.target = str(Path(tmp.name) / 'backup.db'), str(Path(tmp.name) / 'target.db')
        before = {'u_lost': [SECRET], 'u_kept': ['Indian'], 'u_changed': ['Indian'], 'u_never': None,
                  'u_lost_inactive': ['Indian'], 'u_lost_then_reentered': ['Indian']}
        after = {'u_lost': [], 'u_kept': ['Indian'], 'u_changed': ['Other'], 'u_never': None,
                 'u_lost_inactive': [], 'u_lost_then_reentered': [], 'u_new': []}
        recent, old = SINCE + 3600, SINCE - 86400
        make_db(self.backup, before, {})
        make_db(self.target, after, {'u_lost': recent, 'u_kept': recent, 'u_changed': recent, 'u_never': recent,
                                     'u_lost_inactive': old, 'u_lost_then_reentered': recent, 'u_new': recent})
        self.lines = []

    def run_tool(self, *extra):
        self.lines = []
        code = tool.main(['--backup', self.backup, '--target', self.target, *extra], out=self.lines.append)
        return code, '\n'.join(self.lines)

    def ethnicity_now(self, uid):
        conn = db.get_connection(self.target)
        try:
            return json.loads(db.fetch_one(conn, 'User', id=uid)['stats_json']).get('ethnicity')
        finally:
            conn.close()

    def test_dry_run_finds_only_recently_active_lost_members_and_prints_ids_only(self):
        before = Path(self.target).read_bytes()
        code, text = self.run_tool()
        self.assertEqual(code, 0)
        self.assertIn('Mode: dry run', text)
        self.assertIn('Members with ethnicity in the backup but empty now: 2', text)
        self.assertIn('  u_lost', text); self.assertIn('  u_lost_then_reentered', text)
        for not_lost in ('u_kept', 'u_changed', 'u_never', 'u_new', 'u_lost_inactive'):
            self.assertNotIn('  ' + not_lost + '\n', text + '\n', not_lost)
        for personal in (SECRET, 'Indian', 'Other', 'Bangalore'):
            self.assertNotIn(personal, text)                             # never a value, only ids and counts
        self.assertEqual(Path(self.target).read_bytes(), before)          # dry run writes nothing

    def test_all_members_includes_inactive(self):
        _, text = self.run_tool('--all-members')
        self.assertIn('empty now: 3', text)
        self.assertIn('  u_lost_inactive', text)

    def test_apply_restores_only_where_still_empty(self):
        conn = db.get_connection(self.target)
        row = db.fetch_one(conn, 'User', id='u_lost_then_reentered')          # member re-enters after the dry run
        stats = json.loads(row['stats_json']); stats['ethnicity'] = ['Other']
        row['stats_json'] = json.dumps(stats); db.insert_row(conn, 'User', row); conn.commit(); conn.close()
        code, text = self.run_tool('--apply')
        self.assertEqual(code, 0)
        self.assertIn('Restored: 1   Skipped (no longer empty): 0', text)    # the re-entered one is no longer a candidate
        self.assertEqual(self.ethnicity_now('u_lost'), [SECRET])
        self.assertEqual(self.ethnicity_now('u_lost_then_reentered'), ['Other'])   # never overwritten
        self.assertEqual(self.ethnicity_now('u_changed'), ['Other'])
        self.assertEqual(self.ethnicity_now('u_lost_inactive'), [])
        self.assertNotIn(SECRET, text)
        _, again = self.run_tool('--apply')                                    # idempotent
        self.assertIn('empty now: 0', again)

    def test_restore_is_compare_and_set(self):
        backup, target = tool.Database(self.backup), tool.Database(self.target)
        try:
            lost, before = tool.find(backup, target, SINCE)
            self.assertIn('u_lost', lost)
            target.conn.execute('UPDATE "User" SET stats_json = ? WHERE id = ?', (json.dumps({'ethnicity': ['Other']}), 'u_lost'))
            target.conn.commit()                                              # changed between find and write
            self.assertFalse(tool.restore(target, 'u_lost', before['u_lost']))
        finally:
            backup.close(); target.close()
        self.assertEqual(self.ethnicity_now('u_lost'), ['Other'])

    def test_refuses_non_local_hosts_without_the_explicit_flag(self):
        for remote in ('postgresql://user:pw@containers-us-west-1.railway.app:6543/railway',
                       'postgresql://user:pw@db.example.com/prod', 'postgres://u:p@10.0.0.5/dhashu'):
            lines = []
            code = tool.main(['--backup', self.backup, '--target', remote], out=lines.append)
            self.assertEqual(code, 2, remote)
            self.assertIn('Refusing', lines[0])
            self.assertNotIn('pw', lines[0])                                    # never echoes credentials
            lines = []
            self.assertEqual(tool.main(['--backup', remote, '--target', self.target], out=lines.append), 2)
        for local in ('postgresql://u:p@localhost:5433/dhashu_local', 'postgresql://u:p@127.0.0.1/x', self.target):
            self.assertTrue(tool.is_local(local), local)

    def test_never_called_by_the_app(self):
        import subprocess
        hits = subprocess.run(['git', 'grep', '-l', 'find_lost_ethnicity', '--', '*.py', '*.js'],
                              capture_output=True, text=True).stdout.split()
        self.assertEqual(sorted(hits), ['test_find_lost_ethnicity.py', 'tools/find_lost_ethnicity.py'])


if __name__ == '__main__':
    unittest.main()
