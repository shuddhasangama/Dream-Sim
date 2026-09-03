"""The ceremony (Segment E).

One pattern recurs six times across the journey:

    a playbook is drafted  ->  you sign it  ->  your face is captured
                           ->  you enter as verified

It happens before a date, before contact details are shared, before a home
visit, at Relationship entry, and at each stage checkpoint. Building it six
times would mean six places to get the rules slightly different in; this is
the single parameterised version, and the kind is the only thing that
varies.

Naming rule (docs/CLAUDE.md): never the word "contract" in identifiers or
messages — these are playbooks, plans and agreements of understanding.

WHAT THIS IS NOT
================
The face capture is a stub. `capture_face()` records that the step was
taken; it does not look at anything, and nothing here should be described
to a user as identity verification. Real liveness is Phase 9 of the
roadmap. The signature is a typed name, which is a record of intent, not
a legally binding instrument — docs say these agreements are guidelines,
and the copy must keep saying so.

Pure functions. The caller persists Ceremony rows.
"""

from __future__ import annotations

from typing import Any

# ── the four steps, always in this order ──────────────────────────────────

PLAYBOOK = "playbook"
SIGN = "sign"
FACE = "face"
DONE = "done"

STEPS = [
    (PLAYBOOK, "Read the playbook"),
    (SIGN, "Sign it"),
    (FACE, "Confirm it is you"),
    (DONE, "Enter as verified"),
]
STEP_KEYS = [key for key, _ in STEPS]


# ── the six occasions ─────────────────────────────────────────────────────
# `scope` names what the ceremony is ABOUT, so the same kind can happen
# again for a different date, a different stage, a different invitation.
# `fee` links to payments.py where one applies; None means free.

DATE_AGREEMENT = "date_agreement"
CONTACT_SHARE = "contact_share"
HOME_INVITE = "home_invite"
RELATIONSHIP_ENTRY = "relationship_entry"
STAGE_GATE = "stage_gate"

KINDS = {
    DATE_AGREEMENT: {
        "label": "Agreement of understanding",
        "blurb": "The terms for one evening, drawn from what you both already told us.",
        "scope": "one date",
        "fee": "agreement",
        "unlocks": "Your date is confirmed and prep opens.",
    },
    CONTACT_SHARE: {
        "label": "Sharing contact details",
        "blurb": "What you are handing over, and how to take it back.",
        "scope": "one exchange",
        "fee": None,
        "unlocks": "Numbers and handles become visible — to both of you, or neither.",
    },
    HOME_INVITE: {
        "label": "Invitation home",
        "blurb": "Where you are going, who else knows, and what either of you can call off.",
        "scope": "one visit",
        "fee": None,
        "unlocks": "The invitation is sent, with your trusted contact informed.",
    },
    RELATIONSHIP_ENTRY: {
        "label": "Becoming exclusive",
        "blurb": "What changes when you stop seeing other people, said out loud.",
        "scope": "the relationship",
        "fee": None,
        "unlocks": "You enter the Relationship stage and Guru's four pillars begin.",
    },
    STAGE_GATE: {
        "label": "Stage checkpoint",
        "blurb": "What moving to the next stage means, and what it does not.",
        "scope": "one checkpoint",
        "fee": "stage_gate",
        "unlocks": "You both move to the next stage together.",
    },
}


def kind_meta(kind: str) -> dict[str, Any]:
    if kind not in KINDS:
        raise ValueError(f"Unknown ceremony kind {kind!r}; expected one of {sorted(KINDS)}")
    return KINDS[kind]


def new_state(user_id: str, kind: str, scope_id: str, created_at: str) -> dict[str, Any]:
    """The Ceremony row to persist when someone first opens one."""
    kind_meta(kind)
    return {
        "id": f"{user_id}:{kind}:{scope_id}",
        "user_id": user_id,
        "kind": kind,
        "scope_id": scope_id,
        "playbook_ack": 0,
        "signed_name": None,
        "signed_at": None,
        "face_verified": 0,
        "completed_at": None,
        "created_at": created_at,
    }


