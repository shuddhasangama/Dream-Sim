"""The DREAM journey state machine (docs/dream-full-journey-build-brief.pdf
§3, §5) — advanceStage() for Dating→Relationship→Engaged→Married, plus the
exit/re-entry path. Pure data-layer logic: no LLM, deterministic given an
explicit `today`, matching CLAUDE.md's "seeded randomness so runs are
reproducible" (dates here are simulation-controlled, never wall-clock, so
a test run never depends on what day it's actually run).

Structural note on advance_stage(): a Couple row doesn't exist until the
Dating→Relationship transition (schema.sql: "Stages after Dating share one
Couple record... Dating is a separate spec"). advance_stage() still
presents ONE function for all three forward transitions, as the brief asks
("Don't build three bespoke flows") — it just creates the Couple row on
the first call (couple_id not yet in the DB, user_a_id/user_b_id
supplied) and updates it on the other two (couple_id already exists).

The gate is always: verify mutual opt-in -> retake consent -> carry
ROAD/Playbook forward -> update stage -> re-parameterize Guru topics.
Never auto-advanced, never hard-forced — if either partner hasn't opted
in, advance_stage() returns advanced=False and touches nothing.

Exit path (§5): initiate_exit -> complete_exit_interview -> submit_feedback
-> synthesize_guru_feedback (STUBBED — see _stub_guru_synthesis) ->
mandated cool-off, enforced at the data layer by comparing `today` against
Exit.cooloff_ends, never by trusting a client-supplied flag -> attempt_reentry.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

import db
import lockin
import stage_gate
import vision

STAGE_ORDER = ["dating", "relationship", "engaged", "married"]

# "Four pillars... run in every stage" (build brief §2) — never removed.
PILLARS = ["air_resolve", "romance", "expense", "mediator"]

# Stage-specific topics layered on top of the pillars (build brief §4).
# Additive: a couple accumulates every topic from every stage they've
# passed through, never loses one advancing forward.
STAGE_TOPICS = {
    "relationship": ["vibe_chemistry", "shared_hobbies"],
    "engaged": ["wedding_planning", "family", "festivals"],
    "married": ["milestones"],
}

DEFAULT_COOLOFF_DAYS = 14  # "1-2 weeks mandated" — defaults to the top of that range


def next_stage(stage: str) -> str | None:
    """The stage after `stage` in the DREAM journey, or None if `stage` is
    already the last one (married) or unrecognized."""
    if stage not in STAGE_ORDER:
        return None
    idx = STAGE_ORDER.index(stage)
    return STAGE_ORDER[idx + 1] if idx + 1 < len(STAGE_ORDER) else None


def _cumulative_guru_topics(target_stage: str) -> list[tuple[str, str]]:
    """(kind, topic_key) pairs active once a couple reaches target_stage:
    the four pillars, plus every stage_topic introduced at or before it."""
    idx = STAGE_ORDER.index(target_stage)
    pairs = [("pillar", key) for key in PILLARS]
    for stage in STAGE_ORDER[1 : idx + 1]:  # skip 'dating' — no GuruTopic rows pre-Couple
        pairs += [("stage_topic", key) for key in STAGE_TOPICS[stage]]
    return pairs


def _seed_guru_topics(conn, couple_id: str, target_stage: str) -> None:
    for kind, key in _cumulative_guru_topics(target_stage):
        db.insert_row(
            conn,
            "GuruTopic",
            {
                "id": f"{couple_id}:{target_stage}:{key}",
                "couple_id": couple_id,
                "stage": target_stage,
                "kind": kind,
                "topic_key": key,
            },
        )


def _seed_road_profiles(conn, couple_id: str, user_a_id: str, user_b_id: str) -> None:
    """ROAD is "Set at Relationship entry" only (build brief §2) — never
    re-collected on later transitions (docs/stage-use-cases-testing-
    validation.md DTD-REL-002: "ROAD is not re-collected weekly"). Called
    once, from the Dating->Relationship branch of advance_stage()."""
    for user_id in (user_a_id, user_b_id):
        db.insert_row(
            conn,
            "RoadProfile",
            {
                "id": f"{couple_id}:{user_id}",
                "user_id": user_id,
                "couple_id": couple_id,
                "routine_json": "[]",
                "availability_json": "[]",
            },
        )


def _carry_forward_playbook(conn, couple_id: str, from_stage: str | None, target_stage: str, consent_version: str) -> None:
    """Playbook is "reaffirmed/extended per stage, not rewritten from
    scratch" (build brief §2) — the new stage's row starts from the
    previous stage's tiers, not empty ones."""
    previous = db.fetch_one(conn, "Playbook", couple_id=couple_id, stage=from_stage) if from_stage else None
    db.insert_row(
        conn,
        "Playbook",
        {
            "id": f"{couple_id}:{target_stage}",
            "couple_id": couple_id,
            "stage": target_stage,
            "tier_generic_json": previous["tier_generic_json"] if previous else "[]",
            "tier_vision_json": previous["tier_vision_json"] if previous else "[]",
            "tier_custom_json": previous["tier_custom_json"] if previous else "[]",
            "consent_signed_a": 1,
            "consent_signed_b": 1,
            "consent_version": consent_version,
        },
    )


