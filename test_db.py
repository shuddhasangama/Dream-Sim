"""Tests for db.py / schema.sql.

Every entity table gets two tests: one proving a valid row is accepted, one
proving an invalid stage — or, for the few tables with no literal `stage`
column, their nearest analogous constrained field — is rejected.
"""

from __future__ import annotations

import sqlite3
import unittest

import db


class DreamSchemaTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.conn = db.get_connection(":memory:")
        db.init_db(self.conn)

    def tearDown(self) -> None:
        self.conn.close()

    # ── shared fixtures ────────────────────────────────────────────────

    def _make_user(self, user_id: str, journey_state: str = "dating") -> str:
        db.insert_row(self.conn, "User", {"id": user_id, "journey_state": journey_state})
        return user_id

    def _make_couple(self, couple_id: str = "couple-1", stage: str = "relationship") -> str:
        self._make_user("user-a")
        self._make_user("user-b")
        db.insert_row(
            self.conn,
            "Couple",
            {
                "id": couple_id,
                "partner_a_id": "user-a",
                "partner_b_id": "user-b",
                "stage": stage,
                "entered_via": "progression",
                "start_date": "2026-01-01",
            },
        )
        return couple_id

    def _make_lockin(self, lockin_id: str = "lockin-1") -> str:
        self._make_user("user-a")
        self._make_user("user-b")
        db.insert_row(
            self.conn,
            "LockIn",
            {"id": lockin_id, "user_a": "user-a", "user_b": "user-b", "week": 1, "created_at": "Mon:14"},
        )
        return lockin_id

    def _make_dateplan(self, dateplan_id: str = "plan-1") -> str:
        lid = self._make_lockin()
        db.insert_row(
            self.conn,
            "DatePlan",
            {
                "id": dateplan_id,
                "lockin_id": lid,
                "datetime": "2026-02-06T19:00",
                "meal": "dinner",
                "bill_split": "pay-your-own",
            },
        )
        return dateplan_id


class UserTests(DreamSchemaTestCase):
    def test_accepts_valid_row(self) -> None:
        self._make_user("u1", "dating")
        row = db.fetch_one(self.conn, "User", id="u1")
        self.assertIsNotNone(row)
        self.assertEqual(row["journey_state"], "dating")
        self.assertEqual(row["bgv_status"], "declared")  # default

    def test_rejects_invalid_journey_state(self) -> None:
        with self.assertRaises(sqlite3.IntegrityError):
            db.insert_row(self.conn, "User", {"id": "u2", "journey_state": "smitten"})


class CoupleTests(DreamSchemaTestCase):
    def test_accepts_valid_row(self) -> None:
        cid = self._make_couple(stage="engaged")
        row = db.fetch_one(self.conn, "Couple", id=cid)
        self.assertIsNotNone(row)
        self.assertEqual(row["stage"], "engaged")

    def test_rejects_invalid_stage(self) -> None:
        self._make_user("user-a")
        self._make_user("user-b")
        with self.assertRaises(sqlite3.IntegrityError):
            db.insert_row(
                self.conn,
                "Couple",
                {
                    "id": "bad-couple",
                    "partner_a_id": "user-a",
                    "partner_b_id": "user-b",
                    # invalid: a Couple record only exists post-Dating
                    "stage": "dating",
                    "entered_via": "progression",
                    "start_date": "2026-01-01",
                },
            )

    def test_rejects_same_partner_twice(self) -> None:
        self._make_user("solo")
        with self.assertRaises(sqlite3.IntegrityError):
            db.insert_row(
                self.conn,
                "Couple",
                {
                    "id": "bad-couple-2",
                    "partner_a_id": "solo",
                    "partner_b_id": "solo",
                    "stage": "relationship",
                    "entered_via": "progression",
                    "start_date": "2026-01-01",
                },
            )


