"""Tests for db.reconcile_columns() — keeping a live database level with
the schema file (2026-09-04).

WHY THIS EXISTS
===============
CREATE TABLE IF NOT EXISTS creates a table that is missing and does
NOTHING to one that already exists. So a column added to the schema file
ships in the code, deploys cleanly, and then every write to that table
fails with 'column "x" does not exist'.

The obvious fix — run an ALTER by hand on the deployed database — is
exactly how the live database and the repo stop being the same thing.
Six months later nobody can say which of the two is right, and the
difference is invisible until something breaks.

So reconciliation happens in init_db(), on both backends, from the schema
file. One source of truth, one code path, no manual step.

These run on SQLite like the rest of the suite; the PostgreSQL path shares
every line except the introspection query.
"""

from __future__ import annotations

import pathlib
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path

import db

SCHEMA = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")


def _schema_without(fragment: str) -> str:
    assert fragment in SCHEMA, "fixture is out of date with schema.sql"
    return SCHEMA.replace(fragment, "")


ACKS_COLUMN = """    -- Which terms were explicitly ticked, as a JSON list of ack keys. A
    -- signature that does not record WHAT was agreed to is a signature on
    -- nothing; ceremony.ACKS holds the wording for each key.
    acks_json     TEXT NOT NULL DEFAULT '[]',
"""


