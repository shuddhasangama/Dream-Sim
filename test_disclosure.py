"""Tests for disclosure.py — what is open to a user, and when.

Two things depend on this and both are easy to get subtly wrong:

  * TIMING. Intimacy expectations must not be askable before two people
    have met, and a physical-boundary preference must not be askable
    before there is a date to have one at. A leak here is not a cosmetic
    bug — it produces answers people did not mean to give.
  * NAVIGATION. Eleven links, most meaningless before a match, is the
    thing being fixed. These pin the counts so it cannot creep back.
"""

from __future__ import annotations

import unittest

import disclosure as d


def reached(**kwargs):
    base = {"bgv_status": "declared", "journey_state": "onboarding"}
    return d.milestones_for(**{**base, **kwargs})


JUST_REGISTERED = reached()
VERIFIED = reached(bgv_status="verified", journey_state="dating")
MATCHED = reached(bgv_status="verified", journey_state="dating", has_active_lockin=True)
DATE_SET = reached(bgv_status="verified", journey_state="dating",
                   has_active_lockin=True, has_dateplan=True)
AFTER_DATE = reached(bgv_status="verified", journey_state="dating", has_active_lockin=True,
                     has_dateplan=True, has_date_outcome=True)
IN_RELATIONSHIP = reached(bgv_status="verified", journey_state="relationship")


class MilestoneTests(unittest.TestCase):
    def test_everyone_signed_in_is_at_least_registered(self):
        self.assertIn(d.REGISTERED, JUST_REGISTERED)

    def test_an_unverified_user_has_reached_nothing_else(self):
        self.assertEqual(JUST_REGISTERED, {d.REGISTERED})

    def test_each_fact_advances_exactly_as_far_as_it_should(self):
        self.assertEqual(VERIFIED, {d.REGISTERED, d.VERIFIED})
        self.assertEqual(MATCHED, {d.REGISTERED, d.VERIFIED, d.MATCHED})
        self.assertEqual(DATE_SET, {d.REGISTERED, d.VERIFIED, d.MATCHED, d.DATE_SET})

    def test_milestones_are_upward_closed(self):
        """A user in the Relationship stage has plainly had a first date
        even if the outcome row is missing. Reading that literally would
        hide the very screens they need."""
        self.assertEqual(IN_RELATIONSHIP, set(d.ORDER))

    def test_a_late_state_backfills_the_ones_skipped(self):
        engaged = reached(bgv_status="verified", journey_state="engaged")
        for milestone in d.ORDER:
            self.assertIn(milestone, engaged, milestone)


class TimingTests(unittest.TestCase):
    """The rules the product actually cares about."""

    def test_boundaries_are_shut_until_a_date_is_set(self):
        for stage in (JUST_REGISTERED, VERIFIED, MATCHED):
            self.assertFalse(d.is_open("boundaries", stage))
        self.assertTrue(d.is_open("boundaries", DATE_SET))

    def test_expectations_are_shut_until_after_the_first_date(self):
        for stage in (JUST_REGISTERED, VERIFIED, MATCHED, DATE_SET):
            self.assertFalse(d.is_open("expectations", stage))
        self.assertTrue(d.is_open("expectations", AFTER_DATE))

    def test_boundaries_open_strictly_before_expectations(self):
        """A greeting preference is a decision about a specific evening;
        intimacy expectations are a conversation between people who have
        met. They are not the same moment."""
        self.assertTrue(d.is_open("boundaries", DATE_SET))
        self.assertFalse(d.is_open("expectations", DATE_SET))

    def test_chemistry_is_open_from_the_start(self):
        """Chemistry is hobbies and activities. Nothing about it needs
        gating, and gating it would be the original confusion returning."""
        self.assertTrue(d.is_open("chemistry", JUST_REGISTERED))

    def test_sharing_contacts_waits_for_a_first_date(self):
        self.assertFalse(d.is_open("escalations", DATE_SET))
        self.assertTrue(d.is_open("escalations", AFTER_DATE))

    def test_the_week_needs_verification(self):
        self.assertFalse(d.is_open("week", JUST_REGISTERED))
        self.assertTrue(d.is_open("week", VERIFIED))

    def test_verify_retires_once_you_are_verified(self):
        self.assertTrue(d.is_open("verify", JUST_REGISTERED))
        self.assertFalse(d.is_open("verify", VERIFIED))

    def test_the_gate_retires_once_you_are_in_a_relationship(self):
        self.assertTrue(d.is_open("gate", AFTER_DATE))
        self.assertFalse(d.is_open("gate", IN_RELATIONSHIP))

    def test_an_unknown_key_is_open_rather_than_locking_someone_out(self):
        self.assertTrue(d.is_open("some_new_screen", JUST_REGISTERED))


