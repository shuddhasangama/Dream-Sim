-- DREAM simulation harness — consolidated data model.
-- Source: docs/dream-full-journey-build-brief.pdf, section 7 ("Full data model (consolidated)").
--
-- Naming rule (docs/CLAUDE.md): never use the word "contract" in identifiers or copy.
-- Use "playbook" / "plan" / "agreement of understanding" instead.
--
-- No appearance or skin-tone fields anywhere in this schema (docs/CLAUDE.md,
-- brief cross-cutting rules, guardrail DTD-XCT-001). test_db.py asserts this
-- by scanning the live schema, not just by inspection of this file.
--
-- Couple-scoped stage columns (Couple.stage, Playbook.stage, GuruTopic.stage,
-- WeeklyReport.stage, Exit.stage_at_exit) are constrained to the three stages
-- that use a Couple record — 'relationship' | 'engaged' | 'married'. Dating is
-- a separate spec per the brief ("Stages after Dating share one Couple
-- record; stage is a field, not a new table") and is out of scope here.
--
-- User.journey_state uses the full top-level JourneyState enum from section 1,
-- since a single user occupies it before a Couple record exists.
--
-- roadProfileRef / playbookRef / calendarRef from the brief's Couple struct are
-- intentionally not columns here: RoadProfile, Playbook and CalendarEntry all
-- carry couple_id back-references instead, which is the correct, non-redundant
-- way to model a one-to-one/one-to-many link in SQL (a forward pointer column
-- would just be a second, driftable copy of the same relationship).
--
-- Nested/variable-shape fields from the brief (User.stats/vision/skills,
-- Playbook's three tiers, WeeklyReport's list fields) are stored as JSON text
-- columns — read/write them with db.py's json_field helpers, not raw SQL.

PRAGMA foreign_keys = ON;

-- ── User ────────────────────────────────────────────────────────────────
-- { id, journeyState, verification:{ bgvStatus, consentVersion }, stats, vision, skills }
-- preferences_json is not in the brief's §7 struct verbatim, but every user
-- needs it to drive REACH (docs/agent-1-reach.pdf §3: preferences.fixed /
-- preferences.adjustable) — added here rather than left DB-less.
CREATE TABLE IF NOT EXISTS User (
    id                TEXT PRIMARY KEY,
    journey_state     TEXT NOT NULL CHECK (journey_state IN (
                          'onboarding', 'dating', 'relationship', 'engaged', 'married',
                          'exiting', 'cooloff', 're-entry'
                      )),
    bgv_status        TEXT NOT NULL DEFAULT 'declared' CHECK (bgv_status IN (
                          'declared', 'pending', 'verified', 'partially_verified', 'unverifiable'
                      )),
    consent_version   TEXT,
    stats_json        TEXT NOT NULL DEFAULT '{}',
    vision_json       TEXT NOT NULL DEFAULT '{}',
    skills_json       TEXT NOT NULL DEFAULT '{}',
    preferences_json  TEXT NOT NULL DEFAULT '{}'
);

-- ── Couple ──────────────────────────────────────────────────────────────
-- { id, partnerA_id, partnerB_id, stage, enteredVia, startDate, stageWeekIndex,
--   exclusivityAckA/B, consentBlock, road/playbook/calendar refs }
CREATE TABLE IF NOT EXISTS Couple (
    id                   TEXT PRIMARY KEY,
    partner_a_id         TEXT NOT NULL REFERENCES User(id),
    partner_b_id         TEXT NOT NULL REFERENCES User(id),
    stage                TEXT NOT NULL CHECK (stage IN ('relationship', 'engaged', 'married')),
    entered_via          TEXT NOT NULL CHECK (entered_via IN ('progression', 'lateral')),
    start_date           TEXT NOT NULL,
    stage_week_index     INTEGER NOT NULL DEFAULT 0,
    exclusivity_ack_a    INTEGER NOT NULL DEFAULT 0 CHECK (exclusivity_ack_a IN (0, 1)),
    exclusivity_ack_b    INTEGER NOT NULL DEFAULT 0 CHECK (exclusivity_ack_b IN (0, 1)),
    -- consentBlock: { signedA, signedB, biometricA, biometricB, version, stageTaken }
    consent_signed_a     INTEGER NOT NULL DEFAULT 0 CHECK (consent_signed_a IN (0, 1)),
    consent_signed_b     INTEGER NOT NULL DEFAULT 0 CHECK (consent_signed_b IN (0, 1)),
    consent_biometric_a  INTEGER NOT NULL DEFAULT 0 CHECK (consent_biometric_a IN (0, 1)),
    consent_biometric_b  INTEGER NOT NULL DEFAULT 0 CHECK (consent_biometric_b IN (0, 1)),
    consent_version      TEXT,
    consent_stage_taken  TEXT CHECK (
                            consent_stage_taken IS NULL
                            OR consent_stage_taken IN ('relationship', 'engaged', 'married')
                          ),
    -- (2026-08-28, relationship-stage-spec.md Part E / D1 "open Partnership
    -- Vision") — set once by journey.enter_relationship(); the couple's
    -- shared Vision doesn't have its own table (VisionEntry is per-user,
    -- below), so this is just an opaque id journey.py mints at entry.
    partnership_vision_id TEXT,
    CHECK (partner_a_id <> partner_b_id)
);

-- ── RoadProfile ─────────────────────────────────────────────────────────
-- { user_id, couple_id, routine:{work,fitness} } — the R and A of ROAD.
-- O/D (one-time Obligation/Date/travel exceptions) live in CalendarEntry.
-- Keep light: no belief-system fields (docs/dream-full-journey-build-brief.pdf §2).
--
-- routine_json: one merged weekly-recurring list — work and fitness blocks
-- together, each tagged with a category so they can still be told apart:
-- [{"id","category":"work"|"fitness","days":["Mon","Wed"],"label":"Office",
-- "start":"09:00","end":"18:00"}, ...]. Was two separate routine_work/
-- routine_fitness lists; merged into one so the ROAD flow captures a
-- single combined weekly picture instead of two disconnected ones.
--
-- availability_json: the SUBSET of this person's derived free time
-- (whatever routine_json's gaps leave open — computed in app.py, never
-- stored redundantly) that they've explicitly chosen to expose to their
-- partner: [{"id","days","start","end"}, ...]. Everything else about a
-- person's availability stays private by default (brief §8: "Consent-gated
-- sharing at the data layer — availability... default private").
CREATE TABLE IF NOT EXISTS RoadProfile (
    id                 TEXT PRIMARY KEY,
    user_id            TEXT NOT NULL REFERENCES User(id),
    couple_id          TEXT NOT NULL REFERENCES Couple(id),
    routine_json       TEXT NOT NULL DEFAULT '[]',
    availability_json  TEXT NOT NULL DEFAULT '[]',
    UNIQUE (user_id, couple_id)
);

-- ── CalendarEntry ───────────────────────────────────────────────────────
-- { id, couple_id, owner_id, type, travelMode, start, end, title, shared }
-- start/end renamed starts_at/ends_at to sidestep the SQL keyword END.
CREATE TABLE IF NOT EXISTS CalendarEntry (
    id          TEXT PRIMARY KEY,
    couple_id   TEXT NOT NULL REFERENCES Couple(id),
    owner_id    TEXT NOT NULL REFERENCES User(id),
    type        TEXT NOT NULL CHECK (type IN ('availability', 'obligation', 'date', 'travel')),
    travel_mode TEXT CHECK (
                    travel_mode IS NULL OR travel_mode IN ('solo', 'partner_solo', 'together')
                  ),
    starts_at   TEXT NOT NULL,
    ends_at     TEXT NOT NULL,
    title       TEXT,
    shared      INTEGER NOT NULL DEFAULT 0 CHECK (shared IN (0, 1)),
    -- travel_mode only makes sense for type='travel', and is required there
    CHECK (
        (type = 'travel' AND travel_mode IS NOT NULL)
        OR (type <> 'travel' AND travel_mode IS NULL)
    )
);

-- ── Playbook ────────────────────────────────────────────────────────────
-- { couple_id, stage, tierGeneric[], tierVision[], tierCustom[], consentBlock }
-- One row per couple per stage — reaffirmed/extended, never rewritten from scratch.
CREATE TABLE IF NOT EXISTS Playbook (
    id                TEXT PRIMARY KEY,
    couple_id         TEXT NOT NULL REFERENCES Couple(id),
    stage             TEXT NOT NULL CHECK (stage IN ('relationship', 'engaged', 'married')),
    tier_generic_json TEXT NOT NULL DEFAULT '[]',
    tier_vision_json  TEXT NOT NULL DEFAULT '[]',
    tier_custom_json  TEXT NOT NULL DEFAULT '[]',
    consent_signed_a  INTEGER NOT NULL DEFAULT 0 CHECK (consent_signed_a IN (0, 1)),
    consent_signed_b  INTEGER NOT NULL DEFAULT 0 CHECK (consent_signed_b IN (0, 1)),
    consent_version   TEXT,
    UNIQUE (couple_id, stage)
);

-- ── Difference ──────────────────────────────────────────────────────────
-- { id, couple_id, raisedBy, text, tag, status, consentToShare, weekRaised }
-- status mirrors WeeklyReport's own sorted[]/open[] buckets: a difference
-- starts 'open' and moves to 'sorted' once a weekly report resolves it.
CREATE TABLE IF NOT EXISTS Difference (
    id               TEXT PRIMARY KEY,
    couple_id        TEXT NOT NULL REFERENCES Couple(id),
    raised_by        TEXT NOT NULL REFERENCES User(id),
    text             TEXT NOT NULL,
    tag              TEXT,
    status           TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'sorted')),
    consent_to_share INTEGER NOT NULL DEFAULT 0 CHECK (consent_to_share IN (0, 1)),
    week_raised      INTEGER NOT NULL
);