def _set_users_journey_state(conn, user_ids: list[str], journey_state: str) -> None:
    for user_id in user_ids:
        row = db.fetch_one(conn, "User", id=user_id)
        if row is None:
            continue
        updated = dict(row)
        updated["journey_state"] = journey_state
        db.insert_row(conn, "User", updated)


def advance_stage(
    conn,
    couple_id: str,
    opt_in_a: bool,
    opt_in_b: bool,
    *,
    today: str,
    user_a_id: str | None = None,
    user_b_id: str | None = None,
    consent_version: str = "v1",
    biometric_a: bool = True,
    biometric_b: bool = True,
) -> dict[str, Any]:
    """Advance one couple to the next stage — Dating->Relationship (if
    `couple_id` doesn't exist yet: pass user_a_id/user_b_id) or
    Relationship->Engaged / Engaged->Married (if it does).

    Soft gate: returns {"advanced": False, "reason": ...} and changes
    nothing unless both opt_in_a and opt_in_b are True. Never auto-advances,
    never hard-forces (build brief §3).
    """
    existing = db.fetch_one(conn, "Couple", id=couple_id)

    if existing is None:
        if not user_a_id or not user_b_id:
            raise ValueError("Creating a new Couple (Dating->Relationship) needs user_a_id and user_b_id")
        from_stage: str | None = None
        target_stage = "relationship"
    else:
        from_stage = existing["stage"]
        target_stage = next_stage(from_stage)
        if target_stage is None:
            return {"advanced": False, "couple_id": couple_id, "from_stage": from_stage, "to_stage": None, "reason": "already at the final stage (married)"}
        user_a_id, user_b_id = existing["partner_a_id"], existing["partner_b_id"]

    if not (opt_in_a and opt_in_b):
        return {"advanced": False, "couple_id": couple_id, "from_stage": from_stage, "to_stage": target_stage, "reason": "mutual opt-in required — at least one partner has not opted in"}

    # retake consent block (new stageTaken value every transition)
    consent = {
        "consent_signed_a": 1,
        "consent_signed_b": 1,
        "consent_biometric_a": int(biometric_a),
        "consent_biometric_b": int(biometric_b),
        "consent_version": consent_version,
        "consent_stage_taken": target_stage,
    }

    if existing is None:
        db.insert_row(
            conn,
            "Couple",
            {
                "id": couple_id,
                "partner_a_id": user_a_id,
                "partner_b_id": user_b_id,
                "stage": target_stage,
                "entered_via": "progression",
                "start_date": today,
                "stage_week_index": 0,
                "exclusivity_ack_a": 1,
                "exclusivity_ack_b": 1,
                **consent,
            },
        )
        _seed_road_profiles(conn, couple_id, user_a_id, user_b_id)  # ROAD set, once
    else:
        updated = dict(existing)
        updated["stage"] = target_stage
        updated["stage_week_index"] = 0
        updated.update(consent)
        db.insert_row(conn, "Couple", updated)
        # ROAD carries forward automatically — it's keyed by couple_id, not
        # couple_id+stage, so nothing needs to run here to "carry" it.

    _carry_forward_playbook(conn, couple_id, from_stage, target_stage, consent_version)
    _seed_guru_topics(conn, couple_id, target_stage)
    _set_users_journey_state(conn, [user_a_id, user_b_id], target_stage)

    return {"advanced": True, "couple_id": couple_id, "from_stage": from_stage, "to_stage": target_stage, "reason": None}


