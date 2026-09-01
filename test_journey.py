"""Tests for journey.py."""

from __future__ import annotations

import unittest

import db
import journey
import stage_gate
import vision
from chemistry import INTIMACY_MANDATORY_KEYS as CHEMISTRY_INTIMACY_KEYS
from chemistry import MANDATORY_KEYS as CHEMISTRY_MANDATORY_KEYS
from vision import MANDATORY_STATS_FIELDS


class JourneyTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = db.get_connection(":memory:")
        db.init_db(self.conn)
        db.insert_row(self.conn, "User", {"id": "u_a", "journey_state": "dating"})
        db.insert_row(self.conn, "User", {"id": "u_b", "journey_state": "dating"})

    def tearDown(self) -> None:
        self.conn.close()

    def _enter_relationship(self, today: str = "2026-01-01") -> dict:
        return journey.advance_stage(
            self.conn, "couple_1", True, True, today=today, user_a_id="u_a", user_b_id="u_b"
        )


class AdvanceStageDatingToRelationshipTests(JourneyTestCase):
    def test_creates_couple_at_relationship(self) -> None:
        result = self._enter_relationship()
        self.assertTrue(result["advanced"])
        self.assertIsNone(result["from_stage"])
        self.assertEqual(result["to_stage"], "relationship")
        couple = db.fetch_one(self.conn, "Couple", id="couple_1")
        self.assertEqual(couple["stage"], "relationship")
        self.assertEqual(couple["consent_stage_taken"], "relationship")

    def test_requires_mutual_opt_in(self) -> None:
        result = journey.advance_stage(
            self.conn, "couple_1", True, False, today="2026-01-01", user_a_id="u_a", user_b_id="u_b"
        )
        self.assertFalse(result["advanced"])
        self.assertIsNone(db.fetch_one(self.conn, "Couple", id="couple_1"))

    def test_requires_user_ids_for_first_transition(self) -> None:
        with self.assertRaises(ValueError):
            journey.advance_stage(self.conn, "couple_1", True, True, today="2026-01-01")

    def test_seeds_road_profiles_once(self) -> None:
        self._enter_relationship()
        profiles = db.fetch_all(self.conn, "RoadProfile", couple_id="couple_1")
        self.assertEqual({p["user_id"] for p in profiles}, {"u_a", "u_b"})

    def test_seeds_pillars_and_relationship_topics(self) -> None:
        self._enter_relationship()
        rows = db.fetch_all(self.conn, "GuruTopic", couple_id="couple_1", stage="relationship")
        keys = {r["topic_key"] for r in rows}
        self.assertEqual(keys, {"air_resolve", "romance", "expense", "mediator", "vibe_chemistry", "shared_hobbies"})
        kinds = {r["topic_key"]: r["kind"] for r in rows}
        for pillar in journey.PILLARS:
            self.assertEqual(kinds[pillar], "pillar")
        self.assertEqual(kinds["vibe_chemistry"], "stage_topic")

    def test_syncs_both_users_journey_state(self) -> None:
        self._enter_relationship()
        self.assertEqual(db.fetch_one(self.conn, "User", id="u_a")["journey_state"], "relationship")
        self.assertEqual(db.fetch_one(self.conn, "User", id="u_b")["journey_state"], "relationship")

    def test_playbook_starts_empty_with_first_stage(self) -> None:
        self._enter_relationship()
        pb = db.fetch_one(self.conn, "Playbook", couple_id="couple_1", stage="relationship")
        self.assertIsNotNone(pb)
        self.assertEqual(pb["tier_generic_json"], "[]")