-- ── GuruTopic ───────────────────────────────────────────────────────────
-- { couple_id, stage, kind: 'pillar' | 'stage_topic', key: ... }
-- topic_key is deliberately unconstrained (open-ended per the brief's design
-- principle: "no rigid belief-system matrices... keep it open to evolve").
CREATE TABLE IF NOT EXISTS GuruTopic (
    id         TEXT PRIMARY KEY,
    couple_id  TEXT NOT NULL REFERENCES Couple(id),
    stage      TEXT NOT NULL CHECK (stage IN ('relationship', 'engaged', 'married')),
    kind       TEXT NOT NULL CHECK (kind IN ('pillar', 'stage_topic')),
    topic_key  TEXT NOT NULL,
    UNIQUE (couple_id, stage, topic_key)
);

-- ── WeeklyReport ────────────────────────────────────────────────────────
-- { id, couple_id, stage, weekIndex, appreciations[], sorted[], open[],
--   views:{ownA,guruOnA,ownB,guruOnB,combined,guruOnPair}, gapNotes[],
--   romanceNotes, expenseCompliant, optInResources[] }
CREATE TABLE IF NOT EXISTS WeeklyReport (
    id                    TEXT PRIMARY KEY,
    couple_id             TEXT NOT NULL REFERENCES Couple(id),
    stage                 TEXT NOT NULL CHECK (stage IN ('relationship', 'engaged', 'married')),
    week_index            INTEGER NOT NULL,
    appreciations_json    TEXT NOT NULL DEFAULT '[]',
    sorted_json           TEXT NOT NULL DEFAULT '[]',
    open_json             TEXT NOT NULL DEFAULT '[]',
    view_own_a            TEXT,
    view_guru_on_a        TEXT,
    view_own_b            TEXT,
    view_guru_on_b        TEXT,
    view_combined         TEXT,
    view_guru_on_pair     TEXT,
    gap_notes_json        TEXT NOT NULL DEFAULT '[]',
    romance_notes         TEXT,
    expense_compliant     INTEGER NOT NULL DEFAULT 1 CHECK (expense_compliant IN (0, 1)),
    opt_in_resources_json TEXT NOT NULL DEFAULT '[]',
    UNIQUE (couple_id, week_index)
);

