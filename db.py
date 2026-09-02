"""Database persistence for the DREAM simulation harness.

Naming rule (docs/CLAUDE.md): never use the word "contract" in identifiers or
messages here — use "playbook" / "plan" / "agreement of understanding".

The persistence API intentionally hides database-specific SQL differences so
the application can run on SQLite locally and PostgreSQL in deployment.

Usage:
    conn = get_connection()
    init_db(conn)
    insert_row(conn, "User", {"id": "u1", "journey_state": "dating"})
    fetch_one(conn, "User", id="u1")
"""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

SQLITE_SCHEMA_PATH = Path(__file__).with_name("schema.sql")
POSTGRES_SCHEMA_PATH = Path(__file__).with_name("schema_postgres.sql")
DEFAULT_DB_PATH = Path(__file__).parent / "data" / "dream.db"

# Every table defined in schema.sql. insert_row/fetch_all validate against
# this so a bad table name fails fast with a clear error instead of a raw
# database syntax error from string-interpolating an identifier.
TABLES = {
    "User",
    "Couple",
    "RoadProfile",
    "CalendarEntry",
    "Playbook",
    "Difference",
    "GuruTopic",
    "WeeklyReport",
    "Exit",
    "Invite",
    # Dating stage (docs/dating-stage-spec.md §10)
    "Match",
    "LockIn",
    "Availability",
    "DatePlan",
    "Signature",
    "DateOutcome",
    "ComplianceEvent",
    # Progressive disclosure during Dating (docs/relationship-stage-spec.md Part A)
    "ContactRequest",
    "HomeInvite",
    # Dating exit / Relationship entry gate (docs/relationship-stage-spec.md Part B)
    "StageGate",
    "GateResponse",
    "GateAnalysis",
    # Vision / Chemistry at Relationship entry (docs/relationship-stage-spec.md Part C)
    "VisionEntry",
    "VisionChange",
    "ChemistryEntry",
    # Next Level conversation / invite-home rebuild (docs/intimacy-expectations-spec.md)
    "NextLevelThread",
}

CONFLICT_COLUMNS = {
    "RoadProfile": ("user_id", "couple_id"),
    "Playbook": ("couple_id", "stage"),
    "GuruTopic": ("couple_id", "stage", "topic_key"),
    "WeeklyReport": ("couple_id", "week_index"),
    "Match": ("user_id", "week", "slot"),
    "Availability": ("lockin_id", "user_id", "day", "meal_slot"),
    "Signature": ("dateplan_id", "user_id"),
    "DateOutcome": ("dateplan_id",),
    "GateResponse": ("pair_id", "user_id", "question_key"),
    "ChemistryEntry": ("user_id", "key"),
    "NextLevelThread": ("pair_id", "question_key"),
}


def _is_postgres_connection(conn: Any) -> bool:
    """Return True when `conn` is a PostgreSQL connection."""
    module = conn.__class__.__module__
    return module.startswith("psycopg") or module.startswith("psycopg2")


def _placeholder(conn: Any) -> str:
    """Return the parameter placeholder used by the active database."""
    return "%s" if _is_postgres_connection(conn) else "?"

def _table_name(conn: Any, table: str) -> str:
    """Return a safely formatted table identifier."""
    return f'"{table}"' if _is_postgres_connection(conn) else table

def _row_to_dict(row: Any) -> dict[str, Any]:
    """Convert a database row into a plain dictionary."""
    if row is None:
        return {}

    if isinstance(row, dict):
        return dict(row)

    return dict(row)


def _execute(conn: Any, sql: str, values: tuple[Any, ...] = ()) -> Any:
    """Execute SQL using the connection's DB-API interface."""
    return conn.execute(sql, values)


def _commit(conn: Any) -> None:
    """Commit the current transaction."""
    conn.commit()