# ── progress ──────────────────────────────────────────────────────────────


def _truthy(value: Any) -> bool:
    """Rows come back as 0/1 from SQLite and as booleans from psycopg."""
    return bool(value)


def next_step(state: dict[str, Any]) -> str:
    """Which step is open now. Strictly ordered — you cannot sign a
    playbook you have not opened, and the route relies on that rather than
    trusting whichever form was posted."""
    if not _truthy(state.get("playbook_ack")):
        return PLAYBOOK
    if not state.get("signed_name"):
        return SIGN
    if not _truthy(state.get("face_verified")):
        return FACE
    return DONE


def is_complete(state: dict[str, Any]) -> bool:
    return next_step(state) == DONE


def progress(state: dict[str, Any]) -> list[dict[str, Any]]:
    """The step rail. Same shape as the onboarding wizard's, so the two
    read as the same product rather than two different ones."""
    current = next_step(state)
    current_index = STEP_KEYS.index(current)
    return [
        {
            "key": key,
            "label": label,
            "index": i + 1,
            "state": "done" if i < current_index else ("current" if i == current_index else "todo"),
        }
        for i, (key, label) in enumerate(STEPS)
    ]


def ack_playbook(state: dict[str, Any]) -> dict[str, Any]:
    return {**state, "playbook_ack": 1}


def sign(state: dict[str, Any], typed_name: str, signed_at: str) -> dict[str, Any]:
    """Record the typed signature. A blank name is refused rather than
    stored as an empty signature — an unsigned agreement that looks signed
    is worse than an unsigned one."""
    name = (typed_name or "").strip()
    if not name:
        return state
    if not _truthy(state.get("playbook_ack")):
        return state
    return {**state, "signed_name": name, "signed_at": signed_at}


def capture_face(state: dict[str, Any]) -> dict[str, Any]:
    """STUB. Records that the step was taken. Nothing is looked at, and
    no user-facing copy should call this identity verification."""
    if not state.get("signed_name"):
        return state
    return {**state, "face_verified": 1}


def complete(state: dict[str, Any], completed_at: str) -> dict[str, Any]:
    if not is_complete(state):
        return state
    return {**state, "completed_at": state.get("completed_at") or completed_at}


def both_complete(states: list[dict[str, Any]], user_a: str, user_b: str) -> bool:
    """A ceremony binds two people. One signature is half of one."""
    done = {s["user_id"] for s in states if is_complete(s)}
    return user_a in done and user_b in done


# ── the playbooks ─────────────────────────────────────────────────────────
# Every clause is filled from what both people already told us. Nothing
# here is typed by hand, which is the point: the agreement is a readback,
# not a negotiation.


def date_clauses(ctx: dict[str, Any]) -> list[dict[str, str]]:
    """The seven clauses for one date. `ctx` carries the plan's own
    values; anything missing degrades to a readable placeholder rather
    than rendering None at someone."""
    slot = ctx.get("slot", "the agreed slot")
    meal = (ctx.get("meal") or "meal").lower()
    cuisine = ctx.get("cuisine") or "a cuisine you both eat"
    budget = ctx.get("budget") or "the band you both declared"
    split = ctx.get("bill_split") or "the split you both agreed"
    my_diet = ctx.get("my_diet") or "as declared"
    their_diet = ctx.get("their_diet") or "as declared"
    greeting = ctx.get("greeting")

    courtesies = (
        "Each party shall greet the other by name; keep phones face-down and silent for "
        "the duration; and answer questions honestly, including “I would rather not say”."
    )
    if greeting:
        courtesies = (
            f"Greeting preference on the record: {greeting.replace('-', ' ')}, to be respected "
            "without comment. " + courtesies
        )

    return [
        {"n": "1", "title": "Purpose",
         "body": "A single meeting, for the sole purpose of establishing whether a second "
                 "meeting is warranted. No expectation beyond that is created by this agreement."},
        {"n": "2", "title": "Time and place",
         "body": f"{slot} — {meal} at a {cuisine} venue convenient to both parties, confirmed "
                 "in advance."},
        {"n": "3", "title": "The bill",
         "body": f"Both parties declared a {budget} band. The bill shall be settled "
                 f"{split}, requested at the table, and settled without contest. Neither party "
                 "shall treat payment as leverage."},
        {"n": "4", "title": "Dietary terms",
         "body": f"First party: {my_diet}. Second party: {their_diet}. The venue shall carry "
                 "options satisfying both. No commentary on the other party's plate."},
        {"n": "5", "title": "Courtesies", "body": courtesies},
        {"n": "6", "title": "Exit",
         "body": "Either party may end the meeting at any point, without further explanation, "
                 "and shall be seen safely to transport."},
        {"n": "7", "title": "Confidentiality",
         "body": "Nothing disclosed at this meeting shall be repeated, screenshotted, or "
                 "posted. Flags recorded afterwards are visible to Guru only."},
    ]


