"""Tests for progress.py — the journey step tracker (Segment J, step 41).

The failure worth engineering against is a tracker that flatters the demo.
Driven by which page you last opened, it would say "step 9 of 12" for
someone who merely browsed to the debrief; driven by evidence, it says what
the pair has actually done. Every test here is really about that
distinction.
"""

from __future__ import annotations

import unittest

import disclosure as d
import guru
import progress


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

EVERYTHING = {"aligned": True, "agreement_signed": True, "boundary_set": True,
              "flags_given": True, "decision_made": True, "married": True}


class ShapeTests(unittest.TestCase):
    def test_every_step_has_a_label(self):
        for step in progress.steps(JUST_REGISTERED):
            self.assertTrue(step["label"])

    def test_step_numbers_run_from_one(self):
        marked = progress.steps(JUST_REGISTERED)
        self.assertEqual([s["index"] for s in marked], list(range(1, progress.TOTAL + 1)))

    def test_exactly_one_step_is_current_while_the_journey_is_running(self):
        for milestones in (JUST_REGISTERED, VERIFIED, MATCHED, DATE_SET, AFTER_DATE):
            with self.subTest(stage=sorted(milestones)):
                current = [s for s in progress.steps(milestones) if s["state"] == "current"]
                self.assertEqual(len(current), 1)

    def test_nothing_is_current_once_it_is_all_done(self):
        """The end of a journey is not a step you are in the middle of."""
        marked = progress.steps(IN_RELATIONSHIP, EVERYTHING)
        self.assertEqual([s for s in marked if s["state"] == "current"], [])
        self.assertTrue(progress.position(IN_RELATIONSHIP, EVERYTHING)["complete"])


class PositionTests(unittest.TestCase):
    def test_it_advances_as_the_journey_does(self):
        seen = [progress.position(m, {})["done"]
                for m in (JUST_REGISTERED, VERIFIED, MATCHED, DATE_SET, AFTER_DATE)]
        self.assertEqual(seen, sorted(seen))
        self.assertLess(seen[0], seen[-1])

    def test_a_fact_moves_it_without_a_milestone_changing(self):
        """Aligning on the date is real progress that no milestone records."""
        before = progress.position(MATCHED, {})
        after = progress.position(MATCHED, {"aligned": True})
        self.assertEqual(after["done"], before["done"] + 1)

    def test_missing_facts_never_flatter_the_count(self):
        self.assertLess(progress.position(AFTER_DATE, {})["done"],
                        progress.position(AFTER_DATE, EVERYTHING)["done"])

    def test_a_skipped_step_is_not_counted_as_done(self):
        """Milestones are upward-closed, so a later one implies the earlier
        milestones — but NOT the facts in between. Someone in a
        relationship who never recorded flags has not done that step."""
        marked = progress.steps(IN_RELATIONSHIP, {})
        by_key = {s["key"]: s for s in marked}
        self.assertTrue(by_key["relationship"]["done"])
        self.assertFalse(by_key["flags"]["done"])
        position = progress.position(IN_RELATIONSHIP, {})
        self.assertLess(position["done"], progress.TOTAL)

    def test_percent_tracks_steps_actually_done(self):
        self.assertEqual(progress.position(IN_RELATIONSHIP, EVERYTHING)["percent"], 100)
        self.assertLess(progress.position(JUST_REGISTERED, {})["percent"], 20)

    def test_the_label_names_where_they_are(self):
        self.assertEqual(progress.position(VERIFIED, {})["label"], "Locked in")
        self.assertEqual(progress.position(IN_RELATIONSHIP, EVERYTHING)["label"],
                         "Journey complete")


class AgreementWithGuruTests(unittest.TestCase):
    """The tracker and Guru's "what now?" read the same facts. If they
    disagreed, one of the two screens would be lying, and the viewer has
    no way to tell which."""

    FACT_STATES = ({}, {"aligned": True},
                   {"aligned": True, "agreement_signed": True},
                   {"aligned": True, "agreement_signed": True, "boundary_set": True},
                   EVERYTHING)

    def test_neither_reports_finished_while_the_other_has_work_left(self):
        for milestones in (VERIFIED, MATCHED, DATE_SET, AFTER_DATE, IN_RELATIONSHIP):
            for facts in self.FACT_STATES:
                with self.subTest(stage=sorted(milestones), facts=sorted(facts)):
                    position = progress.position(milestones, facts)
                    action = guru.next_action(milestones, facts=facts)
                    if position["complete"]:
                        # Guru may still offer a destination — the end-of-
                        # journey screen is one — but it must not be ASKING
                        # for anything. "Nothing needs you" is the only
                        # headline consistent with a finished tracker.
                        self.assertEqual(action["headline"], "Nothing needs you")

    def test_both_read_the_same_fact_keys(self):
        """A fact renamed on one side and not the other is silent drift."""
        tracker_facts = {fact for _, _, _, fact in progress.STEPS if fact}
        self.assertTrue(tracker_facts <= {
            "aligned", "agreement_signed", "boundary_set",
            "flags_given", "decision_made", "married",
        })


if __name__ == "__main__":
    unittest.main()