class RoadProfileTests(DreamSchemaTestCase):
    def test_accepts_valid_row(self) -> None:
        cid = self._make_couple()
        db.insert_row(
            self.conn,
            "RoadProfile",
            {
                "id": "road-1",
                "user_id": "user-a",
                "couple_id": cid,
                "routine_json": db.json_field(
                    [
                        {"id": "b1", "category": "work", "days": ["Mon", "Wed"], "label": "Office", "start": "09:00", "end": "18:00"},
                        {"id": "b2", "category": "fitness", "days": ["Tue"], "label": "Yoga", "start": "19:30", "end": "20:30"},
                    ]
                ),
                "availability_json": "[]",
            },
        )
        row = db.fetch_one(self.conn, "RoadProfile", id="road-1")
        self.assertIsNotNone(row)
        self.assertEqual(row["couple_id"], cid)
        self.assertEqual(db.load_json_field(row["routine_json"])[0]["label"], "Office")

    def test_rejects_unknown_couple(self) -> None:
        # RoadProfile has no stage/enum column of its own (the brief only
        # gives it user_id/couple_id/routine); its integrity check is the FK.
        self._make_user("user-a")
        with self.assertRaises(sqlite3.IntegrityError):
            db.insert_row(
                self.conn,
                "RoadProfile",
                {"id": "road-2", "user_id": "user-a", "couple_id": "no-such-couple"},
            )


class CalendarEntryTests(DreamSchemaTestCase):
    def test_accepts_valid_row(self) -> None:
        cid = self._make_couple()
        db.insert_row(
            self.conn,
            "CalendarEntry",
            {
                "id": "cal-1",
                "couple_id": cid,
                "owner_id": "user-a",
                "type": "date",
                "starts_at": "2026-02-14T19:00",
                "ends_at": "2026-02-14T21:00",
                "title": "Dinner",
                "shared": 1,
            },
        )
        row = db.fetch_one(self.conn, "CalendarEntry", id="cal-1")
        self.assertIsNotNone(row)
        self.assertEqual(row["type"], "date")

    def test_rejects_invalid_type(self) -> None:
        cid = self._make_couple()
        with self.assertRaises(sqlite3.IntegrityError):
            db.insert_row(
                self.conn,
                "CalendarEntry",
                {
                    "id": "cal-2",
                    "couple_id": cid,
                    "owner_id": "user-a",
                    "type": "vibe-check",  # not availability/obligation/date/travel
                    "starts_at": "2026-02-14T19:00",
                    "ends_at": "2026-02-14T21:00",
                },
            )

    def test_rejects_travel_without_travel_mode(self) -> None:
        cid = self._make_couple()
        with self.assertRaises(sqlite3.IntegrityError):
            db.insert_row(
                self.conn,
                "CalendarEntry",
                {
                    "id": "cal-3",
                    "couple_id": cid,
                    "owner_id": "user-a",
                    "type": "travel",
                    "starts_at": "2026-03-01",
                    "ends_at": "2026-03-05",
                },
            )


class PlaybookTests(DreamSchemaTestCase):
    def test_accepts_valid_row(self) -> None:
        cid = self._make_couple(stage="relationship")
        db.insert_row(
            self.conn,
            "Playbook",
            {
                "id": "pb-1",
                "couple_id": cid,
                "stage": "relationship",
                "tier_generic_json": db.json_field(["greet by name", "phones down"]),
            },
        )
        row = db.fetch_one(self.conn, "Playbook", id="pb-1")
        self.assertIsNotNone(row)
        self.assertEqual(
            db.load_json_field(row["tier_generic_json"]), ["greet by name", "phones down"]
        )

    def test_rejects_invalid_stage(self) -> None:
        cid = self._make_couple()
        with self.assertRaises(sqlite3.IntegrityError):
            db.insert_row(
                self.conn, "Playbook", {"id": "pb-2", "couple_id": cid, "stage": "situationship"}
            )


