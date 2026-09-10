"""What the user sees when something breaks, and what we keep so it can
be fixed.

2026-09-10, user's rule: "Can we have basic error handling so that
Internal server error is not shown. Enough details are captured for issue
resolution and debugging which will serve as a pointer for you."

Two halves, deliberately separated:

* The person gets a page in the product's own voice with ONE thing on it
  they can act on — a short reference code. Not a stack trace, not
  "Internal Server Error", and never a bare Flask page with a different
  typeface from the rest of the app.

* We get the whole incident: route, endpoint, method, who was signed in,
  the exception and its traceback, and the form field NAMES that were
  posted. Enough to find it without the person having to describe it.

Three rules this module keeps to, all learned the hard way in this
codebase:

1. **Recording an error must never raise.** Every capture path is
   wrapped. A logger that throws inside an error handler turns one broken
   screen into a broken site.

2. **The database may be the thing that is broken.** So the incident is
   written to stderr FIRST and to the ErrorReport table second, on a
   connection of its own that is always closed. If the table write fails,
   the stderr line still exists and still carries the same reference.

3. **No values, only names.** Form and query field NAMES are recorded;
   their contents are not. A traceback from /onboarding/stats should not
   put someone's salary in a log, and a traceback from a signature step
   should not put their legal name there.
"""

from __future__ import annotations

import json
import os
import random
import sys
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any

# Unambiguous when read aloud or typed from a screenshot: no O/0, no I/1,
# no S/5. A person reporting a problem is copying this by hand.
_ALPHABET = "ACDEFGHJKLMNPQRTUVWXYZ2346789"

# Field names that must never be recorded even as names, because the name
# alone says what the person was doing.
_NEVER_RECORD = {"signed_name", "password", "otp", "code", "token"}

# Recorded at import so every incident in one deploy shares a build id.
BUILD = os.environ.get("RAILWAY_GIT_COMMIT_SHA", "")[:7] or "local"


def new_reference() -> str:
    """A short code the person can read back to us: DC-4KQ7-M2."""
    rng = random.SystemRandom()
    body = "".join(rng.choice(_ALPHABET) for _ in range(6))
    return f"DC-{body[:4]}-{body[4:]}"


def _safe_field_names(mapping: Any) -> list[str]:
    try:
        return sorted({k for k in mapping.keys() if k not in _NEVER_RECORD})
    except Exception:
        return []


def describe(request: Any, user_id: str | None, exc: BaseException | None,
             status: int) -> dict[str, Any]:
    """Everything worth keeping about one incident. Never raises."""
    detail: dict[str, Any] = {
        "reference": new_reference(),
        "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": status,
        "build": BUILD,
        "user_id": user_id,
    }
    try:
        detail["method"] = request.method
        detail["path"] = request.path
        detail["endpoint"] = request.endpoint
        detail["referrer"] = request.referrer
        detail["form_fields"] = _safe_field_names(request.form)
        detail["query_fields"] = _safe_field_names(request.args)
    except Exception:
        pass
    if exc is not None:
        detail["error"] = type(exc).__name__
        try:
            detail["message"] = str(exc)[:500]
            detail["traceback"] = "".join(
                traceback.format_exception(type(exc), exc, exc.__traceback__))[-6000:]
        except Exception:
            pass
    return detail


def log(detail: dict[str, Any]) -> None:
    """One JSON line on stderr. This is the copy that always gets written,
    because it needs nothing but a working process."""
    try:
        line = {k: v for k, v in detail.items() if k != "traceback"}
        print("DREAM-ERROR " + json.dumps(line, default=str), file=sys.stderr, flush=True)
        if detail.get("traceback"):
            print(detail["traceback"], file=sys.stderr, flush=True)
    except Exception:
        pass


def record(conn_factory: Any, detail: dict[str, Any]) -> None:
    """Persist the incident so it can be looked up later. Best effort by
    design: the database is exactly the kind of thing that is broken when
    this runs, so a failure here is swallowed after the stderr line has
    already gone out.

    Its own connection, always closed — the request's connection may be
    in a failed transaction, and on PostgreSQL every further statement on
    it would fail too.
    """
    conn = None
    try:
        import db  # local import: this module must import cleanly alone

        conn = conn_factory()
        # A 500 can fire on a route that never touched the database — on a
        # brand-new deploy that means ErrorReport does not exist yet,
        # because the schema is applied lazily on the first get_db(). One
        # retry behind init_db() costs nothing and is the difference
        # between having the incident and not.
        try:
            _insert(db, conn, detail)
        except Exception:
            conn.rollback()
            db.init_db(conn)
            _insert(db, conn, detail)
        conn.commit()
    except Exception:
        pass
    finally:
        # 2026-09-05, user's rule: "please avoid these mistakes of opening
        # the connection and not closing it."
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass


def _insert(db: Any, conn: Any, detail: dict[str, Any]) -> None:
    db.insert_row(conn, "ErrorReport", {
            "id": str(uuid.uuid4()),
            "reference": detail["reference"],
            "occurred_at": detail["at"],
            "status": detail.get("status"),
            "build": detail.get("build"),
            "user_id": detail.get("user_id"),
            "method": detail.get("method"),
            "path": detail.get("path"),
            "endpoint": detail.get("endpoint"),
            "error_type": detail.get("error"),
            "message": detail.get("message"),
            "stack": detail.get("traceback"),
            "context_json": json.dumps({
                "form_fields": detail.get("form_fields", []),
                "query_fields": detail.get("query_fields", []),
                "referrer": detail.get("referrer"),
            }, ensure_ascii=False),
        })


# What the person reads. One sentence about what happened, one about what
# to do. No apology stacked on an apology, and nothing that blames them.
COPY = {
    400: {
        "title": "That did not come through",
        "body": "Something in what was sent did not look right, so nothing was saved. "
                "Go back, check the form and try once more.",
    },
    403: {
        "title": "Not open to you",
        "body": "This screen is not available at your stage of the journey, or it belongs to "
                "someone else.",
    },
    404: {
        "title": "There is nothing here",
        "body": "That page does not exist, or it has moved since you last had the link.",
    },
    500: {
        "title": "Something broke at our end",
        "body": "This one is ours, not yours. Nothing you were doing has been lost — it just "
                "did not finish. Try again in a moment.",
    },
}


def copy_for(status: int) -> dict[str, str]:
    return COPY.get(status, COPY[500])
