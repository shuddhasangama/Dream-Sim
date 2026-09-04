"""Tests for guru.py — the hub that replaced four tabs (Segment G).

Guru carries the contextual screens as cards, which makes it the one place
where a timing leak would show up as a link rather than a form. So the
assertion that matters most here is the double gate: a card must never
appear for a surface disclosure.py would refuse, because a card is an
invitation and a 403 after clicking one is a worse experience than the tab
never being there.

The other half is that next_action() stays singular. The moment it returns
a list, this screen is the crowded navigation it was built to replace.
"""

from __future__ import annotations

import unittest

import disclosure as d
import guru


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

ALL_STAGES = (JUST_REGISTERED, VERIFIED, MATCHED, DATE_SET, AFTER_DATE, IN_RELATIONSHIP)

DONE_TO_DATE = {"agreement_signed": True, "boundary_set": True}
ALL_DONE = {**DONE_TO_DATE, "flags_given": True, "decision_made": True}


def keys(milestones):
    return [c["surface"] for c in guru.cards(milestones)]


class CardGateTests(unittest.TestCase):
    def test_a_card_never_offers_a_door_the_router_would_slam(self):
        """The double gate. This is the one that matters: every card is a
        link, and disclosure.py guards the route behind it."""
        for stage in ALL_STAGES:
            for card in guru.cards(stage):
                with self.subTest(surface=card["surface"]):
                    self.assertTrue(d.is_open(card["surface"], stage))

    def test_every_card_names_a_surface_disclosure_actually_knows(self):
        """An unknown key is treated as open by is_open(), so a typo here
        would sail past the gate above rather than failing loudly."""
        for code, *_rest, surface, _needs, _hides in [
            (c[0], c[1], c[2], c[3], c[4], c[5], c[6]) for c in guru.CARDS
        ]:
            with self.subTest(code=code):
                self.assertIn(surface, d.BY_KEY)

    def test_a_brand_new_user_is_offered_nothing(self):
        self.assertEqual(guru.cards(JUST_REGISTERED), [])

    def test_a_verified_user_with_no_match_is_offered_nothing_either(self):
        """Everything open to them at that point — REACH, the week — already
        has a tab. A card for it would be the same link twice."""
        self.assertEqual(guru.cards(VERIFIED), [])

    def test_nothing_that_has_its_own_tab_is_also_a_card(self):
        tabs = {s[0] for s in d.SURFACES if s[5]}
        for card in guru.CARDS:
            with self.subTest(code=card[0]):
                self.assertNotIn(card[4], tabs)

    def test_cards_arrive_as_the_journey_earns_them(self):
        self.assertNotIn("calendar", keys(VERIFIED))
        self.assertIn("calendar", keys(MATCHED))
        self.assertNotIn("debrief", keys(MATCHED))
        self.assertIn("debrief", keys(DATE_SET))
        self.assertNotIn("after_date", keys(DATE_SET))
        self.assertIn("after_date", keys(AFTER_DATE))

    def test_the_dating_cards_retire_once_exclusive(self):
        for surface in ("reach", "calendar", "debrief", "after_date", "gate"):
            with self.subTest(surface=surface):
                self.assertNotIn(surface, keys(IN_RELATIONSHIP))

    def test_the_relationship_cards_are_there_once_exclusive(self):
        self.assertIn("vibes", keys(IN_RELATIONSHIP))

    def test_the_screens_pulled_out_of_the_nav_all_landed_here(self):
        """Expectations, Sharing, the Gate and Vibes stopped being tabs.
        If they had stopped being reachable instead, that is a regression
        dressed up as a tidy-up.

        2026-09-04: Expectations, Sharing and Next level stopped being
        three cards too — they are three sections of /after-date. That is
        one door instead of three, not three doors closed."""
        after = keys(AFTER_DATE)
        for surface in ("after_date", "gate"):
            self.assertIn(surface, after, surface)
        self.assertIn("vibes", keys(IN_RELATIONSHIP))

    def test_the_clubbed_screen_replaced_three_separate_invitations(self):
        """user's rule: "post date expectations all of these can be
        clubbed together"."""
        after = keys(AFTER_DATE)
        for surface in ("expectations", "escalations", "next_level"):
            with self.subTest(surface=surface):
                self.assertNotIn(surface, after)
                self.assertTrue(d.is_open(surface, AFTER_DATE),
                                "still routable, just not a separate card")

    def test_the_hub_stays_readable(self):
        """MAX_CARDS caps what competes with the one answer on /guru.
        The full list lives at /guru/everything, so this is the cap the
        SCREEN is held to — see the route test in
        test_segment_ghij_routes.py."""
        for stage in ALL_STAGES:
            with self.subTest(stage=sorted(stage)):
                self.assertLessEqual(len(guru.cards(stage)[:guru.MAX_CARDS]), guru.MAX_CARDS)

    def test_the_full_list_never_grows_back_into_the_old_navigation(self):
        """Eleven links is what started this. /guru/everything is allowed
        to be longer than the hub, but not unbounded."""
        for stage in ALL_STAGES:
            with self.subTest(stage=sorted(stage)):
                self.assertLessEqual(len(guru.cards(stage)), 6, keys(stage))

    def test_the_action_link_is_never_also_a_tile(self):
        """The same door twice, once as the answer and once as a card, is
        exactly the "multiple options" the review was about."""
        for stage in ALL_STAGES:
            action = guru.next_action(stage, facts=ALL_DONE)
            shown = guru.cards(stage, exclude_endpoint=action["endpoint"])
            with self.subTest(stage=sorted(stage)):
                self.assertNotIn(action["endpoint"], [c["endpoint"] for c in shown])

    def test_every_card_carries_the_text_the_screen_renders(self):
        for stage in ALL_STAGES:
            for card in guru.cards(stage):
                with self.subTest(surface=card["surface"]):
                    self.assertTrue(card["code"] and card["title"] and card["subtitle"])
                    self.assertTrue(card["endpoint"])

    def test_no_card_uses_the_forbidden_word(self):
        """docs/CLAUDE.md: never "contract" in identifiers or copy."""
        for card in guru.CARDS:
            with self.subTest(code=card[0]):
                self.assertNotIn("contract", " ".join(str(x) for x in card).lower())