class AdvanceStageLaterTransitionsTests(JourneyTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._enter_relationship(today="2026-01-01")

    def test_relationship_to_engaged(self) -> None:
        result = journey.advance_stage(self.conn, "couple_1", True, True, today="2026-05-01")
        self.assertTrue(result["advanced"])
        self.assertEqual(result["from_stage"], "relationship")
        self.assertEqual(result["to_stage"], "engaged")
        self.assertEqual(db.fetch_one(self.conn, "Couple", id="couple_1")["stage"], "engaged")

    def test_consent_is_retaken_with_a_new_stage_taken_value(self) -> None:
        journey.advance_stage(self.conn, "couple_1", True, True, today="2026-05-01", consent_version="v2")
        couple = db.fetch_one(self.conn, "Couple", id="couple_1")
        self.assertEqual(couple["consent_stage_taken"], "engaged")
        self.assertEqual(couple["consent_version"], "v2")
        self.assertEqual(couple["consent_signed_a"], 1)
        self.assertEqual(couple["consent_signed_b"], 1)

    def test_road_carries_forward_not_recreated(self) -> None:
        before = {r["id"] for r in db.fetch_all(self.conn, "RoadProfile", couple_id="couple_1")}
        journey.advance_stage(self.conn, "couple_1", True, True, today="2026-05-01")
        after = {r["id"] for r in db.fetch_all(self.conn, "RoadProfile", couple_id="couple_1")}
        self.assertEqual(before, after)  # same two rows, nothing added or replaced

    def test_playbook_reaffirmed_and_extended_not_rewritten(self) -> None:
        # seed some content on the relationship-stage playbook
        pb = db.fetch_one(self.conn, "Playbook", couple_id="couple_1", stage="relationship")
        pb["tier_generic_json"] = db.json_field(["greet by name", "phones down"])
        db.insert_row(self.conn, "Playbook", pb)

        journey.advance_stage(self.conn, "couple_1", True, True, today="2026-05-01")
        engaged_pb = db.fetch_one(self.conn, "Playbook", couple_id="couple_1", stage="engaged")
        self.assertEqual(
            db.load_json_field(engaged_pb["tier_generic_json"]), ["greet by name", "phones down"]
        )

    def test_guru_topics_are_additive_never_dropped(self) -> None:
        journey.advance_stage(self.conn, "couple_1", True, True, today="2026-05-01")  # -> engaged
        rows = db.fetch_all(self.conn, "GuruTopic", couple_id="couple_1", stage="engaged")
        keys = {r["topic_key"] for r in rows}
        # relationship-stage topics are still present at engaged
        self.assertIn("vibe_chemistry", keys)
        self.assertIn("shared_hobbies", keys)
        # plus the new engaged-stage topics
        self.assertIn("wedding_planning", keys)
        self.assertIn("family", keys)
        self.assertIn("festivals", keys)
        for pillar in journey.PILLARS:
            self.assertIn(pillar, keys)

    def test_full_progression_to_married_then_blocked(self) -> None:
        r2 = journey.advance_stage(self.conn, "couple_1", True, True, today="2026-05-01")
        self.assertEqual(r2["to_stage"], "engaged")
        r3 = journey.advance_stage(self.conn, "couple_1", True, True, today="2026-09-01")
        self.assertEqual(r3["to_stage"], "married")
        r4 = journey.advance_stage(self.conn, "couple_1", True, True, today="2027-01-01")
        self.assertFalse(r4["advanced"])
        self.assertIsNone(r4["to_stage"])
        self.assertEqual(db.fetch_one(self.conn, "Couple", id="couple_1")["stage"], "married")

    def test_one_sided_opt_in_changes_nothing(self) -> None:
        before = dict(db.fetch_one(self.conn, "Couple", id="couple_1"))
        result = journey.advance_stage(self.conn, "couple_1", True, False, today="2026-05-01")
        self.assertFalse(result["advanced"])
        after = dict(db.fetch_one(self.conn, "Couple", id="couple_1"))
        self.assertEqual(before, after)
        self.assertEqual(db.fetch_one(self.conn, "User", id="u_a")["journey_state"], "relationship")


class EnterRelationshipTests(JourneyTestCase):
    def setUp(self) -> None:
        super().setUp()
        db.insert_row(
            self.conn, "LockIn",
            {"id": "lockin-1", "user_a": "u_a", "user_b": "u_b", "week": 3, "created_at": "Mon:14", "status": "active"},
        )
        self.gate = stage_gate.open_gate("lockin-1", "exclusivity_raised", "Mon:12")
        self.no_divergence_analysis = {"pair_id": "lockin-1", "divergences": [], "must_resolve": [], "guru_prompts": []}
        self.met_prerequisites = vision.prerequisites_met(
            [{"user_id": "u_a", "element_key": "children"}],
            {field: "x" for field in MANDATORY_STATS_FIELDS},
            [{"key": k, "value": "x"} for k in (*CHEMISTRY_MANDATORY_KEYS, *CHEMISTRY_INTIMACY_KEYS)],
        )

    def _enter(self, **overrides) -> dict:
        kwargs = dict(
            lockin_id="lockin-1",
            gate=self.gate,
            gate_analysis=self.no_divergence_analysis,
            prerequisites=self.met_prerequisites,
            exclusivity_ack_a=True,
            exclusivity_ack_b=True,
            consent_a=True,
            consent_b=True,
            biometric_a=True,
            biometric_b=True,
            vision_entries_for_couple=[{"element_key": "children"}, {"element_key": "cohabitation"}],
            today="2026-03-01",
        )
        kwargs.update(overrides)
        return journey.enter_relationship(self.conn, "couple_1", "u_a", "u_b", **kwargs)

    def test_advances_to_relationship_when_every_gate_passes(self) -> None:
        result = self._enter()
        self.assertTrue(result["advanced"])
        self.assertEqual(result["to_stage"], "relationship")
        self.assertEqual(db.fetch_one(self.conn, "Couple", id="couple_1")["stage"], "relationship")

    def test_completes_the_lockin(self) -> None:
        self._enter()
        self.assertEqual(db.fetch_one(self.conn, "LockIn", id="lockin-1")["status"], "completed")

    def test_sets_real_exclusivity_ack_and_partnership_vision_id(self) -> None:
        self._enter()
        couple = db.fetch_one(self.conn, "Couple", id="couple_1")
        self.assertEqual(couple["exclusivity_ack_a"], 1)
        self.assertEqual(couple["exclusivity_ack_b"], 1)
        self.assertIsNotNone(couple["partnership_vision_id"])

    def test_generates_playbook_specific_tier_from_vision(self) -> None:
        self._enter()
        pb = db.fetch_one(self.conn, "Playbook", couple_id="couple_1", stage="relationship")
        specific = db.load_json_field(pb["tier_vision_json"])
        self.assertIn("children", specific)
        self.assertIn("household_and_shared_space", specific)
        generic = db.load_json_field(pb["tier_generic_json"])
        self.assertEqual(generic, journey.GENERIC_PLAYBOOK_TOPICS)

    def test_schedules_week_zero_report(self) -> None:
        self._enter()
        report = db.fetch_one(self.conn, "WeeklyReport", couple_id="couple_1", week_index=0)
        self.assertIsNotNone(report)

    def test_refuses_when_gate_not_open(self) -> None:
        closed_gate = {**self.gate, "status": "progressed"}
        result = self._enter(gate=closed_gate)
        self.assertFalse(result["advanced"])
        self.assertIsNone(db.fetch_one(self.conn, "Couple", id="couple_1"))

    def test_refuses_on_unresolved_exclusivity_mismatch(self) -> None:
        mismatched = {"pair_id": "lockin-1", "divergences": [], "must_resolve": [{"question_key": "exclusivity_check", "note": "x"}], "guru_prompts": []}
        result = self._enter(gate_analysis=mismatched)
        self.assertFalse(result["advanced"])
        self.assertIn("exclusivity mismatch", result["reason"])

    def test_refuses_when_prerequisites_incomplete(self) -> None:
        result = self._enter(prerequisites={"met": False, "vision_met": False, "stats_missing": ["age"], "chemistry_missing": []})
        self.assertFalse(result["advanced"])

    def test_refuses_without_both_exclusivity_acks(self) -> None:
        result = self._enter(exclusivity_ack_b=False)
        self.assertFalse(result["advanced"])

    def test_refuses_without_both_consents(self) -> None:
        result = self._enter(consent_a=False)
        self.assertFalse(result["advanced"])
        self.assertIsNone(db.fetch_one(self.conn, "Couple", id="couple_1"))


class ScheduleWeeklyReportTests(JourneyTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._enter_relationship()

    def test_creates_a_report_shell(self) -> None:
        report = journey.schedule_weekly_report(self.conn, "couple_1", "relationship", 1)
        self.assertEqual(report["couple_id"], "couple_1")
        self.assertEqual(report["week_index"], 1)

    def test_idempotent_for_the_same_week(self) -> None:
        journey.schedule_weekly_report(self.conn, "couple_1", "relationship", 1)
        journey.schedule_weekly_report(self.conn, "couple_1", "relationship", 1)
        rows = db.fetch_all(self.conn, "WeeklyReport", couple_id="couple_1", week_index=1)
        self.assertEqual(len(rows), 1)


class SixteenWeekCheckpointTests(unittest.TestCase):
    def test_not_reached_before_week_16(self) -> None:
        result = journey.sixteen_week_checkpoint({"stage_week_index": 10})
        self.assertFalse(result["checkpoint_reached"])
        self.assertEqual(result["paths"], [])

    def test_reached_at_week_16(self) -> None:
        result = journey.sixteen_week_checkpoint({"stage_week_index": 16})
        self.assertTrue(result["checkpoint_reached"])
        self.assertEqual(set(result["paths"]), {"progress_toward_engaged", "continue_in_relationship", "part_ways"})


class ExitPathTests(JourneyTestCase):
    def setUp(self) -> None:
        super().setUp()
        self._enter_relationship(today="2026-01-01")
        journey.advance_stage(self.conn, "couple_1", True, True, today="2026-05-01")  # -> engaged

    def test_initiate_exit_records_stage_and_moves_users_to_exiting(self) -> None:
        record = journey.initiate_exit(self.conn, "exit_1", "couple_1", "u_a")
        self.assertEqual(record["stage_at_exit"], "engaged")
        self.assertEqual(record["status"], "interview")
        self.assertEqual(record["exit_interview_done"], 0)
        self.assertEqual(db.fetch_one(self.conn, "User", id="u_a")["journey_state"], "exiting")
        self.assertEqual(db.fetch_one(self.conn, "User", id="u_b")["journey_state"], "exiting")

    def test_feedback_rejected_before_interview_complete(self) -> None:
        journey.initiate_exit(self.conn, "exit_1", "couple_1", "u_a")
        with self.assertRaises(ValueError):
            journey.submit_feedback(self.conn, "exit_1", feedback_a_raw="x")

    def test_full_exit_flow_reaches_cooloff(self) -> None:
        journey.initiate_exit(self.conn, "exit_1", "couple_1", "u_a")
        journey.complete_exit_interview(self.conn, "exit_1")
        journey.submit_feedback(self.conn, "exit_1", feedback_a_raw="He never listened.", feedback_b_raw="She always ran late.")
        record = journey.synthesize_guru_feedback(self.conn, "exit_1", today="2026-06-01")
        self.assertEqual(record["status"], "cooloff")
        self.assertEqual(record["cooloff_ends"], "2026-06-15")  # default 14 days
        self.assertEqual(db.fetch_one(self.conn, "User", id="u_a")["journey_state"], "cooloff")

    def test_raw_feedback_never_appears_in_the_others_synthesis(self) -> None:
        journey.initiate_exit(self.conn, "exit_1", "couple_1", "u_a")
        journey.complete_exit_interview(self.conn, "exit_1")
        journey.submit_feedback(
            self.conn, "exit_1",
            feedback_a_raw="VERY SPECIFIC SECRET FROM A",
            feedback_b_raw="VERY SPECIFIC SECRET FROM B",
        )
        record = journey.synthesize_guru_feedback(self.conn, "exit_1", today="2026-06-01")
        self.assertNotIn("VERY SPECIFIC SECRET FROM A", record["guru_synthesis_for_a"] or "")
        self.assertNotIn("VERY SPECIFIC SECRET FROM A", record["guru_synthesis_for_b"] or "")
        self.assertNotIn("VERY SPECIFIC SECRET FROM B", record["guru_synthesis_for_a"] or "")
        self.assertNotIn("VERY SPECIFIC SECRET FROM B", record["guru_synthesis_for_b"] or "")
        # raw feedback itself is still stored (private input), just never echoed into a synthesis field
        self.assertEqual(record["feedback_a_raw"], "VERY SPECIFIC SECRET FROM A")

    def test_cooloff_days_must_be_within_mandated_range(self) -> None:
        journey.initiate_exit(self.conn, "exit_1", "couple_1", "u_a")
        journey.complete_exit_interview(self.conn, "exit_1")
        journey.submit_feedback(self.conn, "exit_1", feedback_a_raw="x")
        with self.assertRaises(ValueError):
            journey.synthesize_guru_feedback(self.conn, "exit_1", today="2026-06-01", cooloff_days=3)
        with self.assertRaises(ValueError):
            journey.synthesize_guru_feedback(self.conn, "exit_1", today="2026-06-01", cooloff_days=21)

    def _run_to_cooloff(self, cooloff_days: int = 14) -> None:
        journey.initiate_exit(self.conn, "exit_1", "couple_1", "u_a")
        journey.complete_exit_interview(self.conn, "exit_1")
        journey.submit_feedback(self.conn, "exit_1", feedback_a_raw="x", feedback_b_raw="y")
        journey.synthesize_guru_feedback(self.conn, "exit_1", today="2026-06-01", cooloff_days=cooloff_days)

    def test_reentry_blocked_before_cooloff_ends(self) -> None:
        self._run_to_cooloff(cooloff_days=14)
        for probe_date in ("2026-06-01", "2026-06-10", "2026-06-14"):
            result = journey.attempt_reentry(self.conn, "exit_1", today=probe_date)
            self.assertFalse(result["allowed"], probe_date)

    def test_reentry_allowed_exactly_on_cooloff_end_date(self) -> None:
        self._run_to_cooloff(cooloff_days=14)
        result = journey.attempt_reentry(self.conn, "exit_1", today="2026-06-15")
        self.assertTrue(result["allowed"])

    def test_reentry_allowed_after_cooloff_end_date(self) -> None:
        self._run_to_cooloff(cooloff_days=14)
        result = journey.attempt_reentry(self.conn, "exit_1", today="2026-07-01")
        self.assertTrue(result["allowed"])

    def test_successful_reentry_moves_users_to_reentry_state(self) -> None:
        self._run_to_cooloff(cooloff_days=7)
        journey.attempt_reentry(self.conn, "exit_1", today="2026-06-08")
        self.assertEqual(db.fetch_one(self.conn, "User", id="u_a")["journey_state"], "re-entry")
        self.assertEqual(db.fetch_one(self.conn, "User", id="u_b")["journey_state"], "re-entry")

    def test_check_cooloff_is_idempotent(self) -> None:
        self._run_to_cooloff(cooloff_days=7)
        first = journey.check_cooloff(self.conn, "exit_1", today="2026-06-10")
        second = journey.check_cooloff(self.conn, "exit_1", today="2026-06-10")
        self.assertEqual(first, second)
        self.assertEqual(db.fetch_one(self.conn, "Exit", id="exit_1")["status"], "complete")

    def test_data_layer_enforcement_ignores_out_of_order_calls(self) -> None:
        # Even if a caller skips straight to attempt_reentry with no
        # feedback/cooloff step ever run, it must not be silently allowed.
        journey.initiate_exit(self.conn, "exit_2", "couple_1", "u_a")
        result = journey.attempt_reentry(self.conn, "exit_2", today="2099-01-01")
        self.assertFalse(result["allowed"])


if __name__ == "__main__":
    unittest.main()