-- ── Exit ────────────────────────────────────────────────────────────────
-- { couple_id, initiatedBy, stageAtExit, status, exitInterviewDone,
--   feedbackA_raw, feedbackB_raw, guruSynthesisForA, guruSynthesisForB, cooloffEnds }
-- Raw feedback is private per-partner input; only the Guru-synthesized columns
-- are ever meant to be shown to the other partner (docs/CLAUDE.md, brief §5/§8).
CREATE TABLE IF NOT EXISTS Exit (
    id                   TEXT PRIMARY KEY,
    couple_id            TEXT NOT NULL REFERENCES Couple(id),
    initiated_by         TEXT NOT NULL REFERENCES User(id),
    stage_at_exit        TEXT NOT NULL CHECK (stage_at_exit IN ('relationship', 'engaged', 'married')),
    status               TEXT NOT NULL DEFAULT 'interview' CHECK (
                            status IN ('interview', 'feedback', 'cooloff', 'complete')
                          ),
    exit_interview_done  INTEGER NOT NULL DEFAULT 0 CHECK (exit_interview_done IN (0, 1)),
    feedback_a_raw       TEXT,
    feedback_b_raw       TEXT,
    guru_synthesis_for_a TEXT,
    guru_synthesis_for_b TEXT,
    cooloff_ends         TEXT
);

