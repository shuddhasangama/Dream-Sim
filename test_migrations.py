"""mon-alembic: the baseline migration builds exactly the schema init_db builds,
is idempotent, can be stamped onto an existing database, and its dry run
changes nothing. PostgreSQL tests use an isolated throwaway schema."""
import contextlib
import io
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock
from urllib.parse import quote

import db

REPO = Path(__file__).resolve().parent


def _dsn():
    path = os.environ.get('AUTH_TEST_POSTGRES_DSN_FILE')
    return Path(path).read_text(encoding='ascii').strip() if path else None


@unittest.skipUnless(os.environ.get('AUTH_TEST_POSTGRES_DSN_FILE'), 'No isolated PostgreSQL test instance configured')
class BaselineMigrationTests(unittest.TestCase):
    def setUp(self):
        import psycopg
        from psycopg.rows import dict_row
        self.base = _dsn()
        self.control = psycopg.connect(self.base, autocommit=True, row_factory=dict_row)
        self.addCleanup(self.control.close)
        self.schemas = []

    def tearDown(self):
        for schema in self.schemas:
            self.control.execute(f'DROP SCHEMA IF EXISTS "{schema}" CASCADE')

    def schema(self):
        name = 'mig_test_' + uuid.uuid4().hex[:12]
        self.control.execute(f'CREATE SCHEMA "{name}"')
        self.schemas.append(name)
        return name

    def url(self, schema):
        joiner = '&' if '?' in self.base else '?'
        return self.base + joiner + 'options=' + quote('-csearch_path=' + schema)

    def alembic(self, schema, *args, sql=False):
        from alembic import command
        from alembic.config import Config
        cfg = Config(str(REPO / 'alembic.ini'))
        out = io.StringIO()
        cfg.stdout = out
        with mock.patch.dict(os.environ, {'DATABASE_URL': self.url(schema)}), contextlib.redirect_stdout(out):
            getattr(command, args[0])(cfg, *args[1:], **({'sql': True} if sql else {}))
        return out.getvalue()

    def shape(self, schema):
        columns = self.control.execute(
            'SELECT table_name, column_name, data_type, is_nullable, column_default FROM information_schema.columns '
            "WHERE table_schema=%s AND table_name <> 'alembic_version'", (schema,)).fetchall()
        indexes = self.control.execute(
            "SELECT tablename, indexname FROM pg_indexes WHERE schemaname=%s AND tablename <> 'alembic_version'", (schema,)).fetchall()
        return ({tuple(r.values()) for r in columns}, {tuple(r.values()) for r in indexes})

    def init_db_schema(self):
        import psycopg
        from psycopg.rows import dict_row
        from admin_dashboard.manage import initialize
        schema = self.schema()
        with psycopg.connect(self.url(schema), row_factory=dict_row) as conn:
            db.init_db(conn)
            initialize(conn)
        return schema

    def test_baseline_builds_exactly_the_init_db_schema(self):
        migrated = self.schema()
        self.alembic(migrated, 'upgrade', 'head')
        expected = self.shape(self.init_db_schema())
        actual = self.shape(migrated)
        self.assertGreater(len(actual[0]), 400)  # the real schema, not an empty one
        self.assertEqual(actual[0] ^ expected[0], set())
        self.assertEqual(actual[1] ^ expected[1], set())
        version = self.control.execute(f'SELECT version_num FROM "{migrated}".alembic_version').fetchall()
        self.assertEqual([r['version_num'] for r in version], ['0009_account_reviewer'])

    def test_upgrade_is_idempotent_and_stamp_adopts_an_existing_database(self):
        existing = self.init_db_schema()
        before = self.shape(existing)
        self.alembic(existing, 'stamp', '0001_baseline')         # production adoption step
        self.assertEqual(self.shape(existing), before)            # stamping runs no DDL
        self.alembic(existing, 'upgrade', 'head')                 # already at head: no-op
        self.assertEqual(self.shape(existing), before)
        fresh = self.schema()
        self.alembic(fresh, 'upgrade', 'head')
        self.control.execute(f'DELETE FROM "{fresh}".alembic_version')
        self.alembic(fresh, 'upgrade', 'head')                    # re-running the baseline is harmless
        self.assertEqual(self.shape(fresh), self.shape(existing))

    def test_dry_run_prints_sql_and_changes_nothing(self):
        target = self.schema()
        sql = self.alembic(target, 'upgrade', 'head', sql=True)
        self.assertIn('CREATE TABLE IF NOT EXISTS "User"', sql)
        self.assertIn("INSERT INTO alembic_version", sql)
        tables = self.control.execute(
            'SELECT count(*) AS n FROM information_schema.tables WHERE table_schema=%s', (target,)).fetchone()['n']
        self.assertEqual(tables, 0)


class AlembicConfigTests(unittest.TestCase):
    def test_env_refuses_a_non_postgres_database_url(self):
        from alembic import command
        from alembic.config import Config
        for value in ('', 'sqlite:///x.db'):
            with self.subTest(value=value), mock.patch.dict(os.environ, {'DATABASE_URL': value}):
                with self.assertRaisesRegex(RuntimeError, 'PostgreSQL DATABASE_URL'):
                    command.upgrade(Config(str(REPO / 'alembic.ini')), 'head', sql=True)

    def test_baseline_snapshot_matches_the_schema_files_it_was_generated_from(self):
        versions = REPO / 'migrations' / 'versions'
        self.assertTrue((versions / '0001_baseline_app.sql').read_text(encoding='utf-8').startswith(
            (REPO / 'schema_postgres.sql').read_text(encoding='utf-8')[:200]))
        self.assertIn('AdminIdentity', (versions / '0001_baseline_admin.sql').read_text(encoding='utf-8-sig'))


class ReconcileSettingTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.conn = db.get_connection(Path(tmp.name) / 'r.db')
        self.addCleanup(self.conn.close)

    def test_reconcile_runs_by_default_and_can_be_switched_off(self):
        with mock.patch.object(db, 'reconcile_columns', wraps=db.reconcile_columns) as reconcile:
            with mock.patch.dict(os.environ, {'DHASHU_SCHEMA_RECONCILE': '1'}):
                db.init_db(self.conn)
            self.assertEqual(reconcile.call_count, 1)
            with mock.patch.dict(os.environ, {'DHASHU_SCHEMA_RECONCILE': '0'}):
                db.init_db(self.conn)
            self.assertEqual(reconcile.call_count, 1)
        os.environ.pop('DHASHU_SCHEMA_RECONCILE', None)
        self.assertTrue(db.schema_reconcile_enabled())


if __name__ == '__main__':
    unittest.main()
