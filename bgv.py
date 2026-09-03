"""Background verification (Segment B).

The simulation has always had `User.bgv_status` — a five-value enum that
matching.py gates Lane A on — but nothing ever set it for a real person:
generate_users.py assigned it at random. This module is what makes that
column mean something.

Two levels of status, deliberately:

  * per FIELD (age, nationality, profession, salary bracket), which is
    what a person actually sees on the verification screen. The screen
    can show profession "In review" while nationality is already
    "Verified" — one account-level flag cannot express that.
  * per ACCOUNT, derived from the fields by `aggregate_status()`, which is
    the existing User.bgv_status value the rest of the codebase reads.

Nothing here calls a provider. `simulate_provider_callback()` is a stub
standing exactly where the real vendor webhook will land, so Segment B's
walkthrough runs today and the seam is obvious tomorrow. Choosing the
vendor is Phase 6 of the roadmap and a commercial decision, not a coding
one.

Pure functions; the caller persists Verification rows and the User row.
"""

from __future__ import annotations

from typing import Any

# ── the four fields, in the order the screen shows them ───────────────────

FIELDS = [
    ("age", "Age", "Confirms you are who you say, and old enough to be here."),
    ("nationality", "Nationality", "Checked against the document you provide."),
    ("profession", "Profession", "Checked with your employer or your registration."),
    ("salary_bracket", "Salary bracket", "Only the band is checked, and only the band is ever shown."),
]
FIELD_KEYS = [key for key, _, _ in FIELDS]

# Revised 2026-09-03: the raw salary is NOT verified. A person declares a
# salary in Stats so the app can derive a band; verification confirms the
# BAND and never the number. That is a smaller disclosure to the verifier
# for the same result, and it means the exact figure never has to leave
# the user's own profile.
#
# Nothing is derived from anything else any more, so this map is empty —
# kept rather than deleted because the machinery around it is what makes
# adding a derived field later a one-line change.
DERIVED_FROM: dict[str, str] = {}

# ── field-level statuses ──────────────────────────────────────────────────

PENDING = "pending"        # not started
IN_REVIEW = "in_review"    # sent to the provider, no answer yet
VERIFIED = "verified"      # the provider confirmed it
FAILED = "failed"          # the provider could not confirm it

FIELD_STATUSES = (PENDING, IN_REVIEW, VERIFIED, FAILED)

FIELD_STATUS_LABELS = {
    PENDING: "Not started",
    IN_REVIEW: "In review",
    VERIFIED: "Verified",
    FAILED: "Could not verify",
}

# What a derived field would show while its source is unresolved. No
# field is derived today (see DERIVED_FROM); this stays so the display
# logic does not have to grow a special case when one is.
DERIVED_WAITING_LABEL = "Pending"

# ── account-level statuses ────────────────────────────────────────────────
# These are User.bgv_status's CHECK values, unchanged. aggregate_status()
# is the only place that decides which one applies, so the mapping lives in
# exactly one spot.

DECLARED = "declared"
ACCOUNT_PENDING = "pending"
ACCOUNT_VERIFIED = "verified"
PARTIALLY_VERIFIED = "partially_verified"
UNVERIFIABLE = "unverifiable"


def new_verification_rows(user_id: str, updated_at: str) -> list[dict[str, Any]]:
    """One Verification row per field, all pending. Written once, when the
    user first opens the verification screen."""
    return [
        {
            "id": f"{user_id}:{key}",
            "user_id": user_id,
            "field": key,
            "status": PENDING,
            "note": None,
            "updated_at": updated_at,
        }
        for key in FIELD_KEYS
    ]


def statuses_from_rows(rows: list[dict[str, Any]]) -> dict[str, str]:
    """{field: status} for every known field, defaulting anything missing
    to pending rather than raising — a field added to FIELDS later must not
    break an account that predates it."""
    by_field = {r["field"]: r["status"] for r in rows if r["field"] in FIELD_KEYS}
    return {key: by_field.get(key, PENDING) for key in FIELD_KEYS}


def resolve_derived(statuses: dict[str, str]) -> dict[str, str]:
    """Force each derived field to mirror its source. No field is derived
    today, so this is the identity — see DERIVED_FROM."""
    resolved = dict(statuses)
    for field, source in DERIVED_FROM.items():
        resolved[field] = resolved.get(source, PENDING)
    return resolved


