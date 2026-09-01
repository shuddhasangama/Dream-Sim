"""Tests for escalations.py. (Its original HomeInvite coverage moved to
test_invite_home.py on 2026-08-28 when that flow was rebuilt.)"""

from __future__ import annotations

import ast
import unittest
from pathlib import Path

from escalations import (
    CONTACT_CHANNELS,
    WEEK_2_DATES_REQUIRED,
    contact_status_for_requester,
    request_contact,
    respond_to_contact_request,
    unlocks_available,
)


class ScopeBoundaryTests(unittest.TestCase):
    """Part F: declining/ignoring has zero consequence — no rating, no
    flag. Enforced structurally: this module must never import
    outcomes.py (the only place a ComplianceEvent could originate) or
    anything compliance-related, so there's no code path from here to a
    rating effect at all."""

    def test_never_imports_outcomes_module(self) -> None:
        source = Path(__file__).with_name("escalations.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_names.add(node.module)
        self.assertNotIn("outcomes", imported_names)


class UnlocksAvailableTests(unittest.TestCase):
    def test_zero_dates_not_unlocked(self) -> None:
        self.assertFalse(unlocks_available(0))

    def test_one_date_not_unlocked(self) -> None:
        self.assertFalse(unlocks_available(1))

    def test_two_dates_unlocked(self) -> None:
        self.assertTrue(unlocks_available(WEEK_2_DATES_REQUIRED))

    def test_more_than_two_still_unlocked(self) -> None:
        self.assertTrue(unlocks_available(5))


class RequestContactTests(unittest.TestCase):
    def test_builds_a_pending_request(self) -> None:
        row = request_contact("lockin-1", "user-a", "phone", week=3, requested_at="Mon:12", existing_requests=[])
        self.assertEqual(row["status"], "pending")
        self.assertEqual(row["channel"], "phone")
        self.assertIsNone(row["responded_at"])

    def test_rejects_unknown_channel(self) -> None:
        with self.assertRaises(ValueError):
            request_contact("lockin-1", "user-a", "telegram", week=3, requested_at="Mon:12", existing_requests=[])

    def test_rejects_second_request_same_channel_same_week(self) -> None:
        existing = [{"channel": "phone", "week": 3}]
        with self.assertRaises(ValueError):
            request_contact("lockin-1", "user-a", "phone", week=3, requested_at="Mon:12", existing_requests=existing)

    def test_allows_same_channel_a_different_week(self) -> None:
        existing = [{"channel": "phone", "week": 3}]
        row = request_contact("lockin-1", "user-a", "phone", week=4, requested_at="Mon:12", existing_requests=existing)
        self.assertEqual(row["week"], 4)

    def test_allows_a_different_channel_same_week(self) -> None:
        existing = [{"channel": "phone", "week": 3}]
        row = request_contact("lockin-1", "user-a", "instagram", week=3, requested_at="Mon:12", existing_requests=existing)
        self.assertEqual(row["channel"], "instagram")


class RespondToContactRequestTests(unittest.TestCase):
    def _pending(self) -> dict:
        return request_contact("lockin-1", "user-a", "phone", week=3, requested_at="Mon:12", existing_requests=[])

    def test_accepted(self) -> None:
        updated = respond_to_contact_request(self._pending(), "accepted", "Tue:09")
        self.assertEqual(updated["status"], "accepted")
        self.assertEqual(updated["responded_at"], "Tue:09")

    def test_declined_is_a_valid_response(self) -> None:
        updated = respond_to_contact_request(self._pending(), "declined", "Tue:09")
        self.assertEqual(updated["status"], "declined")

    def test_ignored_is_a_valid_response(self) -> None:
        updated = respond_to_contact_request(self._pending(), "ignored", "Tue:09")
        self.assertEqual(updated["status"], "ignored")

    def test_rejects_unknown_response(self) -> None:
        with self.assertRaises(ValueError):
            respond_to_contact_request(self._pending(), "maybe", "Tue:09")

    def test_does_not_mutate_input(self) -> None:
        request = self._pending()
        respond_to_contact_request(request, "declined", "Tue:09")
        self.assertEqual(request["status"], "pending")


class ContactStatusForRequesterTests(unittest.TestCase):
    def test_accepted_shows_shared(self) -> None:
        self.assertEqual(contact_status_for_requester({"status": "accepted"}), "shared")

    def test_declined_looks_the_same_as_pending(self) -> None:
        pending = contact_status_for_requester({"status": "pending"})
        declined = contact_status_for_requester({"status": "declined"})
        self.assertEqual(pending, declined)

    def test_ignored_looks_the_same_as_pending(self) -> None:
        pending = contact_status_for_requester({"status": "pending"})
        ignored = contact_status_for_requester({"status": "ignored"})
        self.assertEqual(pending, ignored)

    def test_all_channels_are_the_expected_set(self) -> None:
        self.assertEqual(set(CONTACT_CHANNELS), {"phone", "whatsapp", "instagram", "linkedin"})


if __name__ == "__main__":
    unittest.main()