class TempDatabaseCase(unittest.TestCase):
    """A throwaway SQLite file per test, closed before it is deleted.

    The closing is not tidiness. On Windows an open file cannot be
    unlinked, so a connection left open turns every test in this file into
    a PermissionError at teardown — on Linux the same code passes, which
    is the worst kind of platform bug to leave in a suite somebody else
    runs. Cleanups fire last-registered-first, so the directory is
    registered first and torn down last.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "test.db"

    def connect(self, path=None) -> sqlite3.Connection:
        conn = db.get_connection(path or self.path)
        self.addCleanup(conn.close)
        return conn


class ReconcileTests(TempDatabaseCase):
    def _stale(self, schema: str) -> sqlite3.Connection:
        """A database built from an OLDER schema — what a deployed
        database looks like the moment the schema file moves on."""
        conn = self.connect()
        conn.executescript(schema)
        conn.commit()
        return conn

    def columns(self, conn, table="Ceremony") -> set[str]:
        return {row[1] for row in conn.execute(f'PRAGMA table_info("{table}")')}

    def test_a_stale_database_is_missing_the_column(self):
        """The fixture has to actually reproduce the problem, or every
        test below passes for the wrong reason."""
        conn = self._stale(_schema_without(ACKS_COLUMN))
        self.assertNotIn("acks_json", self.columns(conn))

    def test_init_db_adds_it_without_anyone_running_an_alter(self):
        conn = self._stale(_schema_without(ACKS_COLUMN))
        db.init_db(conn)
        self.assertIn("acks_json", self.columns(conn))

    def test_the_added_column_keeps_its_declared_default(self):
        """A column added with the wrong default is worse than a missing
        one — it is wrong quietly."""
        conn = self._stale(_schema_without(ACKS_COLUMN))
        db.init_db(conn)
        conn.execute('INSERT INTO "User" (id, journey_state, bgv_status) VALUES (?,?,?)',
                     ("u1", "dating", "verified"))
        conn.execute(
            'INSERT INTO "Ceremony" (id, user_id, kind, scope_id, created_at) VALUES (?,?,?,?,?)',
            ("c1", "u1", "date_agreement", "p1", "Mon:12"))
        conn.commit()
        value = conn.execute('SELECT acks_json FROM "Ceremony" WHERE id = ?', ("c1",)).fetchone()[0]
        self.assertEqual(value, "[]")

    def test_it_reports_what_it_changed(self):
        conn = self._stale(_schema_without(ACKS_COLUMN))
        result = db.reconcile_columns(conn)
        self.assertIn("Ceremony.acks_json", result["added"])

    def test_a_current_database_is_left_alone(self):
        """Running it on every startup means it runs constantly. Doing
        nothing has to be the common case, and has to be silent."""
        conn = self.connect()
        db.init_db(conn)
        self.assertEqual(db.reconcile_columns(conn), {"added": [], "needs_migration": []})

    def test_running_it_twice_changes_nothing_the_second_time(self):
        conn = self._stale(_schema_without(ACKS_COLUMN))
        first = db.reconcile_columns(conn)
        second = db.reconcile_columns(conn)
        self.assertTrue(first["added"])
        self.assertEqual(second["added"], [])

    def test_existing_rows_survive_the_reconciliation(self):
        """This runs against a database with real data in it. A migration
        that empties a table is not a migration."""
        conn = self._stale(_schema_without(ACKS_COLUMN))
        conn.execute('INSERT INTO "User" (id, journey_state, bgv_status) VALUES (?,?,?)',
                     ("u1", "dating", "verified"))
        conn.execute(
            'INSERT INTO "Ceremony" (id, user_id, kind, scope_id, created_at) VALUES (?,?,?,?,?)',
            ("c1", "u1", "date_agreement", "p1", "Mon:12"))
        conn.commit()
        db.init_db(conn)
        row = conn.execute('SELECT id, acks_json FROM "Ceremony" WHERE id = ?', ("c1",)).fetchone()
        self.assertEqual(row[0], "c1")
        self.assertEqual(row[1], "[]")

    def test_a_missing_table_is_left_to_create_table(self):
        """Reconciliation adds columns to tables that exist. Creating the
        table is CREATE TABLE's job, and doing it in two places is how
        they end up disagreeing."""
        conn = self._stale(_schema_without(ACKS_COLUMN))
        conn.execute('DROP TABLE "Ceremony"')
        conn.commit()
        self.assertEqual(db.reconcile_columns(conn)["added"], [])
        db.init_db(conn)
        self.assertIn("acks_json", self.columns(conn))


class HonestLimitTests(TempDatabaseCase):
    """What it refuses to do, and says so.

    Additive only. Adding a column is safe and reversible; dropping,
    renaming or retyping one is not, and a deploy step that silently
    guesses at those is worse than one that stops."""

    def test_a_not_null_column_with_no_default_is_reported_not_attempted(self):
        """There is no value to put in the existing rows. Inventing one is
        a data decision dressed up as a deploy step."""
        conn = self.connect()
        conn.executescript('CREATE TABLE IF NOT EXISTS "Thing" (\n    id TEXT PRIMARY KEY\n);')
        conn.commit()
        schema = Path(self._tmp.name) / "s.sql"
        schema.write_text('CREATE TABLE IF NOT EXISTS "Thing" (\n'
                          '    id TEXT PRIMARY KEY,\n'
                          '    owner TEXT NOT NULL\n'
                          ');', encoding="utf-8")
        result = db.reconcile_columns(conn, schema)
        self.assertEqual(result["added"], [])
        self.assertEqual(result["needs_migration"], ["Thing.owner"])

    def test_a_not_null_column_WITH_a_default_is_added(self):
        conn = self.connect()
        conn.executescript('CREATE TABLE IF NOT EXISTS "Thing" (\n    id TEXT PRIMARY KEY\n);')
        conn.commit()
        schema = Path(self._tmp.name) / "s.sql"
        schema.write_text('CREATE TABLE IF NOT EXISTS "Thing" (\n'
                          '    id TEXT PRIMARY KEY,\n'
                          "    owner TEXT NOT NULL DEFAULT 'nobody'\n"
                          ');', encoding="utf-8")
        self.assertEqual(db.reconcile_columns(conn, schema)["added"], ["Thing.owner"])

    def test_it_never_drops_a_column_the_schema_no_longer_declares(self):
        """Additive means additive. A column removed from the schema file
        stays in the database until a person decides otherwise."""
        conn = self.connect()
        conn.executescript('CREATE TABLE IF NOT EXISTS "Thing" (\n'
                           '    id TEXT PRIMARY KEY,\n'
                           '    legacy TEXT\n'
                           ');')
        conn.commit()
        schema = Path(self._tmp.name) / "s.sql"
        schema.write_text('CREATE TABLE IF NOT EXISTS "Thing" (\n    id TEXT PRIMARY KEY\n);',
                          encoding="utf-8")
        db.reconcile_columns(conn, schema)
        self.assertIn("legacy", {row[1] for row in conn.execute('PRAGMA table_info("Thing")')})

    def test_table_level_constraints_are_not_mistaken_for_columns(self):
        """UNIQUE(...) on its own line is not a column, and trying to ADD
        COLUMN it would fail the whole startup."""
        conn = self.connect()
        conn.executescript('CREATE TABLE IF NOT EXISTS "Thing" (\n    id TEXT PRIMARY KEY\n);')
        conn.commit()
        schema = Path(self._tmp.name) / "s.sql"
        schema.write_text('CREATE TABLE IF NOT EXISTS "Thing" (\n'
                          '    id TEXT PRIMARY KEY,\n'
                          '    a TEXT,\n'
                          '    b TEXT,\n'
                          '    UNIQUE (a, b),\n'
                          '    CHECK (a <> b)\n'
                          ');', encoding="utf-8")
        self.assertEqual(sorted(db.reconcile_columns(conn, schema)["added"]),
                         ["Thing.a", "Thing.b"])


class RealSchemaTests(unittest.TestCase):
    """Parsing the actual schema file, not a fixture."""

    def test_every_table_in_the_schema_is_parsed(self):
        parsed = db._expected_columns(SCHEMA)
        self.assertEqual(set(parsed) & db.TABLES, db.TABLES)

    def test_every_table_has_at_least_an_id(self):
        for table, columns in db._expected_columns(SCHEMA).items():
            with self.subTest(table=table):
                self.assertTrue(columns, f"{table} parsed with no columns")

    def test_the_schema_needs_no_manual_migration_today(self):
        """If this fails, the schema file contains a NOT NULL column with
        no default that reconciliation cannot add — and the deploy needs a
        real migration, written by a person."""
        conn = db.get_connection(":memory:")
        self.addCleanup(conn.close)
        db.init_db(conn)
        self.assertEqual(db.reconcile_columns(conn)["needs_migration"], [])


if __name__ == "__main__":
    unittest.main()


class DriftCheckIsItselfChecked(unittest.TestCase):
    """The drift checker drifted.

    drift-check.sql exists because CREATE TABLE IF NOT EXISTS is a no-op
    on an existing table, so a new column deploys cleanly and then every
    write fails. Its expected-column list was hand-maintained, and
    round_no and answers_closed_at shipped without ever reaching it — a
    checker that reports "clean" on exactly the deploy it was written for.
    It is generated from the schema now; this is what stops it going
    stale again.
    """

    def rows_in_drift_check(self):
        text = pathlib.Path("drift-check.sql").read_text(encoding="utf-8")
        start = text.index("WITH expected(table_name, column_name) AS (VALUES")
        end = text.index("\n)", start)
        return set(re.findall(r"\('([A-Za-z_]+)','([A-Za-z_]+)'\)", text[start:end]))

    def rows_in_schema(self):
        schema = pathlib.Path("schema_postgres.sql").read_text(encoding="utf-8")
        return {(table, name)
                for table, columns in db._expected_columns(schema).items()
                for name, _decl in columns}

    def test_it_lists_exactly_what_the_schema_declares(self):
        self.assertEqual(
            self.rows_in_drift_check(), self.rows_in_schema(),
            "drift-check.sql is out of date — run `python regen-drift-check.py`")

    def test_the_column_added_today_is_in_it(self):
        self.assertIn(("StageGate", "raised_by"), self.rows_in_drift_check())