class DifferenceTests(DreamSchemaTestCase):
    def test_accepts_valid_row(self) -> None:
        cid = self._make_couple()
        db.insert_row(
            self.conn,
            "Difference",
            {
                "id": "diff-1",
                "couple_id": cid,
                "raised_by": "user-a",
                "text": "We disagree on how often to visit in-laws",
                "tag": "family",
                "week_raised": 3,
            },
        )
        row = db.fetch_one(self.conn, "Difference", id="diff-1")
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "open")  # default

    def test_rejects_invalid_status(self) -> None:
        # Difference has no stage column in the brief; status is its nearest
        # constrained field (mirrors WeeklyReport's sorted[]/open[] buckets).
        cid = self._make_couple()
        with self.assertRaises(sqlite3.IntegrityError):
            db.insert_row(
                self.conn,
                "Difference",
                {
                    "id": "diff-2",
                    "couple_id": cid,
                    "raised_by": "user-a",
                    "text": "...",
                    "status": "ignored",
                    "week_raised": 3,
                },
            )


class GuruTopicTests(DreamSchemaTestCase):
    def test_accepts_valid_row(self) -> None:
        cid = self._make_couple(stage="engaged")
        db.insert_row(
            self.conn,
            "GuruTopic",
            {"id": "topic-1", "couple_id": cid, "stage": "engaged", "kind": "stage_topic", "topic_key": "festivals"},
        )
        row = db.fetch_one(self.conn, "GuruTopic", id="topic-1")
        self.assertIsNotNone(row)
        self.assertEqual(row["topic_key"], "festivals")

    def test_rejects_invalid_stage(self) -> None:
        cid = self._make_couple()
        with self.assertRaises(sqlite3.IntegrityError):
            db.insert_row(
                self.conn,
                "GuruTopic",
                {
                    "id": "topic-2",
                    "couple_id": cid,
                    "stage": "honeymoon-phase",
                    "kind": "pillar",
                    "topic_key": "romance",
                },
            )


class WeeklyReportTests(DreamSchemaTestCase):
    def test_accepts_valid_row(self) -> None:
        cid = self._make_couple()
        db.insert_row(
            self.conn,
            "WeeklyReport",
            {"id": "wr-1", "couple_id": cid, "stage": "relationship", "week_index": 1},
        )
        row = db.fetch_one(self.conn, "WeeklyReport", id="wr-1")
        self.assertIsNotNone(row)
        self.assertEqual(row["expense_compliant"], 1)  # default

    def test_rejects_invalid_stage(self) -> None:
        cid = self._make_couple()
        with self.assertRaises(sqlite3.IntegrityError):
            db.insert_row(
                self.conn,
                "WeeklyReport",
                {"id": "wr-2", "couple_id": cid, "stage": "forever", "week_index": 1},
            )


class ExitTests(DreamSchemaTestCase):
    def test_accepts_valid_row(self) -> None:
        cid = self._make_couple(stage="engaged")
        db.insert_row(
            self.conn,
            "Exit",
            {
                "id": "exit-1",
                "couple_id": cid,
                "initiated_by": "user-a",
                "stage_at_exit": "engaged",
                "cooloff_ends": "2026-03-01",
            },
        )
        row = db.fetch_one(self.conn, "Exit", id="exit-1")
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "interview")  # default

    def test_rejects_invalid_stage(self) -> None:
        cid = self._make_couple()
        with self.assertRaises(sqlite3.IntegrityError):
            db.insert_row(
                self.conn,
                "Exit",
                {
                    "id": "exit-2",
                    "couple_id": cid,
                    "initiated_by": "user-a",
                    "stage_at_exit": "situationship",
                },
            )