# ── Relationship entry (docs/relationship-stage-spec.md Parts B/D) ───────

# §D5's Generic tier — same for every couple, never gated on Vision.
GENERIC_PLAYBOOK_TOPICS = [
    "communication_and_conflict",  # incl. keep-it-off-social-media
    "emotional_ownership",
    "debt_transparency",  # not income/property
    "quality_time",
    "extended_family",
    "values",
    "when_to_bring_in_guru",
]

WINDOW_WEEKS = 16  # §D6: the 16-week soft-checkpoint window


def build_relationship_playbook_tiers(vision_entries_for_couple: list[dict[str, Any]]) -> dict[str, list[str]]:
    """§D5's three tiers. Generic is fixed; Specific is only whatever
    this couple's combined Vision entries actually unlock
    (vision.unlocked_specific_topics()); Custom starts empty —
    "anything the couple adds themselves", added later via the app."""
    return {
        "generic": list(GENERIC_PLAYBOOK_TOPICS),
        "specific": vision.unlocked_specific_topics(vision_entries_for_couple),
        "custom": [],
    }


def schedule_weekly_report(conn, couple_id: str, stage: str, week_index: int) -> dict[str, Any]:
    """§D4's fixed-order weekly report. This project has no real async
    scheduler, so "schedule" means: create the (still-empty) week's
    report shell so Guru's mid-week/end-of-week sweep has somewhere to
    write appreciations/sorted/open/the four views/gap notes/romance
    notes/expense compliance/opt-in resources into, in the fixed order
    the schema's own column order already encodes. Idempotent per
    (couple_id, week_index) — db.py's INSERT OR REPLACE convention means
    calling this twice for the same week updates the same row, never
    duplicates it."""
    row_id = f"{couple_id}:{week_index}"
    db.insert_row(conn, "WeeklyReport", {"id": row_id, "couple_id": couple_id, "stage": stage, "week_index": week_index})
    return dict(db.fetch_one(conn, "WeeklyReport", id=row_id))


def sixteen_week_checkpoint(couple: dict[str, Any]) -> dict[str, Any]:
    """§D6: "Soft checkpoint at the end... No forced decision. Three
    paths presented with equal weight." Pure/stateless — just the
    trigger check and the fixed path list; the caller decides what
    happens next, same non-forcing pattern as advance_stage()'s gate."""
    reached = couple["stage_week_index"] >= WINDOW_WEEKS
    return {
        "checkpoint_reached": reached,
        "paths": ["progress_toward_engaged", "continue_in_relationship", "part_ways"] if reached else [],
    }


