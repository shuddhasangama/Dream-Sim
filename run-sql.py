"""Run a .sql file against the deployed database and print the results.

WHY THIS EXISTS
===============
Railway's "Console" tab on a Postgres service is a SHELL, not a query
editor — pasting SQL there hands it to bash, which answers with
"syntax error near unexpected token `('". You have to start a client
first. This is that client, using the psycopg the app already depends on,
so it needs nothing installed that requirements.txt does not already
bring in (no psql on PATH, which Windows usually lacks).

USAGE
=====
    set DATABASE_URL=<Railway's DATABASE_PUBLIC_URL>
    python run-sql.py find-test-pair.sql

Take the connection string from the Postgres service's Variables tab.
DATABASE_PUBLIC_URL is the one reachable from your machine; DATABASE_URL
there is the internal address and only resolves inside Railway.

Read-only by habit, not by enforcement: every statement runs inside one
transaction that is ROLLED BACK at the end. A SELECT file behaves
identically either way; an accidental UPDATE does not land.
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path


def split_statements(sql: str) -> list[str]:
    """Split on semicolons that are not inside a quoted string or a
    comment. Naive splitting breaks on things like '["Any"]'::jsonb the
    moment someone adds a semicolon inside a literal, and a query file
    that silently runs half of itself is worse than one that errors."""
    out, buf = [], []
    in_single = in_double = in_line_comment = in_block_comment = False
    i = 0
    while i < len(sql):
        ch, nxt = sql[i], sql[i + 1 : i + 2]
        if in_line_comment:
            if ch == "\n":
                in_line_comment = False
            buf.append(ch)
        elif in_block_comment:
            if ch == "*" and nxt == "/":
                in_block_comment = False
                buf.append("*/")
                i += 2
                continue
            buf.append(ch)
        elif in_single:
            buf.append(ch)
            if ch == "'":
                if nxt == "'":       # '' is an escaped quote, not a close
                    buf.append("'")
                    i += 2
                    continue
                in_single = False
        elif in_double:
            buf.append(ch)
            if ch == '"':
                in_double = False
        elif ch == "-" and nxt == "-":
            in_line_comment = True
            buf.append("--")
            i += 2
            continue
        elif ch == "/" and nxt == "*":
            in_block_comment = True
            buf.append("/*")
            i += 2
            continue
        elif ch == "'":
            in_single = True
            buf.append(ch)
        elif ch == '"':
            in_double = True
            buf.append(ch)
        elif ch == ";":
            out.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    out.append("".join(buf))
    return [s for s in (x.strip() for x in out) if s and not _only_comments(s)]


def _only_comments(statement: str) -> bool:
    for line in statement.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("--"):
            return False
    return True


def _title_of(statement: str) -> str:
    """The first comment line with real words in it. Skipping the rule
    lines matters — the section banners in find-test-pair.sql are comment
    lines made entirely of box-drawing characters, and taking the first
    comment blindly labels the section with a row of dashes."""
    candidates = []
    for line in statement.splitlines():
        stripped = line.strip()
        if not stripped.startswith("--"):
            continue
        text = stripped.lstrip("-").strip(" -\u2500\u2501\u2550")
        if sum(c.isalnum() for c in text) >= 3:
            candidates.append(text)
    # A numbered section heading beats the file's own banner, which would
    # otherwise label statement 1 with the title of the whole file.
    numbered = [c for c in candidates if re.match(r"^\d+\.", c)]
    if numbered:
        return numbered[0]
    return candidates[0] if candidates else ""


def render(rows: list[dict], columns: list[str]) -> str:
    """A plain aligned table. No dependency on tabulate for one script."""
    if not rows:
        return "(0 rows)"
    widths = {c: len(c) for c in columns}
    cells = []
    for row in rows:
        rendered = {c: ("" if row[c] is None else str(row[c])) for c in columns}
        for c in columns:
            widths[c] = max(widths[c], len(rendered[c]))
        cells.append(rendered)
    line = "-+-".join("-" * widths[c] for c in columns)
    head = " | ".join(c.ljust(widths[c]) for c in columns)
    body = "\n".join(" | ".join(r[c].ljust(widths[c]) for c in columns) for r in cells)
    return f"{head}\n{line}\n{body}\n({len(rows)} row{'s' if len(rows) != 1 else ''})"


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2

    url = os.environ.get("DATABASE_URL")
    if not url:
        print("DATABASE_URL is not set.\n"
              "Copy DATABASE_PUBLIC_URL from the Railway Postgres service's\n"
              "Variables tab, then:  set DATABASE_URL=<that value>")
        return 2
    if not url.startswith(("postgres://", "postgresql://")):
        print(f"DATABASE_URL does not look like a PostgreSQL URL: {url[:40]}...")
        return 2

    path = Path(sys.argv[1])
    if not path.exists():
        print(f"No such file: {path}")
        return 2

    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError:
        print("psycopg is not installed.  pip install -r requirements.txt")
        return 2

    statements = split_statements(path.read_text(encoding="utf-8"))
    print(f"{path.name}: {len(statements)} statement(s)\n")

    with psycopg.connect(url, row_factory=dict_row) as conn:
        for n, statement in enumerate(statements, start=1):
            title = _title_of(statement)
            print("=" * 72)
            print(f"[{n}] {title}" if title else f"[{n}]")
            print("=" * 72)
            try:
                with conn.cursor() as cur:
                    cur.execute(statement)
                    if cur.description is None:
                        print(f"{cur.statusmessage}\n")
                        continue
                    rows = cur.fetchall()
                    print(render(rows, [d.name for d in cur.description]), "\n")
            except psycopg.Error as exc:
                # Keep going: one bad statement should not hide the rest.
                conn.rollback()
                print(f"FAILED: {str(exc).strip()}\n")
        conn.rollback()   # nothing this script runs is meant to persist
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