class InviteTests(DreamSchemaTestCase):
    def test_accepts_valid_row(self) -> None:
        self._make_user("inviter")
        db.insert_row(
            self.conn,
            "Invite",
            {
                "id": "inv-1",
                "from_user_id": "inviter",
                "to_contact": "partner@example.com",
                "mode": "start_together",
                "target_stage": "married",
            },
        )
        row = db.fetch_one(self.conn, "Invite", id="inv-1")
        self.assertIsNotNone(row)
        self.assertEqual(row["target_stage"], "married")

    def test_accepts_join_pool_with_null_stage(self) -> None:
        self._make_user("inviter2")
        db.insert_row(
            self.conn,
            "Invite",
            {
                "id": "inv-2",
                "from_user_id": "inviter2",
                "to_contact": "someone@example.com",
                "mode": "join_pool",
                "target_stage": None,
            },
        )
        row = db.fetch_one(self.conn, "Invite", id="inv-2")
        self.assertIsNone(row["target_stage"])

    def test_rejects_invalid_target_stage(self) -> None:
        self._make_user("inviter3")
        with self.assertRaises(sqlite3.IntegrityError):
            db.insert_row(
                self.conn,
                "Invite",
                {
                    "id": "inv-3",
                    "from_user_id": "inviter3",
                    "to_contact": "x@example.com",
                    "mode": "start_together",
                    "target_stage": "honeymoon",
                },
            )


class MatchTests(DreamSchemaTestCase):
    def test_accepts_valid_row(self) -> None:
        self._make_user("user-a")
        self._make_user("user-b")
        db.insert_row(
            self.conn,
            "Match",
            {
                "id": "match-1",
                "user_id": "user-a",
                "candidate_id": "user-b",
                "week": 1,
                "slot": 1,
                "revealed_at": "Mon:12",
                "window_closes_at": "Tue:12",
            },
        )
        row = db.fetch_one(self.conn, "Match", id="match-1")
        self.assertIsNotNone(row)
        self.assertEqual(row["action"], "none")  # default

    def test_rejects_invalid_slot(self) -> None:
        self._make_user("user-a")
        self._make_user("user-b")
        with self.assertRaises(sqlite3.IntegrityError):
            db.insert_row(
                self.conn,
                "Match",
                {
                    "id": "match-2",
                    "user_id": "user-a",
                    "candidate_id": "user-b",
                    "week": 1,
                    "slot": 4,  # only 1/2/3 exist
                    "revealed_at": "Mon:12",
                    "window_closes_at": "Tue:12",
                },
            )

    def test_rejects_self_match(self) -> None:
        self._make_user("user-a")
        with self.assertRaises(sqlite3.IntegrityError):
            db.insert_row(
                self.conn,
                "Match",
                {
                    "id": "match-3",
                    "user_id": "user-a",
                    "candidate_id": "user-a",
                    "week": 1,
                    "slot": 1,
                    "revealed_at": "Mon:12",
                    "window_closes_at": "Tue:12",
                },
            )


class LockInTests(DreamSchemaTestCase):
    def test_accepts_valid_row(self) -> None:
        lid = self._make_lockin()
        row = db.fetch_one(self.conn, "LockIn", id=lid)
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "active")  # default
        self.assertEqual(row["dates_completed"], 0)  # default

    def test_rejects_invalid_status(self) -> None:
        self._make_user("user-a")
        self._make_user("user-b")
        with self.assertRaises(sqlite3.IntegrityError):
            db.insert_row(
                self.conn,
                "LockIn",
                {"id": "lockin-2", "user_a": "user-a", "user_b": "user-b", "week": 1, "created_at": "Mon:14", "status": "pending"},
            )

    def test_rejects_self_lockin(self) -> None:
        self._make_user("user-a")
        with self.assertRaises(sqlite3.IntegrityError):
            db.insert_row(
                self.conn,
                "LockIn",
                {"id": "lockin-3", "user_a": "user-a", "user_b": "user-a", "week": 1, "created_at": "Mon:14"},
            )