class NextActionTests(unittest.TestCase):
    def test_it_returns_exactly_one_thing_at_every_stage(self):
        for stage in ALL_STAGES:
            with self.subTest(stage=sorted(stage)):
                action = guru.next_action(stage, facts=ALL_DONE)
                self.assertIsInstance(action, dict)
                self.assertTrue(action["headline"])
                self.assertTrue(action["body"])

    def test_an_unverified_user_is_sent_to_verification_and_nowhere_else(self):
        action = guru.next_action(JUST_REGISTERED)
        self.assertEqual(action["endpoint"], "verify_view")

    def test_a_verified_user_with_no_match_is_told_nothing_needs_doing_yet(self):
        self.assertEqual(guru.next_action(VERIFIED)["endpoint"], "week")

    def test_a_matched_user_is_asked_for_availability(self):
        self.assertEqual(guru.next_action(MATCHED)["endpoint"], "calendar_view")

    def test_the_agreement_comes_before_the_boundary(self):
        with_nothing = guru.next_action(DATE_SET, facts={})
        with_signature = guru.next_action(DATE_SET, facts={"agreement_signed": True})
        self.assertEqual(with_nothing["endpoint"], "plan_view")
        self.assertEqual(with_signature["endpoint"], "boundaries_view")

    def test_between_the_prep_and_the_date_there_is_nothing_to_do(self):
        action = guru.next_action(DATE_SET, facts=DONE_TO_DATE)
        self.assertIsNone(action.get("cta") and None)
        self.assertEqual(action["headline"], "Enjoy it")

    def test_flags_come_before_the_decision(self):
        flags_first = guru.next_action(AFTER_DATE, facts=DONE_TO_DATE)
        then_decide = guru.next_action(AFTER_DATE, facts={**DONE_TO_DATE, "flags_given": True})
        self.assertEqual(flags_first["endpoint"], "debrief_view")
        self.assertIn("green", flags_first["headline"].lower())
        self.assertEqual(then_decide["endpoint"], "debrief_view")
        self.assertIn("next", then_decide["headline"].lower())

    def test_missing_facts_under_promise_rather_than_claiming_a_step_is_done(self):
        """Guru is told facts a milestone cannot express. An absent fact
        must read as not-yet-done — telling someone they have signed when
        they have not is the failure worth engineering against."""
        self.assertEqual(guru.next_action(DATE_SET, facts=None)["endpoint"], "plan_view")
        self.assertEqual(guru.next_action(DATE_SET, facts={})["endpoint"], "plan_view")

    def test_a_couple_is_pointed_at_the_four_pillars(self):
        action = guru.next_action(IN_RELATIONSHIP, facts=ALL_DONE)
        self.assertEqual(action["endpoint"], "relationship_view")

    def test_when_there_is_nothing_it_says_so_rather_than_inventing_busywork(self):
        """Reached only by a user past the first date who has done
        everything and is not yet exclusive — waiting on their partner."""
        action = guru.next_action(AFTER_DATE, facts=ALL_DONE)
        self.assertIsNone(action["endpoint"])
        self.assertIsNone(action["cta"])

    def test_every_endpoint_it_offers_is_a_surface_that_is_open(self):
        """Guru must not send someone at a lock. Checked against every
        combination of the facts it reasons about, not just the happy
        path — that is where an ordering slip would hide."""
        endpoints = {s[2]: s[0] for s in d.SURFACES}
        for stage in ALL_STAGES:
            for facts in ({}, DONE_TO_DATE, ALL_DONE):
                action = guru.next_action(stage, facts=facts)
                endpoint = action["endpoint"]
                if endpoint is None:
                    continue
                with self.subTest(stage=sorted(stage), endpoint=endpoint):
                    self.assertIn(endpoint, endpoints)
                    self.assertTrue(d.is_open(endpoints[endpoint], stage))

    def test_an_action_with_a_destination_always_has_a_label_for_it(self):
        for stage in ALL_STAGES:
            for facts in ({}, DONE_TO_DATE, ALL_DONE):
                action = guru.next_action(stage, facts=facts)
                with self.subTest(stage=sorted(stage), headline=action["headline"]):
                    self.assertEqual(action["endpoint"] is None, action["cta"] is None)


