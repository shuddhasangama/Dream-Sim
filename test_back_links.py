"""Every back link goes to the screen you came from.

2026-09-09, user's rule: "Please check in general whether the return
button at each level goes back to appropriate previous screen."

Before this, every signed-in screen fell back to the Dashboard. That is
right for a nav tab and wrong for everything reached from a Guru card,
wrong for the three sections of the post-date screen, and the ceremony
had no way out at all. The destinations now come from one table
(disclosure.PARENT), so the assertions worth making are about that table
and about what the rendered page actually contains.
"""

from __future__ import annotations

import re
import unittest

import ceremony
import db
import disclosure as d

from test_segment_efg_routes import RouteTestCase, app_module


class ParentTableTests(unittest.TestCase):
    def test_every_surface_declares_where_back_goes(self):
        """A surface missing from PARENT would silently fall through to
        no link at all, which is the dead end this replaced."""
        for key, *_rest in d.SURFACES:
            with self.subTest(surface=key):
                self.assertIn(key, d.PARENT)

    def test_every_parent_is_a_real_endpoint(self):
        endpoints = set(d.ENDPOINT_TO_KEY)
        for key, parent in d.PARENT.items():
            if parent is None:
                continue
            with self.subTest(surface=key):
                self.assertIn(parent, endpoints)
        for endpoint, parent in d.ENDPOINT_PARENT.items():
            with self.subTest(endpoint=endpoint):
                self.assertIn(parent, endpoints)

    def test_nothing_is_its_own_parent(self):
        for key, parent in d.PARENT.items():
            if parent is None:
                continue
            with self.subTest(surface=key):
                self.assertNotEqual(d.ENDPOINT_TO_KEY.get(parent), key)

    def walk_back(self, key):
        seen, current = [key], key
        while True:
            parent = d.parent_of(current)
            if parent is None:
                return current, seen
            current = d.ENDPOINT_TO_KEY[parent]
            self.assertNotIn(current, seen, f"cycle: {seen + [current]}")
            seen.append(current)

    def test_following_back_always_reaches_the_dashboard(self):
        """No cycles, and nothing stranded. Walking back repeatedly from
        any screen has to terminate somewhere a person recognises."""
        for key, *_rest in d.SURFACES:
            if key in d.DYNAMIC_PARENT:
                continue
            end, trail = self.walk_back(key)
            with self.subTest(surface=key):
                self.assertEqual(end, "dashboard", f"{key} walks back via {trail}")

    def test_the_dynamic_ones_reach_it_too(self):
        """A screen whose parent the view computes still has to land
        somewhere — it is just not this table that says where."""
        for kind, parent in app_module.CEREMONY_PARENT.items():
            end, trail = self.walk_back(d.ENDPOINT_TO_KEY[parent])
            with self.subTest(kind=kind):
                self.assertEqual(end, "dashboard", f"{kind} walks back via {trail}")

    def test_the_ceremony_names_a_parent_for_every_kind(self):
        """It is the one screen entered from four places, so its parent
        cannot live in the table — which makes a missing kind easy to
        overlook."""
        for kind in ceremony.KINDS:
            with self.subTest(kind=kind):
                self.assertIn(kind, app_module.CEREMONY_PARENT)


class RenderedBackLinkTests(RouteTestCase):
    """The table is right; this is whether the page actually renders it."""

    def setUp(self):
        super().setUp()
        self.login(self.make_user("u1"))
        self.make_user("u2")
        self.lock = self.make_lockin("u1", "u2")
        plan = self.make_plan(self.lock, status="confirmed")
        db.insert_row(self.conn, "DateOutcome", {
            "id": f"outcome:{plan}", "dateplan_id": plan, "happened": 1,
            "a_green_flags_json": "[]", "a_red_flags_json": "[]",
            "b_green_flags_json": "[]", "b_red_flags_json": "[]",
        })
        self.conn.commit()

    def back_href(self, path):
        body = self.client.get(path).get_data(as_text=True)
        found = re.search(r'<a class="backlink" href="([^"]+)"', body)
        return found.group(1) if found else None

    def test_the_agreement_goes_back_to_guru_not_the_dashboard(self):
        """user's rule: "Guru -> Agreement of Understanding - there is no
        return option back to Guru. It should take back to Guru, rather
        than Dashboard"."""
        self.assertEqual(self.back_href("/plan"), "/guru")

    def test_the_post_date_sections_go_back_to_the_post_date_screen(self):
        for path in ("/expectations", "/escalations", "/next-level"):
            with self.subTest(path=path):
                self.assertEqual(self.back_href(path), "/after-date")

    def test_the_post_date_screen_goes_back_to_guru(self):
        self.assertEqual(self.back_href("/after-date"), "/guru")

    def test_the_ceremony_has_a_way_out(self):
        """user's rule: "Again there is no way to go back to where you
        were before"."""
        self.assertEqual(self.back_href(f"/ceremony/{ceremony.DATE_AGREEMENT}"), "/plan")
        self.assertEqual(self.back_href(f"/ceremony/{ceremony.CONTACT_SHARE}"), "/after-date")

    def test_boundaries_goes_back_to_the_plan_that_sent_you(self):
        self.assertEqual(self.back_href("/boundaries"), "/plan")

    def test_everything_else_goes_back_to_guru(self):
        self.assertEqual(self.back_href("/guru/everything"), "/guru")

    def test_the_back_link_names_its_destination(self):
        body = self.client.get("/plan").get_data(as_text=True)
        self.assertIn("Guru", body.split('class="backlink"')[1][:40])


if __name__ == "__main__":
    unittest.main()