class AvailabilityTests(DreamSchemaTestCase):
    def test_accepts_valid_row(self) -> None:
        lid = self._make_lockin()
        db.insert_row(
            self.conn,
            "Availability",
            {"id": "avail-1", "lockin_id": lid, "user_id": "user-a", "day": "Sat", "meal_slot": "dinner"},
        )
        row = db.fetch_one(self.conn, "Availability", id="avail-1")
        self.assertIsNotNone(row)
        self.assertEqual(row["meal_slot"], "dinner")

    def test_rejects_invalid_meal_slot(self) -> None:
        lid = self._make_lockin()
        with self.assertRaises(sqlite3.IntegrityError):
            db.insert_row(
                self.conn,
                "Availability",
                {"id": "avail-2", "lockin_id": lid, "user_id": "user-a", "day": "Sat", "meal_slot": "brunch"},
            )

    def test_rejects_friday_breakfast(self) -> None:
        # Friday is a working day — only Coffee and Dinner slots exist (§5).
        lid = self._make_lockin()
        with self.assertRaises(sqlite3.IntegrityError):
            db.insert_row(
                self.conn,
                "Availability",
                {"id": "avail-3", "lockin_id": lid, "user_id": "user-a", "day": "Fri", "meal_slot": "breakfast"},
            )


class DatePlanTests(DreamSchemaTestCase):
    def test_accepts_valid_row(self) -> None:
        pid = self._make_dateplan()
        row = db.fetch_one(self.conn, "DatePlan", id=pid)
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "pending_signatures")  # default

    def test_rejects_invalid_bill_split(self) -> None:
        lid = self._make_lockin()
        with self.assertRaises(sqlite3.IntegrityError):
            db.insert_row(
                self.conn,
                "DatePlan",
                {
                    "id": "plan-2",
                    "lockin_id": lid,
                    "datetime": "2026-02-06T19:00",
                    "meal": "dinner",
                    "bill_split": "even-steven",  # not a real option
                },
            )


class SignatureTests(DreamSchemaTestCase):
    def test_accepts_valid_row(self) -> None:
        pid = self._make_dateplan()
        db.insert_row(
            self.conn,
            "Signature",
            {
                "id": "sig-1",
                "dateplan_id": pid,
                "user_id": "user-a",
                "signed_at": "Thu:19",
                "face_verified": 1,
                "ack_conduct": 1,
                "ack_cancellation": 1,
                "ack_not_a_relationship": 1,
                "ack_liability": 1,
            },
        )
        row = db.fetch_one(self.conn, "Signature", id="sig-1")
        self.assertIsNotNone(row)
        self.assertEqual(row["face_verified"], 1)

    def test_rejects_missing_face_verified(self) -> None:
        pid = self._make_dateplan()
        with self.assertRaises(sqlite3.IntegrityError):
            db.insert_row(
                self.conn,
                "Signature",
                {"id": "sig-2", "dateplan_id": pid, "user_id": "user-a", "signed_at": "Thu:19"},
            )


class DateOutcomeTests(DreamSchemaTestCase):
    def test_accepts_valid_row(self) -> None:
        pid = self._make_dateplan()
        db.insert_row(
            self.conn,
            "DateOutcome",
            {"id": "outcome-1", "dateplan_id": pid, "happened": 1, "a_decision": "continue", "b_decision": "continue"},
        )
        row = db.fetch_one(self.conn, "DateOutcome", id="outcome-1")
        self.assertIsNotNone(row)
        self.assertEqual(row["together_photo"], 0)  # default — consent-gated, off by default

    def test_rejects_invalid_decision(self) -> None:
        pid = self._make_dateplan()
        with self.assertRaises(sqlite3.IntegrityError):
            db.insert_row(
                self.conn,
                "DateOutcome",
                {"id": "outcome-2", "dateplan_id": pid, "happened": 1, "a_decision": "maybe-later"},
            )

    def test_accepts_relationship_decision(self) -> None:
        pid = self._make_dateplan()
        db.insert_row(
            self.conn,
            "DateOutcome",
            {"id": "outcome-3", "dateplan_id": pid, "happened": 1, "a_decision": "relationship", "b_decision": "relationship"},
        )
        row = db.fetch_one(self.conn, "DateOutcome", id="outcome-3")
        self.assertEqual(row["a_decision"], "relationship")


