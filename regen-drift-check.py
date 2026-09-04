"""Rebuild drift-check.sql's expected-column list from schema_postgres.sql.

WHY THIS EXISTS
drift-check.sql catches columns the deployed database is missing. Its own
list was hand-maintained, so it drifted from the schema — round_no and
answers_closed_at shipped without ever being added to it. A drift checker
that drifts reports "clean" on exactly the deploy it was written for.

    python regen-drift-check.py

Rewrites the VALUES block in place and leaves everything around it alone.
test_db_reconcile.py fails if the two ever disagree again.
"""

from __future__ import annotations

import pathlib
import sys

import db

HEADER = "WITH expected(table_name, column_name) AS (VALUES\n"


def expected_rows() -> list[str]:
    schema = pathlib.Path("schema_postgres.sql").read_text(encoding="utf-8")
    rows = []
    for table, columns in db._expected_columns(schema).items():
        for name, _decl in columns:
            rows.append(f"  ('{table}','{name}')")
    return rows


def render(rows: list[str]) -> str:
    return HEADER + ",\n".join(rows) + "\n"


def main() -> int:
    path = pathlib.Path("drift-check.sql")
    text = path.read_text(encoding="utf-8")
    start = text.index(HEADER)
    end = text.index("\n)", start)
    updated = text[:start] + render(expected_rows()) + text[end + 1:]
    if updated == text:
        print("drift-check.sql already matches schema_postgres.sql")
        return 0
    path.write_text(updated, encoding="utf-8", newline="\n")
    print(f"drift-check.sql rewritten — {len(expected_rows())} columns")
    return 0


if __name__ == "__main__":
    sys.exit(main())
