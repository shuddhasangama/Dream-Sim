"""Static checks on schema_postgres.sql.

WHY THIS EXISTS
===============
Every other test in this repo runs on SQLite, because that is what
db.get_connection() gives you without DATABASE_URL set. SQLite treats
identifiers case-insensitively, so `CREATE TABLE Account` and
`SELECT * FROM "Account"` both work there and agree with each other.

PostgreSQL does not. It folds UNQUOTED identifiers to lower case, so
`CREATE TABLE Account` creates a table literally named `account`. And
db._table_name() quotes every name for PostgreSQL:

    return f'"{table}"' if _is_postgres_connection(conn) else table

so the app then asks for `FROM "Account"` — exact case — and PostgreSQL
answers `relation "Account" does not exist`.

That mismatch cost a working deployment on 2026-09-03: 29 tables were
declared unquoted while every query quoted them. It was invisible locally
because 596 tests all passed on SQLite, and invisible in production until
a screen touched a table other than "User".

These tests read the SQL as text rather than connecting to anything, so
they run in the normal suite with no PostgreSQL and no network, and they
fail on the exact class of mistake that got through.
"""

from __future__ import annotations

import codecs
import re
import unittest
from pathlib import Path

import db

SCHEMA = Path(__file__).with_name("schema_postgres.sql").read_text(encoding="utf-8")

QUOTED_TABLE = re.compile(r'CREATE TABLE IF NOT EXISTS\s+"([A-Za-z_]+)"')
UNQUOTED_TABLE = re.compile(r'CREATE TABLE IF NOT EXISTS\s+([A-Za-z_]+)\s*\(')
INDEX_ON_UNQUOTED = re.compile(r'CREATE INDEX[^;]*?\bON\s+([A-Za-z_]+)\s*\(')
REFERENCES_UNQUOTED = re.compile(r'REFERENCES\s+([A-Za-z_]+)\s*\(')


def _table_body(name: str) -> str:
    """The text between a table's opening paren and its closing `);`."""
    start = SCHEMA.index(f'CREATE TABLE IF NOT EXISTS "{name}"')
    return SCHEMA[start:SCHEMA.index("\n);", start)]


class QuotingTests(unittest.TestCase):
    """The bug that broke the deployment, in three assertions."""

    def test_every_table_the_code_queries_is_declared_quoted(self):
        declared = set(QUOTED_TABLE.findall(SCHEMA))
        missing = sorted(t for t in db.TABLES if t not in declared)
        self.assertEqual(
            missing, [],
            "db.py queries these with quoted CamelCase, but schema_postgres.sql "
            "does not declare them that way, so PostgreSQL will report "
            f'relation "X" does not exist: {missing}',
        )

    def test_no_table_is_declared_unquoted(self):
        unquoted = sorted(set(UNQUOTED_TABLE.findall(SCHEMA)))
        self.assertEqual(
            unquoted, [],
            "PostgreSQL folds unquoted identifiers to lower case, so these "
            f"would be created with the wrong name: {unquoted}",
        )

    def test_indexes_and_foreign_keys_target_quoted_tables(self):
        self.assertEqual(sorted(set(INDEX_ON_UNQUOTED.findall(SCHEMA))), [],
                         "a CREATE INDEX names its table unquoted")
        self.assertEqual(sorted(set(REFERENCES_UNQUOTED.findall(SCHEMA))), [],
                         "a REFERENCES clause names its table unquoted")


class EncodingTests(unittest.TestCase):
    """A byte-order mark is invisible in an editor and fatal to psql.

    Windows editors add one silently on save. PostgreSQL reads the three
    BOM bytes as part of the first statement and fails on it, which
    presents as a syntax error pointing at a line that looks correct —
    the hardest kind of schema break to diagnose, and one that only shows
    up on the deployed database. Both files are checked, because either
    can be opened and re-saved on its own.
    """

    FILES = ("schema.sql", "schema_postgres.sql")

    def test_no_schema_file_starts_with_a_byte_order_mark(self):
        for name in self.FILES:
            with self.subTest(file=name):
                raw = Path(__file__).with_name(name).read_bytes()
                self.assertFalse(
                    raw.startswith(codecs.BOM_UTF8),
                    f"{name} begins with a UTF-8 BOM. PostgreSQL reads those "
                    "three bytes as part of the first statement. Re-save it as "
                    "UTF-8 without BOM.",
                )
                for bom, label in ((codecs.BOM_UTF16_LE, "UTF-16 LE"),
                                   (codecs.BOM_UTF16_BE, "UTF-16 BE")):
                    self.assertFalse(raw.startswith(bom), f"{name} is {label}, not UTF-8")

    def test_every_schema_file_is_valid_utf8(self):
        for name in self.FILES:
            with self.subTest(file=name):
                raw = Path(__file__).with_name(name).read_bytes()
                try:
                    raw.decode("utf-8")
                except UnicodeDecodeError as exc:
                    self.fail(f"{name} is not valid UTF-8: {exc}")

    def test_no_stray_nulls_or_carriage_returns_inside_statements(self):
        """A lone CR (old-Mac line ending) or a NUL byte survives a copy-paste
        and breaks the file in ways the SQL itself does not explain."""
        for name in self.FILES:
            with self.subTest(file=name):
                raw = Path(__file__).with_name(name).read_bytes()
                self.assertNotIn(b"\x00", raw, f"{name} contains a NUL byte")
                self.assertNotIn(b"\r\r", raw, f"{name} contains a doubled carriage return")


