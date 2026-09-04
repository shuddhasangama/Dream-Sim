"""Suite-wide guards for mistakes that only show up on someone else's machine.

WHY THIS EXISTS
===============
2026-09-04: a test opened a SQLite connection to a temp file and never
closed it. On Linux an open file unlinks fine, so the suite passed. On
Windows the file is locked, TemporaryDirectory.cleanup() raises
PermissionError [WinError 32], and TWELVE tests failed at teardown — none
of them for the reason they were written to check.

That class of bug cannot be caught by reading the diff, because the code
is correct on the machine it was written on. So it is caught here instead:
any test that leaves a file-backed SQLite connection open fails, on every
platform, immediately, naming itself.

An in-memory connection locks nothing and is left alone.
"""

from __future__ import annotations

import sqlite3

import pytest

_TRACKED: list[tuple[str, sqlite3.Connection]] = []
_REAL_CONNECT = sqlite3.connect


def _tracking_connect(*args, **kwargs):
    conn = _REAL_CONNECT(*args, **kwargs)
    target = str(args[0]) if args else str(kwargs.get("database", "?"))
    _TRACKED.append((target, conn))
    return conn


@pytest.fixture(autouse=True)
def _no_leaked_sqlite_connections():
    """Fail any test that leaves a file-backed SQLite connection open.

    Checked after the test's own cleanups have run, which is exactly when
    Windows would try to delete the file and find it locked.
    """
    start = len(_TRACKED)
    sqlite3.connect = _tracking_connect
    try:
        yield
    finally:
        sqlite3.connect = _REAL_CONNECT

    leaked = []
    for target, conn in _TRACKED[start:]:
        if target in (":memory:", "?") or target.startswith("file::memory:"):
            continue  # nothing on disk to lock
        try:
            conn.execute("SELECT 1")
        except sqlite3.ProgrammingError:
            continue  # closed, as it should be
        except sqlite3.Error:
            continue  # unusable for some other reason; not a lock
        leaked.append(target)
        conn.close()  # so one failure does not cascade into every later test

    del _TRACKED[start:]

    if leaked:
        pytest.fail(
            "SQLite connection left open: " + ", ".join(sorted(set(leaked))) + "\n"
            "On Windows this locks the file and the temp directory cannot be "
            "deleted, failing at teardown rather than on the assertion.\n"
            "Fix: self.addCleanup(conn.close) when you open it."
        )