class ComplianceEventTests(DreamSchemaTestCase):
    def test_accepts_valid_row(self) -> None:
        self._make_user("user-a")
        db.insert_row(
            self.conn,
            "ComplianceEvent",
            {"id": "ce-1", "user_id": "user-a", "type": "no_show", "week": 3, "notes": "missed Saturday dinner"},
        )
        row = db.fetch_one(self.conn, "ComplianceEvent", id="ce-1")
        self.assertIsNotNone(row)
        self.assertEqual(row["type"], "no_show")

    def test_rejects_invalid_type(self) -> None:
        self._make_user("user-a")
        with self.assertRaises(sqlite3.IntegrityError):
            db.insert_row(
                self.conn,
                "ComplianceEvent",
                {"id": "ce-2", "user_id": "user-a", "type": "vibe-mismatch", "week": 3},
            )


class ContactRequestTests(DreamSchemaTestCase):
    def test_accepts_valid_row(self) -> None:
        lid = self._make_lockin()
        db.insert_row(
            self.conn,
            "ContactRequest",
            {
                "id": "cr-1",
                "pair_id": lid,
                "requester_id": "user-a",
                "channel": "phone",
                "week": 3,
                "requested_at": "Mon:12",
            },
        )
        row = db.fetch_one(self.conn, "ContactRequest", id="cr-1")
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "pending")  # default

    def test_rejects_invalid_channel(self) -> None:
        lid = self._make_lockin()
        with self.assertRaises(sqlite3.IntegrityError):
            db.insert_row(
                self.conn,
                "ContactRequest",
                {
                    "id": "cr-2",
                    "pair_id": lid,
                    "requester_id": "user-a",
                    "channel": "telegram",  # not a real option
                    "week": 3,
                    "requested_at": "Mon:12",
                },
            )


class HomeInviteTests(DreamSchemaTestCase):
    def test_accepts_valid_row(self) -> None:
        lid = self._make_lockin()
        db.insert_row(
            self.conn,
            "HomeInvite",
            {
                "id": "hi-1",
                "pair_id": lid,
                "requester_id": "user-a",
                "proposed_datetime": "2026-02-06T19:00",
                "expectation_flag": "social_only",
            },
        )
        row = db.fetch_one(self.conn, "HomeInvite", id="hi-1")
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "pending")  # default
        self.assertEqual(row["ack_signed_a"], 0)  # default

    def test_rejects_invalid_expectation_flag(self) -> None:
        lid = self._make_lockin()
        with self.assertRaises(sqlite3.IntegrityError):
            db.insert_row(
                self.conn,
                "HomeInvite",
                {
                    "id": "hi-3",
                    "pair_id": lid,
                    "requester_id": "user-a",
                    "proposed_datetime": "2026-02-06T19:00",
                    "expectation_flag": "surprise-me",  # not a real option
                },
            )

    def test_rejects_invalid_status(self) -> None:
        lid = self._make_lockin()
        with self.assertRaises(sqlite3.IntegrityError):
            db.insert_row(
                self.conn,
                "HomeInvite",
                {
                    "id": "hi-2",
                    "pair_id": lid,
                    "requester_id": "user-a",
                    "proposed_datetime": "2026-02-06T19:00",
                    "expectation_flag": "social_only",
                    "status": "maybe-later",  # not a real option
                },
            )


class StageGateTests(DreamSchemaTestCase):
    def test_accepts_valid_row(self) -> None:
        lid = self._make_lockin()
        db.insert_row(self.conn, "StageGate", {"id": "sg-1", "pair_id": lid, "trigger": "exclusivity_raised", "opened_at": "Mon:12"})
        row = db.fetch_one(self.conn, "StageGate", id="sg-1")
        self.assertIsNotNone(row)
        self.assertEqual(row["status"], "open")  # default

    def test_rejects_invalid_trigger(self) -> None:
        lid = self._make_lockin()
        with self.assertRaises(sqlite3.IntegrityError):
            db.insert_row(self.conn, "StageGate", {"id": "sg-2", "pair_id": lid, "trigger": "curiosity", "opened_at": "Mon:12"})