-- ── Dating stage (docs/dating-stage-spec.md §10) ───────────────────────────
-- Authoritative Dating-stage data model — supersedes the earlier
-- WeeklyInteraction stand-in (removed). revealed_at/window_closes_at/
-- created_at are simulation-clock stamps ("Day:Hour", e.g. "Mon:12" —
-- see clock.py's SimulationClock); the enclosing week number lives in its
-- own column alongside them so the string doesn't have to repeat it.
-- DatePlan.datetime is a real calendar date+time (app.py derives it from
-- the confirmed week/day/meal-slot via the existing WEEK_ONE_MONDAY epoch),
-- since a DatePlan represents an actual upcoming appointment, not just a
-- position in the simulated week.

-- { id, user_id, candidate_id, week, slot(1|2|3), revealed_at,
--   window_closes_at, action(interest|pass|none), pass_reason }
CREATE TABLE IF NOT EXISTS Match (
    id                 TEXT PRIMARY KEY,
    user_id            TEXT NOT NULL REFERENCES User(id),
    candidate_id       TEXT NOT NULL REFERENCES User(id),
    week               INTEGER NOT NULL,
    slot               INTEGER NOT NULL CHECK (slot IN (1, 2, 3)),
    revealed_at        TEXT NOT NULL,
    window_closes_at   TEXT NOT NULL,
    action             TEXT NOT NULL DEFAULT 'none' CHECK (action IN ('interest', 'pass', 'none')),
    pass_reason        TEXT,
    UNIQUE (user_id, week, slot),
    CHECK (user_id <> candidate_id)
);

-- { id, user_a, user_b, week, created_at, status }
-- release_reason isn't in the spec's own §10 column list but §4 explicitly
-- asks for "the reason recorded" when a lock-in returns its pair to the
-- pool — added here rather than left nowhere to put it.
-- dates_completed (2026-08-28, relationship-stage-spec.md §A1): a running
-- count of full date-cycles this LockIn has been through feedback for —
-- incremented once per date, only once BOTH partners' feedback decision
-- is in (lockin.increment_dates_completed()). Feeds
-- escalations.unlocks_available()'s "completed_dates >= 2 and
-- feedback_complete_both" check with a single field, since it can only
-- ever increment once both halves of that condition are true.
CREATE TABLE IF NOT EXISTS LockIn (
    id                TEXT PRIMARY KEY,
    user_a            TEXT NOT NULL REFERENCES User(id),
    user_b            TEXT NOT NULL REFERENCES User(id),
    week              INTEGER NOT NULL,
    created_at        TEXT NOT NULL,
    status            TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'released', 'completed')),
    release_reason    TEXT,
    dates_completed   INTEGER NOT NULL DEFAULT 0,
    CHECK (user_a <> user_b)
);

-- { id, lockin_id, user_id, day, meal_slot } — fixed slots per §5, not the
-- free-form time ranges RoadProfile/CalendarEntry use for Relationship-stage
-- availability. Friday has no breakfast/lunch (working day, §5's table).
CREATE TABLE IF NOT EXISTS Availability (
    id          TEXT PRIMARY KEY,
    lockin_id   TEXT NOT NULL REFERENCES LockIn(id),
    user_id     TEXT NOT NULL REFERENCES User(id),
    day         TEXT NOT NULL CHECK (day IN ('Fri', 'Sat', 'Sun')),
    meal_slot   TEXT NOT NULL CHECK (meal_slot IN ('breakfast', 'lunch', 'coffee', 'dinner')),
    UNIQUE (lockin_id, user_id, day, meal_slot),
    CHECK (NOT (day = 'Fri' AND meal_slot IN ('breakfast', 'lunch')))
);

-- { id, lockin_id, datetime, meal, venue, cuisine, bill_split, fee,
--   cancel_notice_hrs, cancel_fee, status }
-- selections_a_json/selections_b_json ({"greeting","dietary","dress"}) hold
-- §6's "both partners' selections appear in the signed plan" requirement —
-- not in the spec's bare column list, added as JSON columns (this schema's
-- existing convention for nested/variable-shape fields) since they're a
-- small per-partner bundle, not worth three more scalar columns each.
CREATE TABLE IF NOT EXISTS DatePlan (
    id                  TEXT PRIMARY KEY,
    lockin_id           TEXT NOT NULL REFERENCES LockIn(id),
    datetime            TEXT NOT NULL,
    meal                TEXT NOT NULL CHECK (meal IN ('breakfast', 'lunch', 'coffee', 'dinner')),
    venue               TEXT,
    cuisine             TEXT,
    budget_estimate     TEXT,
    -- 2026-08-28: only two bill-split options — no 50/50, host-pays, or
    -- alternate-treats.
    bill_split          TEXT NOT NULL CHECK (bill_split IN ('pay-your-own', 'one-third-two-thirds')),
    fee                 REAL NOT NULL DEFAULT 0,
    cancel_notice_hrs   INTEGER NOT NULL DEFAULT 24,
    cancel_fee          REAL NOT NULL DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'pending_signatures' CHECK (
                            status IN ('pending_signatures', 'confirmed', 'cancelled', 'completed')
                        ),
    selections_a_json   TEXT NOT NULL DEFAULT '{}',
    selections_b_json   TEXT NOT NULL DEFAULT '{}'
);