def get_connection(db_path: str | Path = DEFAULT_DB_PATH) -> Any:
    """Open the configured database connection.

    SQLite remains the default for local development and the existing test
    suite. PostgreSQL is selected when DATABASE_URL is set to a PostgreSQL
    connection URL.
    """
    database_url = os.environ.get("DATABASE_URL")

    if database_url and database_url.startswith(("postgres://", "postgresql://")):
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError(
                "DATABASE_URL points to PostgreSQL, but the 'psycopg' package "
                "is not installed."
            ) from exc

        return psycopg.connect(database_url, row_factory=dict_row)

    if db_path != ":memory:":
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(
    conn: Any,
    schema_path: str | Path | None = None,
) -> None:
    """Create all tables for the active database backend."""

    if _is_postgres_connection(conn):
        path = Path(schema_path) if schema_path else POSTGRES_SCHEMA_PATH
        sql = path.read_text(encoding="utf-8")

        # psycopg does not provide SQLite's executescript().
        # PostgreSQL can execute these DDL statements sequentially.
        with conn.cursor() as cur:
            cur.execute(sql)

        _commit(conn)
        return

    path = Path(schema_path) if schema_path else SQLITE_SCHEMA_PATH
    sql = path.read_text(encoding="utf-8")
    conn.executescript(sql)
    _commit(conn)


def _check_table(table: str) -> None:
    if table not in TABLES:
        raise ValueError(
            f"Unknown table {table!r}; expected one of {sorted(TABLES)}"
        )


def insert_row(conn: Any, table: str, row: dict[str, Any]) -> Any:
    """Insert one row or update an existing logical row.

    SQLite keeps the existing INSERT OR REPLACE behavior.
    PostgreSQL uses the table's logical unique key where one exists,
    otherwise the primary-key id.
    """
    _check_table(table)

    table_name = _table_name(conn, table)

    columns_list = list(row.keys())
    columns = ", ".join(columns_list)
    values = tuple(row.values())
    placeholder = _placeholder(conn)

    if _is_postgres_connection(conn):
        placeholders = ", ".join(placeholder for _ in row)

        conflict_columns = CONFLICT_COLUMNS.get(table, ("id",))
        conflict_target = ", ".join(conflict_columns)

        update_columns = [
            column
            for column in columns_list
            if column not in conflict_columns
        ]

        if update_columns:
            updates = ", ".join(
                f"{column} = EXCLUDED.{column}"
                for column in update_columns
            )
            sql = (
                f"INSERT INTO {table_name} ({columns}) "
                f"VALUES ({placeholders}) "
                f"ON CONFLICT ({conflict_target}) "
                f"DO UPDATE SET {updates}"
            )
        else:
            sql = (
                f"INSERT INTO {table_name} ({columns}) "
                f"VALUES ({placeholders}) "
                f"ON CONFLICT ({conflict_target}) DO NOTHING"
            )
    else:
        placeholders = ", ".join(placeholder for _ in row)
        sql = (
            f"INSERT OR REPLACE INTO {table_name} "
            f"({columns}) VALUES ({placeholders})"
        )

    _execute(conn, sql, values)
    _commit(conn)
    return row.get("id")


def fetch_all(
    conn: Any,
    table: str,
    **where: Any,
) -> list[dict[str, Any]]:
    """Fetch every row from `table`, optionally filtered by equality."""
    _check_table(table)

    table_name = _table_name(conn, table)
    sql = f"SELECT * FROM {table_name}"
    values: tuple[Any, ...] = ()

    if where:
        placeholder = _placeholder(conn)
        clause = " AND ".join(
            f"{column} = {placeholder}"
            for column in where
        )
        sql += f" WHERE {clause}"
        values = tuple(where.values())

    cur = _execute(conn, sql, values)
    return [_row_to_dict(row) for row in cur.fetchall()]


def fetch_one(
    conn: Any,
    table: str,
    **where: Any,
) -> dict[str, Any] | None:
    """Fetch the first row matching `where`, or None."""
    rows = fetch_all(conn, table, **where)
    return rows[0] if rows else None


def delete_row(conn: Any, table: str, row_id: str) -> None:
    """Delete one row from `table` by id. No-op if it doesn't exist."""
    _check_table(table)

    table_name = _table_name(conn, table)
    placeholder = _placeholder(conn)
    _execute(
        conn,
        f"DELETE FROM {table_name} WHERE id = {placeholder}",
        (row_id,),
    )
    _commit(conn)


def json_field(value: Any) -> str:
    """Serialize a list/dict value for one of the schema's *_json columns."""
    return json.dumps(value)


def load_json_field(value: str | None, default: Any = None) -> Any:
    """Deserialize a *_json column value read back from a row."""
    if value is None:
        return default
    return json.loads(value)