class GateResponseTests(DreamSchemaTestCase):
    def test_accepts_valid_row(self) -> None:
        lid = self._make_lockin()
        db.insert_row(
            self.conn, "GateResponse",
            {"id": "gr-1", "pair_id": lid, "user_id": "user-a", "question_key": "open_question", "answer_text": "Do they want kids?"},
        )
        row = db.fetch_one(self.conn, "GateResponse", id="gr-1")
        self.assertIsNotNone(row)
        self.assertEqual(row["answer_text"], "Do they want kids?")

    def test_a_second_response_id_for_the_same_question_replaces_not_duplicates(self) -> None:
        # db.insert_row is INSERT OR REPLACE — a UNIQUE collision (here,
        # the same pair_id/user_id/question_key under a different row id)
        # overwrites in place rather than raising, same as every other
        # UNIQUE-constrained table in this schema.
        lid = self._make_lockin()
        db.insert_row(self.conn, "GateResponse", {"id": "gr-2", "pair_id": lid, "user_id": "user-a", "question_key": "money_talk", "answer_text": "first"})
        db.insert_row(self.conn, "GateResponse", {"id": "gr-3", "pair_id": lid, "user_id": "user-a", "question_key": "money_talk", "answer_text": "second"})
        rows = db.fetch_all(self.conn, "GateResponse", pair_id=lid, user_id="user-a", question_key="money_talk")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["answer_text"], "second")


class GateAnalysisTests(DreamSchemaTestCase):
    def test_accepts_valid_row(self) -> None:
        lid = self._make_lockin()
        db.insert_row(self.conn, "GateAnalysis", {"id": "ga-1", "pair_id": lid})
        row = db.fetch_one(self.conn, "GateAnalysis", id="ga-1")
        self.assertIsNotNone(row)
        self.assertEqual(row["divergences_json"], "[]")  # default


class VisionEntryTests(DreamSchemaTestCase):
    def test_accepts_valid_row(self) -> None:
        self._make_user("user-a")
        db.insert_row(
            self.conn, "VisionEntry",
            {"id": "ve-1", "user_id": "user-a", "element_key": "children", "detail_text": "wants children", "added_at": "2026-03-01"},
        )
        row = db.fetch_one(self.conn, "VisionEntry", id="ve-1")
        self.assertIsNotNone(row)
        self.assertIsNone(row["parent_id"])

    def test_chains_to_a_parent_entry(self) -> None:
        self._make_user("user-a")
        db.insert_row(
            self.conn, "VisionEntry",
            {"id": "ve-2", "user_id": "user-a", "element_key": "children", "detail_text": "wants children", "added_at": "2026-03-01"},
        )
        db.insert_row(
            self.conn, "VisionEntry",
            {"id": "ve-3", "user_id": "user-a", "element_key": "children", "detail_text": "2 kids", "added_at": "2026-03-15", "parent_id": "ve-2"},
        )
        row = db.fetch_one(self.conn, "VisionEntry", id="ve-3")
        self.assertEqual(row["parent_id"], "ve-2")


class VisionChangeTests(DreamSchemaTestCase):
    def test_accepts_a_disclosed_change(self) -> None:
        self._make_user("user-a")
        db.insert_row(
            self.conn, "VisionChange",
            {
                "id": "vc-1", "user_id": "user-a", "element_key": "children",
                "from_value": "wants children", "to_value": "does not want children",
                "declared_at": "2026-03-01", "disclosed_to_partner": 1,
            },
        )
        row = db.fetch_one(self.conn, "VisionChange", id="vc-1")
        self.assertIsNotNone(row)

    def test_rejects_an_undisclosed_change(self) -> None:
        self._make_user("user-a")
        with self.assertRaises(sqlite3.IntegrityError):
            db.insert_row(
                self.conn, "VisionChange",
                {
                    "id": "vc-2", "user_id": "user-a", "element_key": "children",
                    "from_value": "wants children", "to_value": "does not want children",
                    "declared_at": "2026-03-01", "disclosed_to_partner": 0,
                },
            )