-- { id, dateplan_id, user_id, signed_at, face_verified }
-- A row only exists once actually signed (no "unsigned" placeholder row),
-- so signed_at is always set; is_confirmed() in dateplan.py checks for
-- both partners' rows existing with every ack true, per §6 step 4.
CREATE TABLE IF NOT EXISTS Signature (
    id                       TEXT PRIMARY KEY,
    dateplan_id              TEXT NOT NULL REFERENCES DatePlan(id),
    user_id                  TEXT NOT NULL REFERENCES User(id),
    signed_at                TEXT NOT NULL,
    face_verified            INTEGER NOT NULL CHECK (face_verified IN (0, 1)),
    ack_conduct              INTEGER NOT NULL DEFAULT 0 CHECK (ack_conduct IN (0, 1)),
    ack_cancellation         INTEGER NOT NULL DEFAULT 0 CHECK (ack_cancellation IN (0, 1)),
    ack_not_a_relationship   INTEGER NOT NULL DEFAULT 0 CHECK (ack_not_a_relationship IN (0, 1)),
    ack_liability            INTEGER NOT NULL DEFAULT 0 CHECK (ack_liability IN (0, 1)),
    UNIQUE (dateplan_id, user_id)
);

-- { id, dateplan_id, happened, together_photo, bill_photo, a_decision,
--   b_decision, a_reason, b_reason } — together_photo/bill_photo are
-- consent-gated booleans (§12: "default off"), never scored or inferred
-- from (§9: "never enters any scoring or inference").
--
-- Three-way per-partner decision (2026-08-28, user's explicit rule):
-- 'continue' = accept, keep dating (repeat the date cycle, same LockIn);
-- 'relationship' = accept, advance to Relationship stage — only when BOTH
-- partners pick this exact value (journey.advance_stage()'s own mutual
-- opt-in rule, unchanged); 'pass' = reject, back to the pool/REACH;
-- 'ghosted' = no response by close, never a person's own choice. See
-- outcomes.py's resolution()/apply_resolution() for what each combination
-- of a_decision/b_decision leads to.
-- a_green_flags_json/a_red_flags_json (and the b_ equivalents): each
-- partner's post-date flag feedback (guru_dating.GREEN_FLAGS/RED_FLAGS),
-- collected BEFORE the accept/reject decision below and required
-- regardless of which way that decision goes — "a journey of improvement"
-- (2026-08-28, user's explicit rule), not just feedback on a rejection.
CREATE TABLE IF NOT EXISTS DateOutcome (
    id                  TEXT PRIMARY KEY,
    dateplan_id         TEXT NOT NULL REFERENCES DatePlan(id),
    happened            INTEGER NOT NULL CHECK (happened IN (0, 1)),
    together_photo      INTEGER NOT NULL DEFAULT 0 CHECK (together_photo IN (0, 1)),
    bill_photo          INTEGER NOT NULL DEFAULT 0 CHECK (bill_photo IN (0, 1)),
    a_green_flags_json  TEXT NOT NULL DEFAULT '[]',
    a_red_flags_json    TEXT NOT NULL DEFAULT '[]',
    b_green_flags_json  TEXT NOT NULL DEFAULT '[]',
    b_red_flags_json    TEXT NOT NULL DEFAULT '[]',
    a_decision          TEXT CHECK (a_decision IS NULL OR a_decision IN ('continue', 'relationship', 'pass', 'ghosted')),
    b_decision          TEXT CHECK (b_decision IS NULL OR b_decision IN ('continue', 'relationship', 'pass', 'ghosted')),
    a_reason            TEXT,
    b_reason            TEXT,
    UNIQUE (dateplan_id)
);

-- { id, user_id, type(rating|no_show|late_cancel|report|violation), value,
--   week, notes } — value stays TEXT (a rating score, or just a label for
-- the non-numeric event types) since the spec doesn't give it a fixed
-- shape; compliance_status() in outcomes.py is what interprets it per type.
CREATE TABLE IF NOT EXISTS ComplianceEvent (
    id       TEXT PRIMARY KEY,
    user_id  TEXT NOT NULL REFERENCES User(id),
    type     TEXT NOT NULL CHECK (type IN ('rating', 'no_show', 'late_cancel', 'report', 'violation')),
    value    TEXT,
    week     INTEGER NOT NULL,
    notes    TEXT
);

-- ── Progressive disclosure during Dating (docs/relationship-stage-spec.md
-- Part A) ───────────────────────────────────────────────────────────────
-- pair_id is a LockIn.id, not a Couple.id — contact exchange unlocks
-- after a Week-2 lock-in + feedback cycle while a pair is still in Dating
-- (a Couple record doesn't exist until Relationship entry, the same
-- invariant the Dating-stage tables above already rely on). See
-- escalations.py. (HomeInvite, §A3's original simpler table, was defined
-- here too until its 2026-08-28 rebuild per
-- docs/intimacy-expectations-spec.md Part C — see that table's own
-- definition further down, near invite_home.py.)

-- { id, pair_id, requester_id, channel, status, requested_at, responded_at }
-- week isn't in the spec's own field list but is needed to enforce its
-- "rate-limit to one request per channel per week" rule (§A2) —
-- escalations.request_contact() checks it against existing rows.
CREATE TABLE IF NOT EXISTS ContactRequest (
    id            TEXT PRIMARY KEY,
    pair_id       TEXT NOT NULL REFERENCES LockIn(id),
    requester_id  TEXT NOT NULL REFERENCES User(id),
    channel       TEXT NOT NULL CHECK (channel IN ('phone', 'whatsapp', 'instagram', 'linkedin')),
    week          INTEGER NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'declined', 'ignored')),
    requested_at  TEXT NOT NULL,
    responded_at  TEXT
);