class ReferenceTargetTests(unittest.TestCase):
    """Foreign keys and indexes are checked against the table list, not just
    for quoting.

    Quoting alone is not enough: `REFERENCES "Usr"(id)` is correctly quoted
    and still wrong. PostgreSQL only complains when the statement runs, by
    which point the deployment is already broken.
    """

    def _declared(self) -> set[str]:
        return set(QUOTED_TABLE.findall(SCHEMA))

    def test_every_foreign_key_points_at_a_declared_table(self):
        declared = self._declared()
        targets = set(re.findall(r'REFERENCES\s+"([A-Za-z_]+)"', SCHEMA))
        missing = sorted(targets - declared)
        self.assertEqual(missing, [], f"REFERENCES names tables that are never declared: {missing}")

    def test_every_index_is_built_on_a_declared_table(self):
        declared = self._declared()
        targets = set(re.findall(r'CREATE INDEX[^;]*?\bON\s+"([A-Za-z_]+)"', SCHEMA))
        missing = sorted(targets - declared)
        self.assertEqual(missing, [], f"CREATE INDEX names tables that are never declared: {missing}")

    def test_every_indexed_column_exists_on_its_table(self):
        """An index on a column that was renamed fails at deploy time, and
        the error names the index rather than the rename that caused it."""
        for statement in re.findall(r'CREATE INDEX[^;]+;', SCHEMA):
            match = re.search(r'ON\s+"([A-Za-z_]+)"\s*\(([^)]*)\)', statement)
            if match is None:
                continue
            table, columns = match.group(1), match.group(2)
            index_name = re.search(r'CREATE INDEX IF NOT EXISTS\s+(\w+)', statement)
            body = _table_body(table)
            for column in (c.strip() for c in columns.split(",")):
                column = column.split()[0] if column else column
                with self.subTest(index=index_name.group(1) if index_name else table, column=column):
                    # MULTILINE matters: column declarations start their own
                    # line, and without it "^" only ever matches the very
                    # start of the table body.
                    self.assertRegex(
                        body, re.compile(rf'^\s*{re.escape(column)}\s', re.MULTILINE),
                        f'index on "{table}" ({column}) — that table has no such column',
                    )

    def test_both_schemas_agree_on_their_indexes(self):
        """An index added to one file and forgotten in the other means the
        local database and the deployed one perform differently, which is
        the kind of difference nobody notices until it is slow."""
        sqlite_sql = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        names = lambda sql: set(re.findall(r'CREATE INDEX IF NOT EXISTS\s+(\w+)', sql))
        self.assertEqual(
            names(sqlite_sql), names(SCHEMA),
            f"only in schema.sql: {sorted(names(sqlite_sql) - names(SCHEMA))}; "
            f"only in schema_postgres.sql: {sorted(names(SCHEMA) - names(sqlite_sql))}",
        )


class UpsertKeyTests(unittest.TestCase):
    """db.insert_row() builds `ON CONFLICT (cols) DO UPDATE` from
    CONFLICT_COLUMNS. PostgreSQL rejects that at runtime unless those
    columns carry a UNIQUE or PRIMARY KEY constraint — another failure
    SQLite never reproduces, because its INSERT OR REPLACE needs nothing."""

    def test_every_conflict_key_has_a_matching_unique_constraint(self):
        for table, columns in db.CONFLICT_COLUMNS.items():
            with self.subTest(table=table):
                self.assertIn(table, db.TABLES)
                body = _table_body(table)
                found = [
                    tuple(c.strip() for c in group.split(","))
                    for group in re.findall(r'UNIQUE\s*\(([^)]*)\)', body)
                ]
                self.assertIn(
                    tuple(columns), found,
                    f'{table}: db.CONFLICT_COLUMNS says ON CONFLICT {columns}, '
                    f"but the table declares UNIQUE {found or 'nothing'}. "
                    "PostgreSQL will raise on every upsert into this table.",
                )

    def test_tables_without_a_conflict_key_upsert_on_their_primary_key(self):
        """Anything absent from CONFLICT_COLUMNS falls back to ("id",), so
        it needs an `id` primary key or the same failure appears."""
        for table in db.TABLES:
            if table in db.CONFLICT_COLUMNS:
                continue
            with self.subTest(table=table):
                self.assertRegex(
                    _table_body(table), r'\bid\s+TEXT\s+PRIMARY KEY',
                    f"{table} has no CONFLICT_COLUMNS entry, so insert_row falls "
                    "back to ON CONFLICT (id) — but it has no id primary key.",
                )


class ParityTests(unittest.TestCase):
    """The two schema files must describe the same database. A table added
    to one and forgotten in the other is the next version of this bug."""

    def test_both_schemas_declare_the_same_tables(self):
        sqlite_sql = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
        # SQLite is case-insensitive, so accept either spelling there.
        sqlite_tables = set(re.findall(
            r'CREATE TABLE IF NOT EXISTS\s+"?([A-Za-z_]+)"?\s*\(', sqlite_sql))
        postgres_tables = set(QUOTED_TABLE.findall(SCHEMA))
        self.assertEqual(
            sqlite_tables, postgres_tables,
            f"only in schema.sql: {sorted(sqlite_tables - postgres_tables)}; "
            f"only in schema_postgres.sql: {sorted(postgres_tables - sqlite_tables)}",
        )

    def test_every_declared_table_is_known_to_db_py(self):
        """A table in the schema that db.TABLES does not list can never be
        read or written — insert_row/fetch_all reject the name outright."""
        orphans = sorted(set(QUOTED_TABLE.findall(SCHEMA)) - set(db.TABLES))
        self.assertEqual(orphans, [], f"declared but unreachable from db.py: {orphans}")


if __name__ == "__main__":
    unittest.main()