class ChemistryEntryTests(DreamSchemaTestCase):
    def test_accepts_valid_row(self) -> None:
        self._make_user("user-a")
        db.insert_row(
            self.conn, "ChemistryEntry",
            {"id": "ce-chem-1", "user_id": "user-a", "key": "love_language", "value": "words of affirmation", "updated_at": "2026-03-01"},
        )
        row = db.fetch_one(self.conn, "ChemistryEntry", id="ce-chem-1")
        self.assertIsNotNone(row)

    def test_a_second_entry_id_for_the_same_key_replaces_not_duplicates(self) -> None:
        # Same INSERT OR REPLACE semantics as GateResponse above.
        self._make_user("user-a")
        db.insert_row(self.conn, "ChemistryEntry", {"id": "ce-chem-2", "user_id": "user-a", "key": "love_language", "value": "a", "updated_at": "2026-03-01"})
        db.insert_row(self.conn, "ChemistryEntry", {"id": "ce-chem-3", "user_id": "user-a", "key": "love_language", "value": "b", "updated_at": "2026-03-02"})
        rows = db.fetch_all(self.conn, "ChemistryEntry", user_id="user-a", key="love_language")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["value"], "b")


class CouplePartnershipVisionIdTests(DreamSchemaTestCase):
    def test_defaults_to_null_and_can_be_set(self) -> None:
        cid = self._make_couple()
        self.assertIsNone(db.fetch_one(self.conn, "Couple", id=cid)["partnership_vision_id"])
        couple = dict(db.fetch_one(self.conn, "Couple", id=cid))
        couple["partnership_vision_id"] = f"{cid}:vision"
        db.insert_row(self.conn, "Couple", couple)
        self.assertEqual(db.fetch_one(self.conn, "Couple", id=cid)["partnership_vision_id"], f"{cid}:vision")


class NextLevelThreadTests(DreamSchemaTestCase):
    def test_accepts_valid_row(self) -> None:
        lid = self._make_lockin()
        db.insert_row(
            self.conn, "NextLevelThread",
            {"id": "nl-1", "pair_id": lid, "opened_by": "user", "question_key": "pace_from_here", "opened_at": "Mon:12"},
        )
        row = db.fetch_one(self.conn, "NextLevelThread", id="nl-1")
        self.assertIsNotNone(row)
        self.assertEqual(row["declined_a"], 0)  # default
        self.assertIsNone(row["reluctance_flagged_to"])

    def test_rejects_invalid_opened_by(self) -> None:
        lid = self._make_lockin()
        with self.assertRaises(sqlite3.IntegrityError):
            db.insert_row(
                self.conn, "NextLevelThread",
                {"id": "nl-2", "pair_id": lid, "opened_by": "curiosity", "question_key": "pace_from_here", "opened_at": "Mon:12"},
            )

    def test_rejects_invalid_reluctance_flagged_to(self) -> None:
        lid = self._make_lockin()
        with self.assertRaises(sqlite3.IntegrityError):
            db.insert_row(
                self.conn, "NextLevelThread",
                {
                    "id": "nl-3", "pair_id": lid, "opened_by": "user", "question_key": "reluctance_check",
                    "opened_at": "Mon:12", "reluctance_flagged_to": "both",
                },
            )


class GuardrailTests(DreamSchemaTestCase):
    """DTD-XCT-001 (no skin-tone classification anywhere) — a schema check
    that fails the build if a future field adds one. Scans the live
    schema via PRAGMA, not just this file's text, so it catches additions
    to schema.sql automatically."""

    FORBIDDEN_SUBSTRINGS = ("appearance", "skin", "complexion", "race", "ethnic")

    def test_no_appearance_or_skin_tone_columns(self) -> None:
        tables = [
            r["name"]
            for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        ]
        offending = []
        for table in tables:
            for row in self.conn.execute(f"PRAGMA table_info({table})"):
                col = row["name"].lower()
                if any(bad in col for bad in self.FORBIDDEN_SUBSTRINGS):
                    offending.append(f"{table}.{row['name']}")
        self.assertEqual(offending, [], f"Forbidden columns found: {offending}")


if __name__ == "__main__":
    unittest.main()