-- ── Dating exit / Relationship entry gate (docs/relationship-stage-spec.md
-- Part B) ───────────────────────────────────────────────────────────────
-- pair_id is a LockIn.id, same invariant as ContactRequest/HomeInvite
-- above — the gate opens from Dating ("after a pattern of sustained
-- lock-ins"), before any Couple record exists. See stage_gate.py.

-- { id, pair_id, trigger, opened_at, status, resolved_at }. The six
-- confirm_*/exclusivity_ack_*/consent_*/biometric_* flags aren't in the
-- spec's own Part E field list — they're where B2's steps 4/6/7 (mutual
-- confirm, exclusivity ack, consent signature) accumulate per-partner
-- state WHILE the gate is open, since a Couple record (which is where
-- exclusivity_ack/consent normally live post-entry) doesn't exist yet.
-- Defaulted/added by app.py at insert time, not by stage_gate.open_gate()
-- itself — same split as every other table's `id` column here.
CREATE TABLE IF NOT EXISTS StageGate (
    id                    TEXT PRIMARY KEY,
    pair_id               TEXT NOT NULL REFERENCES LockIn(id),
    trigger               TEXT NOT NULL CHECK (trigger IN ('guru_checkin', 'exclusivity_raised')),
    status                TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'must_resolve', 'progressed', 'declined')),
    opened_at             TEXT NOT NULL,
    resolved_at           TEXT,
    confirm_a             INTEGER NOT NULL DEFAULT 0 CHECK (confirm_a IN (0, 1)),
    confirm_b             INTEGER NOT NULL DEFAULT 0 CHECK (confirm_b IN (0, 1)),
    exclusivity_ack_a     INTEGER NOT NULL DEFAULT 0 CHECK (exclusivity_ack_a IN (0, 1)),
    exclusivity_ack_b     INTEGER NOT NULL DEFAULT 0 CHECK (exclusivity_ack_b IN (0, 1)),
    consent_a             INTEGER NOT NULL DEFAULT 0 CHECK (consent_a IN (0, 1)),
    consent_b             INTEGER NOT NULL DEFAULT 0 CHECK (consent_b IN (0, 1)),
    biometric_a           INTEGER NOT NULL DEFAULT 0 CHECK (biometric_a IN (0, 1)),
    biometric_b           INTEGER NOT NULL DEFAULT 0 CHECK (biometric_b IN (0, 1))
);

-- { id, pair_id, user_id, question_key, answer_text, readiness_scale } —
-- question_key/readiness_scale are validated in code
-- (stage_gate.STAGE_GATE_QUESTIONS), not duplicated into a CHECK here.
CREATE TABLE IF NOT EXISTS GateResponse (
    id               TEXT PRIMARY KEY,
    pair_id          TEXT NOT NULL REFERENCES LockIn(id),
    user_id          TEXT NOT NULL REFERENCES User(id),
    question_key     TEXT NOT NULL,
    answer_text      TEXT,
    readiness_scale  TEXT,
    UNIQUE (pair_id, user_id, question_key)
);

-- { id, pair_id, divergences_json, must_resolve_json, guru_prompts_json }
-- — stage_gate.analyze_gate()'s output, persisted verbatim. Never holds
-- raw answer_text — only question_key/category-level notes (§B4).
CREATE TABLE IF NOT EXISTS GateAnalysis (
    id                 TEXT PRIMARY KEY,
    pair_id            TEXT NOT NULL REFERENCES LockIn(id),
    divergences_json   TEXT NOT NULL DEFAULT '[]',
    must_resolve_json  TEXT NOT NULL DEFAULT '[]',
    guru_prompts_json  TEXT NOT NULL DEFAULT '[]'
);

