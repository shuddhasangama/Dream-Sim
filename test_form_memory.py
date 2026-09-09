"""Tests for form_memory.py — input surviving a rejected submit.

2026-09-09, user's rule: "Retain/remember selections if 'Continue to
Stats' fails. Check if there are any other screens in which remember
selections need to be done."

An audit found twelve others. Two shapes: routes that re-render from
state validation declined to write, and routes that redirect (which
discards the body by definition). These are the route-level proofs for
the worst of them.
"""

from __future__ import annotations

import unittest
from unittest import mock

import ceremony
import db
import form_memory as fm

from test_segment_efg_routes import RouteTestCase, app_module


class ShapingTests(unittest.TestCase):
    def test_a_signature_is_never_remembered(self):
        """Re-filling a typed name would mean the second attempt was
        signed by the first attempt's keystrokes — which is the one thing
        a signature exists to rule out."""
        got = fm.capture("ceremony_view", {"signed_name": "Arjun", "acks": ["a", "b"]})
        self.assertNotIn("signed_name", got["fields"])
        self.assertEqual(got["fields"]["acks"], ["a", "b"])

    def test_a_memory_never_leaks_into_a_different_screen(self):
        got = fm.capture("gate_view", {"question_key": ["who_knows"]})
        self.assertEqual(fm.recall(got, "vision_view")["fields"], {})
        self.assertTrue(fm.recall(got, "gate_view")["recalled"])

    def test_clearing_a_field_survives(self):
        """A remembered empty value beats the fallback. Emptying a box is
        something someone did on purpose; restoring the old text would
        undo it in front of them."""
        self.assertEqual(fm.value({"reason": ""}, "reason", "old text"), "")
        self.assertEqual(fm.chosen({"cuisine": []}, "cuisine", ["Thai"]), [])

    def test_an_absent_field_falls_back(self):
        self.assertEqual(fm.value({}, "reason", "old text"), "old text")
        self.assertEqual(fm.chosen({}, "cuisine", ["Thai"]), ["Thai"])


class RememberedAcrossRedirectTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.login(self.make_user("u1"))
        self.make_user("u2")
        self.lock = self.make_lockin("u1", "u2")

    def test_a_rejected_activity_sort_keeps_every_pick(self):
        """The worst instance: twelve activities into four buckets, lost
        to a silent redirect with no error either."""
        self.client.post("/chemistry/activities", data={
            "act__Cooking": "good", "act__Yoga": "improve"})
        body = self.client.get("/chemistry").get_data(as_text=True)
        self.assertIn("form-error", body)
        self.assertEqual(body.count("checked"), 2)

    def test_it_is_forgotten_after_one_render(self):
        """Otherwise the rejection reappears every later visit."""
        self.client.post("/chemistry/activities", data={"act__Cooking": "good"})
        self.client.get("/chemistry")
        self.assertNotIn("form-error", self.client.get("/chemistry").get_data(as_text=True))

    def test_a_refused_signature_keeps_the_ticked_terms(self):
        self.make_plan(self.lock, status="pending_signatures")
        kind = ceremony.DATE_AGREEMENT
        self.client.get(f"/ceremony/{kind}")
        self.client.post(f"/ceremony/{kind}/step")                    # playbook
        keys = list(ceremony.ack_keys(kind))
        self.client.post(f"/ceremony/{kind}/step",
                         data={"signed_name": "", "acks": keys[:2]})  # blank name
        body = self.client.get(f"/ceremony/{kind}").get_data(as_text=True)
        self.assertEqual(body.count('name="acks"') - body.count("checked"), 2)

    def test_the_name_itself_is_not_re_filled(self):
        self.make_plan(self.lock, status="pending_signatures")
        kind = ceremony.DATE_AGREEMENT
        self.client.get(f"/ceremony/{kind}")
        self.client.post(f"/ceremony/{kind}/step")
        self.client.post(f"/ceremony/{kind}/step",
                         data={"signed_name": "Arjun Rao", "acks": []})
        self.assertNotIn("Arjun Rao", self.client.get(f"/ceremony/{kind}").get_data(as_text=True))

    def test_a_blank_chemistry_set_stays_on_the_screen_you_were_on(self):
        """The success path honoured `back`; this early return did not,
        so a blank submit threw you off /expectations onto /chemistry."""
        got = self.client.post("/chemistry/set", data={
            "key": "", "value": "", "back": "expectations_view"})
        self.assertTrue(got.headers["Location"].endswith("/expectations"))


class SilentRejectionTests(RouteTestCase):
    """Screens that refused a submit and said nothing at all."""

    def setUp(self):
        super().setUp()
        self.login(self.make_user("u1"))

    def test_a_rejected_vision_change_says_why(self):
        self.client.post("/vision/declare-change", data={
            "element_key": "Kids", "from_value": "Want kids", "to_value": ""})
        self.assertIn("form-error", self.client.get("/vision").get_data(as_text=True))


if __name__ == "__main__":
    unittest.main()
