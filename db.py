"""SQLite persistence for the DREAM simulation harness.

Naming rule (docs/CLAUDE.md): never use the word "contract" in identifiers or
messages here — use "playbook" / "plan" / "agreement of understanding".

Usage:
    conn = get_connection()
    init_db(conn)
    insert_row(conn, "User", {"id": "u1", "journey_state": "dating"})
    fetch_one(conn, "User", id="u1")
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

SCHEMA_PATH = Path(__file__).with_name("schema.sql")
DEFAULT_DB_PATH = Path(__file__).parent / "data" / "dream.db"

# Every table defined in schema.sql. insert_row/fetch_all validate against
# this so a bad table name fails fast with a clear error instead of a raw
# sqlite3 syntax error from string-interpolating an identifier.
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


def get_connection(db_path: str | Path = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """Open a connection with foreign-key enforcement on (SQLite defaults it
    off) and dict-like row access. Pass ":memory:" for an ephemeral DB."""
    if db_path != ":memory:":
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection, schema_path: str | Path = SCHEMA_PATH) -> None:
    """Create all tables from schema.sql. Safe to call repeatedly — every
    CREATE TABLE in the schema is IF NOT EXISTS."""
    sql = Path(schema_path).read_text(encoding="utf-8")
    conn.executescript(sql)
    conn.commit()


def _check_table(table: str) -> None:
    if table not in TABLES:
        raise ValueError(f"Unknown table {table!r}; expected one of {sorted(TABLES)}")


def insert_row(conn: sqlite3.Connection, table: str, row: dict[str, Any]) -> Any:
    """Insert one row into `table`, or overwrite it if its id already
    exists (every table here uses a caller-assigned TEXT primary key, not
    an autoincrement integer, so re-running a seed script with the same ids
    should update in place rather than error). Returns the row's id.

    Note: REPLACE conflict resolution only changes behaviour for
    UNIQUE/PRIMARY KEY collisions — CHECK constraint violations (e.g. an
    invalid stage value) still raise sqlite3.IntegrityError exactly as
    before."""
    _check_table(table)
    columns = ", ".join(row.keys())
    placeholders = ", ".join("?" for _ in row)
    values = tuple(row.values())
    conn.execute(f"INSERT OR REPLACE INTO {table} ({columns}) VALUES ({placeholders})", values)
    conn.commit()
    return row.get("id")


def fetch_all(conn: sqlite3.Connection, table: str, **where: Any) -> list[dict[str, Any]]:
    """Fetch every row from `table`, optionally filtered by equality on the
    given keyword columns (e.g. fetch_all(conn, "CalendarEntry", couple_id=cid))."""
    _check_table(table)
    sql = f"SELECT * FROM {table}"
    values: tuple[Any, ...] = ()
    if where:
        clause = " AND ".join(f"{col} = ?" for col in where)
        sql += f" WHERE {clause}"
        values = tuple(where.values())
    cur = conn.execute(sql, values)
    return [dict(r) for r in cur.fetchall()]


def fetch_one(conn: sqlite3.Connection, table: str, **where: Any) -> dict[str, Any] | None:
    """Fetch the first row matching `where`, or None."""
    rows = fetch_all(conn, table, **where)
    return rows[0] if rows else None


def delete_row(conn: sqlite3.Connection, table: str, row_id: str) -> None:
    """Delete one row from `table` by id. No-op if it doesn't exist."""
    _check_table(table)
    conn.execute(f"DELETE FROM {table} WHERE id = ?", (row_id,))
    conn.commit()


def json_field(value: Any) -> str:
    """Serialize a list/dict value for one of the schema's *_json columns."""
    return json.dumps(value)


def load_json_field(value: str | None, default: Any = None) -> Any:
    """Deserialize a *_json column value read back from a row."""
    if value is None:
        return default
    return json.loads(value)