def _simple_clauses(items: list[tuple[str, str]]) -> list[dict[str, str]]:
    return [{"n": str(i + 1), "title": t, "body": b} for i, (t, b) in enumerate(items)]


def clauses_for(kind: str, ctx: dict[str, Any] | None = None) -> list[dict[str, str]]:
    """The playbook for this kind of ceremony."""
    ctx = ctx or {}
    kind_meta(kind)

    if kind == DATE_AGREEMENT:
        return date_clauses(ctx)

    if kind == CONTACT_SHARE:
        channel = ctx.get("channel") or "the channel requested"
        return _simple_clauses([
            ("What is shared", f"Your {channel} becomes visible to the other party, and theirs "
                               "to you. Neither is shared until both have signed."),
            ("Withdrawal", "Either party may revoke at any time. Revoking hides the detail "
                           "again; it does not un-send anything already sent elsewhere."),
            ("Use", "Contact details are for contacting each other. They shall not be added to "
                    "any list, shared onward, or used to find the other party elsewhere."),
            ("No obligation", "Sharing a channel creates no expectation of a reply, a pace, or "
                              "a continued exchange."),
        ])

    if kind == HOME_INVITE:
        return _simple_clauses([
            ("The invitation", "One visit, to the address confirmed in the invitation, at the "
                               "agreed time. Neither party is committing to anything beyond it."),
            ("Someone knows", "Both parties confirm a trusted contact outside this app has been "
                              "told where they will be and when they expect to leave."),
            ("Calling it off", "Either party may cancel at any point before or during, without "
                               "explanation and without it counting against them anywhere."),
            ("Boundaries stand", "Everything either party recorded about pace and boundaries "
                                 "applies here exactly as it does anywhere else."),
        ])

    if kind == RELATIONSHIP_ENTRY:
        return _simple_clauses([
            ("Exclusivity", "Both parties leave the weekly matching pool. Neither will be shown "
                            "to anyone else, and neither will be shown anyone else."),
            ("What begins", "Guru's four pillars start: airing and resolving differences, "
                            "sharing expenses, mediation when wanted, and keeping romance alive."),
            ("What this is not", "This is an agreement of understanding between two people, not "
                                 "a legal instrument, and it creates no financial or legal tie."),
            ("Leaving", "Either party may exit. Exiting opens a private conversation with Guru "
                        "and a cool-off period before returning to the pool."),
        ])

    next_name = ctx.get("next_stage_name") or "the next stage"
    return _simple_clauses([
        ("Both, or neither", f"Moving to {next_name} needs both of you. One opt-in advances "
                             "nothing, and nothing here is automatic."),
        ("What changes", ctx.get("what_changes") or
                         f"{next_name} layers new topics onto the same four pillars. The pillars "
                         "themselves do not change."),
        ("What does not", "Nothing about this checkpoint is irreversible, and reaching a stage "
                          "creates no obligation to reach the next one."),
        ("Honesty", "This checkpoint works only if both answers are honest. A checkpoint passed "
                    "to please the other person is worse than one not yet passed."),
    ])