if __name__ == "__main__":
    unittest.main()


class GateFirstTests(unittest.TestCase):
    """2026-09-04, user's rule: "If one of them expressed moving to next
    stage it should be visible or first thing someone wants to see."

    It used to be the ninth tile down, and next_action() had no knowledge
    of it at all.
    """

    OPEN = {**ALL_DONE, "gate_open": True, "partner_name": "Meera"}

    def test_an_open_gate_outranks_everything_else(self):
        for facts in ({"gate_open": True, "partner_name": "Meera"},   # nothing else done
                      self.OPEN):                                     # everything else done
            with self.subTest(facts=sorted(facts)):
                action = guru.next_action(AFTER_DATE, facts=facts)
                self.assertEqual(action["endpoint"], "gate_view")

    def test_it_names_who_moved_first(self):
        action = guru.next_action(AFTER_DATE, facts={**self.OPEN, "gate_raised_by_partner": True})
        self.assertIn("Meera", action["headline"])

    def test_it_names_nobody_when_they_arrived_together(self):
        """Both picking "relationship" at the debrief has no single mover,
        and inventing one would be a lie."""
        action = guru.next_action(AFTER_DATE, facts={**self.OPEN, "gate_raised_by_partner": False})
        self.assertNotIn("Meera", action["headline"])

    def test_it_says_something_different_when_your_answers_are_open(self):
        waiting = guru.next_action(AFTER_DATE, facts={**self.OPEN, "gate_waiting_on_me": True})
        done = guru.next_action(AFTER_DATE, facts=self.OPEN)
        self.assertNotEqual(waiting["body"], done["body"])
        self.assertNotEqual(waiting["cta"], done["cta"])

    def test_it_never_hurries_anyone(self):
        """user's rule: "People not committing to things or committing too
        early without thinking is what made me to take up this problem"."""
        for facts in (self.OPEN,
                      {**self.OPEN, "gate_waiting_on_me": True},
                      {**self.OPEN, "gate_nothing_asked_yet": True}):
            action = guru.next_action(AFTER_DATE, facts=facts)
            with self.subTest(cta=action["cta"]):
                for word in ("now", "today", "hurry", "don't wait", "before"):
                    self.assertNotIn(word, action["cta"].lower())

    def test_a_closed_gate_goes_back_to_the_ordinary_order(self):
        action = guru.next_action(AFTER_DATE, facts={**ALL_DONE, "gate_open": False})
        self.assertNotEqual(action["endpoint"], "gate_view")


class StaleActionTests(unittest.TestCase):
    """Guru asked for a signature on a date that had already happened.

    Found while cutting the hub to two cards: with the list short, the
    wrong answer at the top is the whole screen.
    """

    AFTER = {"flags_given": False, "decision_made": False, "date_done": True}

    def test_it_does_not_chase_a_signature_for_an_evening_that_is_over(self):
        action = guru.next_action(AFTER_DATE, facts=self.AFTER)
        self.assertEqual(action["endpoint"], "debrief_view")

    def test_it_still_chases_one_for_a_date_that_has_not_happened(self):
        action = guru.next_action(DATE_SET, facts={"date_done": False})
        self.assertEqual(action["endpoint"], "plan_view")

    def test_a_second_date_asks_for_its_own_signature_again(self):
        """The plan row is rebuilt per date, so date_done is about THIS
        date — a couple on their second date signs again."""
        action = guru.next_action(AFTER_DATE, facts={**ALL_DONE, "date_done": False,
                                                     "agreement_signed": False})
        self.assertEqual(action["endpoint"], "plan_view")


class CardOrderTests(unittest.TestCase):
    def test_the_newest_thing_is_the_first_card(self):
        """Only MAX_CARDS reach the hub. In table order that put the
        agreement for a date already had above the checkpoint just
        raised."""
        shown = [c["surface"] for c in guru.cards(AFTER_DATE)][:guru.MAX_CARDS]
        self.assertIn("after_date", shown)
        self.assertIn("gate", shown)
        self.assertNotIn("plan", shown)