def aggregate_status(statuses: dict[str, str]) -> str:
    """Collapse the field statuses into one User.bgv_status value.

    The rules, in the order they are checked:
      - every field verified            -> verified
      - any field failed                -> unverifiable if none verified,
                                           otherwise partially_verified
      - any field in review             -> pending
      - nothing started                 -> declared
    """
    resolved = resolve_derived(statuses)
    values = list(resolved.values())

    if all(v == VERIFIED for v in values):
        return ACCOUNT_VERIFIED
    if any(v == FAILED for v in values):
        return PARTIALLY_VERIFIED if any(v == VERIFIED for v in values) else UNVERIFIABLE
    if any(v == IN_REVIEW for v in values):
        return ACCOUNT_PENDING
    return DECLARED


def is_verified(statuses: dict[str, str]) -> bool:
    return aggregate_status(statuses) == ACCOUNT_VERIFIED


def start_review(statuses: dict[str, str]) -> dict[str, str]:
    """"Begin verification": every pending field goes to the provider.
    Already-verified fields are not re-checked, and a failed field is
    retried — a retry is the whole point of an appeal."""
    return {
        key: (IN_REVIEW if value in (PENDING, FAILED) else value)
        for key, value in statuses.items()
    }


# ── the provider seam ─────────────────────────────────────────────────────

OUTCOMES = ("all_pass", "bracket_fails", "all_fail")

OUTCOME_LABELS = {
    "all_pass": "Everything checks out",
    "bracket_fails": "Salary bracket cannot be confirmed",
    "all_fail": "Nothing can be confirmed",
}


def simulate_provider_callback(statuses: dict[str, str], outcome: str = "all_pass") -> dict[str, str]:
    """Stub for the vendor webhook. THIS IS THE ONE FUNCTION A REAL BGV
    INTEGRATION REPLACES — everything else in this module stays as it is.

    Only fields currently in review are answered; a field the user never
    submitted is not silently decided for them.
    """
    if outcome not in OUTCOMES:
        raise ValueError(f"Unknown outcome {outcome!r}; expected one of {OUTCOMES}")

    def answer(field: str, current: str) -> str:
        if current != IN_REVIEW:
            return current
        if outcome == "all_pass":
            return VERIFIED
        if outcome == "all_fail":
            return FAILED
        return FAILED if field == "salary_bracket" else VERIFIED

    return {key: answer(key, value) for key, value in statuses.items()}


# ── what the screen renders ───────────────────────────────────────────────


def field_view(statuses: dict[str, str]) -> list[dict[str, Any]]:
    """One display row per field: label, why it is checked, and the status
    as a person should read it."""
    resolved = resolve_derived(statuses)
    rows = []
    for key, label, why in FIELDS:
        status = resolved[key]
        source = DERIVED_FROM.get(key)
        waiting_on_source = source is not None and status in (PENDING, IN_REVIEW)
        rows.append(
            {
                "key": key,
                "label": label,
                "why": why,
                "status": status,
                "status_label": DERIVED_WAITING_LABEL if waiting_on_source else FIELD_STATUS_LABELS[status],
                "derived": source is not None,
            }
        )
    return rows


def next_action(statuses: dict[str, str]) -> dict[str, Any]:
    """What the verification screen should offer next, given where the
    fields stand. One place decides, so the button and the copy can never
    disagree with each other."""
    account = aggregate_status(statuses)

    if account == ACCOUNT_VERIFIED:
        return {
            "state": "verified",
            "headline": "You are verified",
            "body": "Your stats are confirmed. You are in the matching pool from the next weekly run.",
            "cta": None,
        }
    if account == ACCOUNT_PENDING:
        return {
            "state": "in_review",
            "headline": "With the verifier",
            "body": "Nothing for you to do. This normally takes a day or two — we will let you know.",
            "cta": "simulate",
        }
    if account in (PARTIALLY_VERIFIED, UNVERIFIABLE):
        return {
            "state": "failed",
            "headline": "Some of it could not be confirmed",
            "body": "You can correct the details and send it back. Nothing is decided until you do.",
            "cta": "retry",
        }
    return {
        "state": "not_started",
        "headline": "Get verified",
        "body": "Four checks. Until they clear you can look around, but you will not appear in anyone's matches.",
        "cta": "start",
    }


# ── promotion ─────────────────────────────────────────────────────────────

PROMOTES_FROM = "onboarding"
PROMOTES_TO = "dating"


def promotion_for(journey_state: str, statuses: dict[str, str]) -> str | None:
    """The journey_state a user should move to once verification lands, or
    None to leave them where they are.

    Deliberately narrow: this only ever moves onboarding -> dating. Every
    later transition is a couple-level decision that goes through
    journey.advance_stage(), and this must never shortcut it.
    """
    if journey_state != PROMOTES_FROM:
        return None
    return PROMOTES_TO if is_verified(statuses) else None