class NavTests(unittest.TestCase):
    def _labels(self, milestones, **kw):
        return [l["label"] for l in d.nav_for(milestones, **kw)]

    def test_a_new_user_sees_a_short_menu(self):
        labels = self._labels(JUST_REGISTERED)
        self.assertEqual(labels, ["Dashboard", "Verify", "Vision", "Chemistry"])

    def test_a_verified_user_sees_no_couple_screens(self):
        labels = self._labels(VERIFIED)
        for absent in ("Sharing", "Next level", "Gate", "Relationship", "Boundaries", "Expectations"):
            self.assertNotIn(absent, labels)

    def test_the_menu_never_gets_back_to_eleven_links(self):
        """The problem being fixed. Every stage stays scannable."""
        for stage in (JUST_REGISTERED, VERIFIED, MATCHED, DATE_SET, AFTER_DATE, IN_RELATIONSHIP):
            self.assertLessEqual(len(d.nav_for(stage)), d.MAX_NAV_LINKS, self._labels(stage))

    def test_links_appear_as_the_journey_earns_them(self):
        self.assertIn("Guru", self._labels(VERIFIED))
        self.assertIn("Relationship", self._labels(IN_RELATIONSHIP))

    def test_the_contextual_screens_moved_into_guru_rather_than_the_nav(self):
        """Expectations, Sharing, the Gate and Vibes are open after a first
        date, but they are cards in Guru's hub now, not tabs. That swap is
        what got the menu from eleven links back to six — asserting the
        openness AND the absence together is what stops the next person
        from "fixing" a missing tab by putting it back."""
        for key in ("expectations", "escalations", "gate"):
            self.assertTrue(d.is_open(key, AFTER_DATE), key)
        self.assertTrue(d.is_open("vibes", IN_RELATIONSHIP))
        for label in ("Expectations", "Sharing", "Gate", "Vibes"):
            self.assertNotIn(label, self._labels(AFTER_DATE), label)
            self.assertNotIn(label, self._labels(IN_RELATIONSHIP), label)

    def test_the_dating_machine_retires_once_exclusive(self):
        """REACH and the weekly rotation are not merely unused in a
        relationship, they are the wrong thing to be offering."""
        for label in ("REACH", "Week"):
            self.assertIn(label, self._labels(AFTER_DATE), label)
            self.assertNotIn(label, self._labels(IN_RELATIONSHIP), label)
        for key in ("reach", "week", "escalations", "gate"):
            self.assertFalse(d.is_open(key, IN_RELATIONSHIP), key)

    def test_guru_is_the_one_tab_that_never_leaves(self):
        """Everything else comes and goes. If Guru could retire, the cards
        it carries would have nowhere to be reached from."""
        for stage in (VERIFIED, MATCHED, DATE_SET, AFTER_DATE, IN_RELATIONSHIP):
            self.assertIn("Guru", self._labels(stage))
        self.assertNotIn("Guru", self._labels(JUST_REGISTERED))

    def test_reach_hides_when_it_is_locked_for_the_week(self):
        self.assertIn("REACH", self._labels(VERIFIED))
        self.assertNotIn("REACH", self._labels(VERIFIED, reach_locked=True))

    def test_screens_marked_not_nav_never_appear_as_links(self):
        """Calendar and the date plan are reached from the flow that needs
        them, not from a permanent link."""
        for stage in (DATE_SET, AFTER_DATE, IN_RELATIONSHIP):
            labels = self._labels(stage)
            for absent in ("Calendar", "Date plan", "Boundaries", "Next level"):
                self.assertNotIn(absent, labels, absent)

    def test_every_surface_points_at_a_real_endpoint_name(self):
        for key, label, endpoint, unlocks, retires, nav in d.SURFACES:
            self.assertTrue(endpoint and endpoint.isidentifier(), key)
            self.assertIn(unlocks, d.ORDER, key)
            if retires is not None:
                self.assertIn(retires, d.ORDER, key)

    def test_no_surface_retires_before_it_unlocks(self):
        for key, _, _, unlocks, retires, _ in d.SURFACES:
            if retires is not None:
                self.assertLess(d.ORDER.index(unlocks), d.ORDER.index(retires), key)


class LockedReasonTests(unittest.TestCase):
    def test_an_open_surface_has_no_reason(self):
        self.assertIsNone(d.locked_reason("chemistry", JUST_REGISTERED))

    def test_every_locked_surface_explains_itself(self):
        for key, *_ in d.SURFACES:
            if not d.is_open(key, JUST_REGISTERED):
                reason = d.locked_reason(key, JUST_REGISTERED)
                self.assertTrue(reason, key)
                self.assertGreater(len(reason), 20, key)

    def test_the_expectations_reason_says_why_not_just_no(self):
        reason = d.locked_reason("expectations", DATE_SET)
        self.assertIn("first date", reason.lower())

    def test_a_retired_surface_says_it_is_behind_you(self):
        self.assertIn("behind you", d.locked_reason("verify", VERIFIED))


if __name__ == "__main__":
    unittest.main()