def enter_relationship(
    conn,
    couple_id: str,
    user_a_id: str,
    user_b_id: str,
    *,
    lockin_id: str,
    gate: dict[str, Any],
    gate_analysis: dict[str, Any],
    prerequisites: dict[str, Any],
    exclusivity_ack_a: bool,
    exclusivity_ack_b: bool,
    consent_a: bool,
    consent_b: bool,
    biometric_a: bool,
    biometric_b: bool,
    vision_entries_for_couple: list[dict[str, Any]],
    today: str,
    consent_version: str = "v1",
) -> dict[str, Any]:
    """B2 steps 5-9 / D1's on_relationship_entry, enforced in code rather
    than left to the UI to call things in the right order. Steps 1-4
    (Getting-to-Know Agreement close, private questionnaire, Guru's gap
    analysis, mutual confirm-to-progress) are the caller's job before
    calling this — stage_gate.py handles those — this function picks up
    from step 5 and refuses (returns {"advanced": False, "reason": ...},
    touching nothing) at whichever check fails first.

    Reuses advance_stage() for the actual Couple/ROAD/Playbook/GuruTopic
    creation (D1's "run ROAD setup once" / "activate Guru four pillars"
    are already exactly what that function does for any Dating->
    Relationship transition), then layers on the parts specific to a
    *gated* entry: a real exclusivity_ack (advance_stage() on its own
    always sets both to 1 unconditionally, since its other two
    transitions — Relationship->Engaged, Engaged->Married — don't go
    through a gate at all), opening Partnership Vision, generating the
    three-tier playbook from actual Vision content, scheduling week 0's
    report, and completing the LockIn this pair is graduating out of.
    """
    if gate["status"] != "open":
        return {"advanced": False, "reason": f"gate is not open (status={gate['status']!r})"}
    if stage_gate.has_unresolved_exclusivity_mismatch(gate_analysis):
        return {"advanced": False, "reason": "unresolved exclusivity mismatch — must be resolved before continuing"}
    if not prerequisites["met"]:
        return {"advanced": False, "reason": "Vision/Stats/Chemistry prerequisites are not all complete"}
    if not (exclusivity_ack_a and exclusivity_ack_b):
        return {"advanced": False, "reason": "both partners must acknowledge exclusivity"}
    if not (consent_a and consent_b):
        return {"advanced": False, "reason": "both partners must sign the consent block"}

    result = advance_stage(
        conn,
        couple_id,
        True,
        True,
        today=today,
        user_a_id=user_a_id,
        user_b_id=user_b_id,
        consent_version=consent_version,
        biometric_a=biometric_a,
        biometric_b=biometric_b,
    )
    if not result["advanced"]:
        return result

    couple = dict(db.fetch_one(conn, "Couple", id=couple_id))
    couple["exclusivity_ack_a"] = 1
    couple["exclusivity_ack_b"] = 1
    couple["partnership_vision_id"] = f"{couple_id}:vision"
    db.insert_row(conn, "Couple", couple)

    tiers = build_relationship_playbook_tiers(vision_entries_for_couple)
    playbook = dict(db.fetch_one(conn, "Playbook", couple_id=couple_id, stage="relationship"))
    playbook["tier_generic_json"] = db.json_field(tiers["generic"])
    playbook["tier_vision_json"] = db.json_field(tiers["specific"])
    db.insert_row(conn, "Playbook", playbook)

    schedule_weekly_report(conn, couple_id, "relationship", 0)

    lockin_row = db.fetch_one(conn, "LockIn", id=lockin_id)
    if lockin_row is not None:
        db.insert_row(conn, "LockIn", lockin.complete(dict(lockin_row)))

    return {**result, "lockin_completed": lockin_id}


# ── Exit / re-entry path (build brief §5) ─────────────────────────────────


def _get_exit(conn, exit_id: str) -> dict[str, Any]:
    row = db.fetch_one(conn, "Exit", id=exit_id)
    if row is None:
        raise ValueError(f"No Exit record with id {exit_id!r}")
    return dict(row)


def initiate_exit(conn, exit_id: str, couple_id: str, initiated_by: str) -> dict[str, Any]:
    """Start a structured exit — never a silent unmatch. Both partners'
    journey_state moves to 'exiting' immediately."""
    couple = db.fetch_one(conn, "Couple", id=couple_id)
    if couple is None:
        raise ValueError(f"No Couple with id {couple_id!r}")

    db.insert_row(
        conn,
        "Exit",
        {
            "id": exit_id,
            "couple_id": couple_id,
            "initiated_by": initiated_by,
            "stage_at_exit": couple["stage"],
            "status": "interview",
            "exit_interview_done": 0,
        },
    )
    _set_users_journey_state(conn, [couple["partner_a_id"], couple["partner_b_id"]], "exiting")
    return _get_exit(conn, exit_id)


def complete_exit_interview(conn, exit_id: str) -> dict[str, Any]:
    """Exit interview before any re-entry — facilitated closure if needed,
    not open-ended (build brief §5)."""
    record = _get_exit(conn, exit_id)
    if record["status"] != "interview":
        raise ValueError(f"Exit {exit_id!r} is past the interview step (status={record['status']!r})")
    record["exit_interview_done"] = 1
    record["status"] = "feedback"
    db.insert_row(conn, "Exit", record)
    return _get_exit(conn, exit_id)


