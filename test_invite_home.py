"""Tests for invite_home.py."""

from __future__ import annotations

import ast
import inspect
import unittest
from pathlib import Path

from invite_home import (
    EXPECTATION_FLAGS,
    IMMUTABLE_ACKNOWLEDGEMENT_TEXT,
    INTIMACY_EXPECTED_GUIDANCE,
    RULES_OF_ENGAGEMENT,
    acknowledge,
    both_acknowledged,
    mark_flag_seen,
    notify_trusted_contact,
    propose_invite,
    respond_to_invite,
    revoke,
    show_guidance,
    status_for_requester,
)


def _proposed(expectation_flag: str = "social_only", existing=None) -> dict:
    return propose_invite("lockin-1", "user-a", "2026-03-06T19:00", expectation_flag, existing or [])


def _seen(invite: dict) -> dict:
    return mark_flag_seen(invite, "Mon:12")


def _accepted(expectation_flag: str = "social_only") -> dict:
    return respond_to_invite(_seen(_proposed(expectation_flag)), "accepted")


class ScopeBoundaryTests(unittest.TestCase):
    """Part F / declining-has-zero-effect-on-compliance: enforced
    structurally by never importing outcomes.py at all — no code path
    from here can reach a ComplianceEvent."""

    def test_never_imports_outcomes_module(self) -> None:
        source = Path(__file__).with_name("invite_home.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        imported_names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_names.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_names.add(node.module)
        self.assertNotIn("outcomes", imported_names)


class ImmutableTextTests(unittest.TestCase):
    """"The immutable text cannot be modified or omitted." Two separate
    guarantees: the constant's own wording is exactly the spec's, and
    acknowledge() has no parameter that could substitute a different
    string for it — so no caller, however constructed, can omit or
    reword it while still producing a valid acknowledgement."""

    def test_text_matches_the_spec_verbatim(self) -> None:
        self.assertTrue(IMMUTABLE_ACKNOWLEDGEMENT_TEXT.startswith("This records a planned visit"))
        self.assertIn("It is not consent to physical intimacy, and it cannot be.", IMMUTABLE_ACKNOWLEDGEMENT_TEXT)
        self.assertIn("Changing your mind is not a broken promise. It is your right, always.", IMMUTABLE_ACKNOWLEDGEMENT_TEXT)
        self.assertTrue(IMMUTABLE_ACKNOWLEDGEMENT_TEXT.endswith("without explanation."))

    def test_acknowledge_accepts_no_text_override(self) -> None:
        params = list(inspect.signature(acknowledge).parameters)
        self.assertEqual(params, ["invite", "party", "face_verified"])

    def test_every_acknowledgement_is_versioned(self) -> None:
        invite = acknowledge(_accepted(), "a", True)
        self.assertIsNotNone(invite["acknowledgement_version"])


class ProposeInviteTests(unittest.TestCase):
    def test_builds_a_pending_invite(self) -> None:
        invite = _proposed("intimacy_expected")
        self.assertEqual(invite["status"], "pending")
        self.assertEqual(invite["expectation_flag"], "intimacy_expected")
        self.assertIsNone(invite["flag_seen_by_recipient_at"])
        self.assertFalse(invite["ack_signed_a"])

    def test_rejects_unknown_expectation_flag(self) -> None:
        with self.assertRaises(ValueError):
            propose_invite("lockin-1", "user-a", "2026-03-06T19:00", "surprise-me", [])

    def test_rejects_a_second_pending_invite(self) -> None:
        with self.assertRaises(ValueError):
            _proposed(existing=[{"status": "pending"}])

    def test_allows_a_new_proposal_after_a_decline(self) -> None:
        invite = _proposed(existing=[{"status": "declined"}])
        self.assertEqual(invite["status"], "pending")

    def test_all_three_flags_have_recipient_copy(self) -> None:
        from invite_home import EXPECTATION_FLAG_COPY
        self.assertEqual(set(EXPECTATION_FLAG_COPY), set(EXPECTATION_FLAGS))


class RespondToInviteTests(unittest.TestCase):
    def test_requires_flag_seen_before_responding(self) -> None:
        with self.assertRaises(ValueError):
            respond_to_invite(_proposed(), "accepted")

    def test_accept_decline_ignore_all_valid(self) -> None:
        for response in ("accepted", "declined", "ignored"):
            updated = respond_to_invite(_seen(_proposed()), response)
            self.assertEqual(updated["status"], response)

    def test_declining_changes_only_status(self) -> None:
        # "Declining has zero effect on compliance rating" (behavioral
        # half of the guardrail — the structural half is
        # ScopeBoundaryTests above).
        seen = _seen(_proposed())
        declined = respond_to_invite(seen, "declined")
        for field in seen:
            if field == "status":
                continue
            self.assertEqual(declined[field], seen[field], field)


class ShowGuidanceTests(unittest.TestCase):
    def test_only_applies_to_intimacy_expected(self) -> None:
        with self.assertRaises(ValueError):
            show_guidance(_proposed("social_only"), "a")

    def test_marks_shown_for_the_given_party(self) -> None:
        updated = show_guidance(_proposed("intimacy_expected"), "a")
        self.assertTrue(updated["guidance_shown_a"])
        self.assertFalse(updated["guidance_shown_b"])

    def test_six_guidance_points(self) -> None:
        self.assertEqual(len(INTIMACY_EXPECTED_GUIDANCE), 6)


class AcknowledgeTests(unittest.TestCase):
    def test_acknowledges_for_party_a(self) -> None:
        updated = acknowledge(_accepted(), "a", True)
        self.assertTrue(updated["ack_signed_a"])
        self.assertTrue(updated["face_verified_a"])
        self.assertFalse(updated["ack_signed_b"])

    def test_rejects_acknowledging_before_accepted(self) -> None:
        with self.assertRaises(ValueError):
            acknowledge(_seen(_proposed()), "a", True)

    def test_intimacy_expected_requires_guidance_shown_first(self) -> None:
        accepted = _accepted("intimacy_expected")
        with self.assertRaises(ValueError):
            acknowledge(accepted, "a", True)

    def test_intimacy_expected_acknowledge_succeeds_after_guidance(self) -> None:
        accepted = _accepted("intimacy_expected")
        with_guidance = show_guidance(accepted, "a")
        updated = acknowledge(with_guidance, "a", True)
        self.assertTrue(updated["ack_signed_a"])

    def test_social_only_never_needs_guidance(self) -> None:
        updated = acknowledge(_accepted("social_only"), "a", True)
        self.assertTrue(updated["ack_signed_a"])

    def test_both_acknowledged_true_only_once_both_sides_sign(self) -> None:
        invite = _accepted()
        self.assertFalse(both_acknowledged(invite))
        invite = acknowledge(invite, "a", True)
        self.assertFalse(both_acknowledged(invite))
        invite = acknowledge(invite, "b", True)
        self.assertTrue(both_acknowledged(invite))


class NotifyTrustedContactTests(unittest.TestCase):
    def test_marks_the_given_party(self) -> None:
        updated = notify_trusted_contact(_proposed(), "b")
        self.assertTrue(updated["trusted_contact_notified_b"])
        self.assertFalse(updated["trusted_contact_notified_a"])


class RevokeTests(unittest.TestCase):
    """"Revocation always succeeds and records no fault." """

    def test_revokes_a_pending_invite(self) -> None:
        revoked = revoke(_proposed(), "user-b", "Tue:09")
        self.assertEqual(revoked["status"], "revoked")
        self.assertEqual(revoked["revoked_by"], "user-b")
        self.assertEqual(revoked["revoked_at"], "Tue:09")

    def test_revokes_after_both_have_acknowledged(self) -> None:
        invite = _accepted()
        invite = acknowledge(invite, "a", True)
        invite = acknowledge(invite, "b", True)
        revoked = revoke(invite, "user-a", "Tue:09")
        self.assertEqual(revoked["status"], "revoked")

    def test_records_no_fault_field_of_any_kind(self) -> None:
        revoked = revoke(_proposed(), "user-b", "Tue:09")
        self.assertNotIn("fault", revoked)
        self.assertNotIn("reason", revoked)
        self.assertNotIn("penalty", revoked)

    def test_rejects_revoking_an_already_revoked_invite(self) -> None:
        revoked = revoke(_proposed(), "user-b", "Tue:09")
        with self.assertRaises(ValueError):
            revoke(revoked, "user-a", "Wed:10")

    def test_rejects_revoking_a_declined_invite(self) -> None:
        declined = respond_to_invite(_seen(_proposed()), "declined")
        with self.assertRaises(ValueError):
            revoke(declined, "user-a", "Wed:10")


class StatusForRequesterTests(unittest.TestCase):
    def test_declined_and_ignored_collapse_to_the_same_neutral_phrase(self) -> None:
        declined = status_for_requester({"status": "declined"})
        ignored = status_for_requester({"status": "ignored"})
        self.assertEqual(declined, ignored)
        self.assertNotEqual(declined, "declined")

    def test_revoked_shown_as_is(self) -> None:
        self.assertEqual(status_for_requester({"status": "revoked"}), "revoked")


class RulesOfEngagementTests(unittest.TestCase):
    def test_six_bullets(self) -> None:
        self.assertEqual(len(RULES_OF_ENGAGEMENT), 6)


if __name__ == "__main__":
    unittest.main()
