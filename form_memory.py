"""What someone typed, kept across a rejected submit.

2026-09-09, user's rule: "Retain/remember selections if 'Continue to
Stats' fails. Check if there are any other screens in which remember
selections need to be done."

There were twelve others. They came in two shapes:

  RE-RENDER   The route renders the template again on failure, but from
              stored state that validation had just declined to write.
              /onboarding/vision and /align were this: the screen comes
              back blank and the error reads as "start again".

  REDIRECT    The route redirects on failure, and a redirect discards the
              request body by definition. Sorting twelve activities into
              buckets, typing a signature and ticking four terms, writing
              a paragraph of date feedback — all of it gone, and in most
              cases with no error shown either.

Rather than thirteen bespoke fixes, one mechanism that covers both: the
route remembers the submitted form, the redirect happens as before, and
the screen re-fills from what was remembered. A form is remembered for
exactly one render and then forgotten, so a later visit to the same
screen is clean.

This module is the pure half — shaping and matching. app.py owns the
session I/O, because that is the part that cannot be tested without a
request.
"""

from __future__ import annotations

from typing import Any

# Never remembered, whatever the form contains. A typed name on a
# ceremony is a signature: re-filling it would mean the second attempt
# was signed by the first attempt's keystrokes, which is exactly the
# thing a signature is supposed to rule out. The terms beside it are
# remembered; the name is typed again, deliberately.
NEVER_REMEMBER = frozenset({"signed_name"})


def capture(endpoint: str, fields: dict[str, Any], error: str | None = None) -> dict[str, Any]:
    """Shape a submitted form for storage.

    Values arrive as strings or lists of strings and are kept as they
    came, because a checkbox group and a text input have to be re-filled
    differently and only the template knows which is which.
    """
    kept = {k: v for k, v in (fields or {}).items() if k not in NEVER_REMEMBER}
    return {"endpoint": endpoint, "fields": kept, "error": error}


def recall(memory: dict[str, Any] | None, endpoint: str) -> dict[str, Any]:
    """What to re-fill this screen with.

    Returns empty rather than someone else's form when the remembered
    endpoint is not the one being rendered — a memory left behind by a
    different screen must never leak into this one.
    """
    if not memory or memory.get("endpoint") != endpoint:
        return {"fields": {}, "error": None, "recalled": False}
    return {"fields": memory.get("fields") or {},
            "error": memory.get("error"),
            "recalled": True}


def value(fields: dict[str, Any], key: str, fallback: Any = "") -> Any:
    """One remembered scalar, or the fallback the screen would have used.

    A remembered EMPTY string still wins over the fallback: clearing a
    field is a thing someone did on purpose, and restoring the old value
    would undo it in front of them.
    """
    if key not in fields:
        return fallback
    got = fields[key]
    if isinstance(got, list):
        return got[0] if got else ""
    return got


def chosen(fields: dict[str, Any], key: str, fallback: Any = None) -> list[str]:
    """One remembered multi-select, as a list.

    Same rule: a remembered empty list means they unticked everything,
    which is not the same as never having answered.
    """
    if key not in fields:
        return list(fallback or [])
    got = fields[key]
    if isinstance(got, list):
        return list(got)
    return [got] if got else []