def submit_feedback(conn, exit_id: str, *, feedback_a_raw: str | None = None, feedback_b_raw: str | None = None) -> dict[str, Any]:
    """Record either or both partners' private raw feedback. Can be called
    more than once as each partner submits in their own time — raw
    feedback is never shown to the other party (see synthesize_guru_feedback)."""
    record = _get_exit(conn, exit_id)
    if record["status"] != "feedback":
        raise ValueError(f"Exit {exit_id!r} is not accepting feedback (status={record['status']!r})")
    if feedback_a_raw is not None:
        record["feedback_a_raw"] = feedback_a_raw
    if feedback_b_raw is not None:
        record["feedback_b_raw"] = feedback_b_raw
    db.insert_row(conn, "Exit", record)
    return _get_exit(conn, exit_id)


def _stub_guru_synthesis(raw_feedback: str | None) -> str | None:
    """Placeholder for Guru's real narration (build brief step 6 — agents
    are layered on AFTER the deterministic core). Deliberately generic and
    NEVER includes the raw text: the whole point of Guru-mediation is that
    a partner's raw feedback never reaches the other party, even in a
    stubbed form. Replace with a real LLM call once agent narration lands."""
    if not raw_feedback:
        return None
    return "[Guru synthesis stub] A constructive, depersonalized growth reflection will be prepared here once agent narration is built."


def synthesize_guru_feedback(conn, exit_id: str, today: str, cooloff_days: int = DEFAULT_COOLOFF_DAYS) -> dict[str, Any]:
    """Turn each partner's raw feedback into the other partner's
    Guru-mediated synthesis (stubbed), then open the mandated cool-off.
    cooloff_days should be 7-14 ("1-2 weeks mandated")."""
    if not (7 <= cooloff_days <= 14):
        raise ValueError("cooloff_days must be within the mandated 1-2 week range (7-14)")
    record = _get_exit(conn, exit_id)
    if record["status"] != "feedback":
        raise ValueError(f"Exit {exit_id!r} has no feedback to synthesize (status={record['status']!r})")

    # A's synthesis is built from B's raw feedback (and vice versa) — never
    # the other way round, so nobody ever reads their own words reflected
    # back labeled as "what they said about you".
    record["guru_synthesis_for_a"] = _stub_guru_synthesis(record.get("feedback_b_raw"))
    record["guru_synthesis_for_b"] = _stub_guru_synthesis(record.get("feedback_a_raw"))
    record["status"] = "cooloff"
    cooloff_ends = (date.fromisoformat(today) + timedelta(days=cooloff_days)).isoformat()
    record["cooloff_ends"] = cooloff_ends
    db.insert_row(conn, "Exit", record)

    couple = db.fetch_one(conn, "Couple", id=record["couple_id"])
    if couple is not None:
        _set_users_journey_state(conn, [couple["partner_a_id"], couple["partner_b_id"]], "cooloff")

    return _get_exit(conn, exit_id)


def check_cooloff(conn, exit_id: str, today: str) -> dict[str, Any]:
    """Data-layer enforcement: is `today` on/after cooloff_ends? Flips
    status to 'complete' once true (idempotent) — the only source of truth
    for whether re-entry is allowed, never a client-supplied flag."""
    record = _get_exit(conn, exit_id)
    if record["status"] == "complete":
        return {"exit_id": exit_id, "cooloff_over": True, "cooloff_ends": record["cooloff_ends"]}
    if record["status"] != "cooloff":
        return {"exit_id": exit_id, "cooloff_over": False, "cooloff_ends": record.get("cooloff_ends")}

    cooloff_over = date.fromisoformat(today) >= date.fromisoformat(record["cooloff_ends"])
    if cooloff_over:
        record["status"] = "complete"
        db.insert_row(conn, "Exit", record)
    return {"exit_id": exit_id, "cooloff_over": cooloff_over, "cooloff_ends": record["cooloff_ends"]}


def attempt_reentry(conn, exit_id: str, today: str) -> dict[str, Any]:
    """The re-entry gate. Blocked until the cool-off has actually elapsed
    — enforced by check_cooloff()'s date comparison at the data layer, not
    by trusting the caller."""
    status = check_cooloff(conn, exit_id, today)
    if not status["cooloff_over"]:
        return {"allowed": False, "reason": f"cool-off active until {status['cooloff_ends']}"}

    record = _get_exit(conn, exit_id)
    couple = db.fetch_one(conn, "Couple", id=record["couple_id"])
    if couple is not None:
        _set_users_journey_state(conn, [couple["partner_a_id"], couple["partner_b_id"]], "re-entry")
    return {"allowed": True, "reason": None}