-- ── Vision / Chemistry at Relationship entry (docs/relationship-stage-spec.md
-- Part C) ───────────────────────────────────────────────────────────────

-- { id, user_id, element_key, detail_text, added_at, parent_id } —
-- additive-only: vision.py defines no delete/edit-in-place function.
CREATE TABLE IF NOT EXISTS VisionEntry (
    id           TEXT PRIMARY KEY,
    user_id      TEXT NOT NULL REFERENCES User(id),
    element_key  TEXT NOT NULL,
    detail_text  TEXT NOT NULL,
    added_at     TEXT NOT NULL,
    parent_id    TEXT REFERENCES VisionEntry(id)
);

-- { id, user_id, element_key, from_value, to_value, declared_at,
--   disclosed_to_partner, guru_conversation_id } — the only path to a
-- material Vision reversal (vision.declare_vision_change()), which
-- itself refuses to build a row with disclosed_to_partner=False; the
-- CHECK below is defense-in-depth against a row constructed some other
-- way (Part F: "reversals require an explicit, partner-disclosed
-- declaration" — enforced in code AND schema, not just one or the other).
CREATE TABLE IF NOT EXISTS VisionChange (
    id                    TEXT PRIMARY KEY,
    user_id               TEXT NOT NULL REFERENCES User(id),
    element_key           TEXT NOT NULL,
    from_value            TEXT NOT NULL,
    to_value               TEXT NOT NULL,
    declared_at           TEXT NOT NULL,
    disclosed_to_partner  INTEGER NOT NULL CHECK (disclosed_to_partner = 1),
    guru_conversation_id  TEXT
);

-- { id, user_id, key, value, updated_at } — freely editable
-- (chemistry.py upserts by (user_id, key)), unlike Vision above.
CREATE TABLE IF NOT EXISTS ChemistryEntry (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES User(id),
    key         TEXT NOT NULL,
    value       TEXT NOT NULL,
    updated_at  TEXT NOT NULL,
    UNIQUE (user_id, key)
);

-- ── The "Next Level" conversation (docs/intimacy-expectations-spec.md
-- Part B) ───────────────────────────────────────────────────────────────
-- pair_id is a LockIn.id, same invariant as the tables above. One row per
-- (pair_id, question_key) — reciprocal unlock (see next_level.py's
-- submit_answer()) happens per-question, not once for the whole set.
-- opened_at isn't in the spec's own field list but every other
-- caller-facing "when did this open" table in this schema has one, added
-- here for the same reason ContactRequest's `week` was.
-- reluctance_flagged_to is application-private: only
-- next_level.visible_answers() ever exposes it, and only to the flagged
-- side (Part F: "never to their partner") — nothing at the schema layer
-- restricts which row a query can read, same as every other table here.
CREATE TABLE IF NOT EXISTS NextLevelThread (
    id                    TEXT PRIMARY KEY,
    pair_id               TEXT NOT NULL REFERENCES LockIn(id),
    opened_by             TEXT NOT NULL CHECK (opened_by IN ('user', 'guru_offer')),
    question_key          TEXT NOT NULL,
    opened_at             TEXT NOT NULL,
    answer_a              TEXT,
    answer_b              TEXT,
    declined_a            INTEGER NOT NULL DEFAULT 0 CHECK (declined_a IN (0, 1)),
    declined_b            INTEGER NOT NULL DEFAULT 0 CHECK (declined_b IN (0, 1)),
    answered_at_a         TEXT,
    answered_at_b         TEXT,
    revealed_at           TEXT,
    reluctance_flagged_to TEXT CHECK (reluctance_flagged_to IS NULL OR reluctance_flagged_to IN ('a', 'b')),
    UNIQUE (pair_id, question_key)
);

-- ── Invite home, with honest expectation disclosure
-- (docs/intimacy-expectations-spec.md Part C) — REBUILD of the simpler
-- HomeInvite from docs/relationship-stage-spec.md §A3 (Pass 1); this is
-- the table's second, superseding definition. No address field, by
-- design (§Part E note). See invite_home.py.
CREATE TABLE IF NOT EXISTS HomeInvite (
    id                           TEXT PRIMARY KEY,
    pair_id                      TEXT NOT NULL REFERENCES LockIn(id),
    requester_id                 TEXT NOT NULL REFERENCES User(id),
    proposed_datetime            TEXT NOT NULL,
    expectation_flag             TEXT NOT NULL CHECK (expectation_flag IN ('social_only', 'open_ended', 'intimacy_expected')),
    flag_seen_by_recipient_at    TEXT,
    status                       TEXT NOT NULL DEFAULT 'pending' CHECK (
                                    status IN ('pending', 'accepted', 'declined', 'ignored', 'revoked', 'completed')
                                  ),
    guidance_shown_a             INTEGER NOT NULL DEFAULT 0 CHECK (guidance_shown_a IN (0, 1)),
    guidance_shown_b             INTEGER NOT NULL DEFAULT 0 CHECK (guidance_shown_b IN (0, 1)),
    ack_signed_a                 INTEGER NOT NULL DEFAULT 0 CHECK (ack_signed_a IN (0, 1)),
    ack_signed_b                 INTEGER NOT NULL DEFAULT 0 CHECK (ack_signed_b IN (0, 1)),
    face_verified_a              INTEGER NOT NULL DEFAULT 0 CHECK (face_verified_a IN (0, 1)),
    face_verified_b              INTEGER NOT NULL DEFAULT 0 CHECK (face_verified_b IN (0, 1)),
    trusted_contact_notified_a   INTEGER NOT NULL DEFAULT 0 CHECK (trusted_contact_notified_a IN (0, 1)),
    trusted_contact_notified_b   INTEGER NOT NULL DEFAULT 0 CHECK (trusted_contact_notified_b IN (0, 1)),
    revoked_by                   TEXT REFERENCES User(id),
    revoked_at                   TEXT,
    acknowledgement_version      TEXT
);

-- ── Invite ──────────────────────────────────────────────────────────────
-- { fromUser_id, toContact, mode: 'start_together' | 'join_pool',
--   targetStage: 'relationship' | 'engaged' | 'married' | null // null for join_pool }
CREATE TABLE IF NOT EXISTS Invite (
    id            TEXT PRIMARY KEY,
    from_user_id  TEXT NOT NULL REFERENCES User(id),
    to_contact    TEXT NOT NULL,
    mode          TEXT NOT NULL CHECK (mode IN ('start_together', 'join_pool')),
    target_stage  TEXT CHECK (
                    target_stage IS NULL OR target_stage IN ('relationship', 'engaged', 'married')
                  ),
    CHECK (
        (mode = 'join_pool' AND target_stage IS NULL)
        OR (mode = 'start_together' AND target_stage IS NOT NULL)
    )
);

-- ── Account: the credential, kept apart from the dating profile ──
-- Added by Segment A. Nothing validates these yet (Case 1 specifies an
-- unvalidated front door); password_hash and the two verified_* flags
-- exist so Phase 3 can fill them without another schema change.
CREATE TABLE IF NOT EXISTS Account (
    id              TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL REFERENCES "User"(id),
    email           TEXT,
    phone           TEXT,
    password_hash   TEXT,
    verified_email  INTEGER NOT NULL DEFAULT 0 CHECK (verified_email IN (0, 1)),
    verified_phone  INTEGER NOT NULL DEFAULT 0 CHECK (verified_phone IN (0, 1)),
    created_at      TEXT NOT NULL,
    UNIQUE (user_id)
);
CREATE INDEX IF NOT EXISTS idx_account_email ON Account (email);
CREATE INDEX IF NOT EXISTS idx_account_phone ON Account (phone);

-- ── Verification: per-field background checks (Segment B) ──
-- User.bgv_status is the account-level roll-up; this is the field-level
-- detail behind it, because "salary in review, nationality verified" is a
-- state one enum value cannot express. bgv.aggregate_status() is the only
-- thing that collapses these into that column.
CREATE TABLE IF NOT EXISTS Verification (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES "User"(id),
    field       TEXT NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('pending', 'in_review', 'verified', 'failed')),
    note        TEXT,
    updated_at  TEXT NOT NULL,
    UNIQUE (user_id, field)
);
CREATE INDEX IF NOT EXISTS idx_verification_user ON Verification (user_id);

-- ── Payment: the four fees (Segment D) ──
-- Scoped, not one-off: (user, purpose, scope_id) is unique, so the
-- availability fee charges again for the next date rather than being
-- "paid forever", and a webhook that arrives twice writes once.
CREATE TABLE IF NOT EXISTS Payment (
    id          TEXT PRIMARY KEY,
    user_id     TEXT NOT NULL REFERENCES "User"(id),
    purpose     TEXT NOT NULL CHECK (purpose IN ('availability', 'agreement', 'stage_gate', 'guru')),
    scope_id    TEXT NOT NULL,
    amount_inr  INTEGER NOT NULL,
    status      TEXT NOT NULL CHECK (status IN ('pending', 'paid', 'failed')),
    reference   TEXT,
    created_at  TEXT NOT NULL,
    UNIQUE (user_id, purpose, scope_id)
);
CREATE INDEX IF NOT EXISTS idx_payment_user ON Payment (user_id);
