"""Strictly increasing UTC ISO-8601 timestamps for rows that are ordered by created_at.

On Windows (and on fast machines anywhere) two datetime.now() calls a few
microseconds apart can return the same value. Rows created back to back (a BGV
request and its result-fetch child, an attempt and its review) then tie on
created_at and any "latest first" sort becomes arbitrary.

utc_now_iso() never returns the same or an earlier value twice within a
process: if the clock has not moved on, it advances by one microsecond. It is
thread-safe. Callers that sort rows must still use a deterministic tiebreaker,
because separate processes can produce equal values (see bgv_policy.newest_first).
"""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

_lock = threading.Lock()
_last: datetime | None = None


def _now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    global _last
    with _lock:
        current = _now()
        if _last is not None and current <= _last:
            current = _last + timedelta(microseconds=1)
        _last = current
    return current.isoformat()
