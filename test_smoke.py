"""The smoke test, rewritten.

2026-09-10, user's rule: "Fix 'smoke_test.py is still broken'".

The old smoke_test.py imported a `load_users` that stopped existing
sometime around the move to a database, so it had been excluded from
every run since. A broken test nobody runs is worse than no test: it is a
green tick that means nothing. It is deleted, and this replaces it.

What it does instead is the check that would have caught the three
Internal Server Errors reported between 4 and 10 September, none of which
any unit test could see: **walk the whole route table and open every page
that a signed-in person can reach, in both genders, and fail if any of
them returns a 5xx.**

The pool it walks with is deliberately not a pristine generated one. It
holds the two shapes that broke production and that `generate_users()`
cannot produce:

* a registrant who skipped every optional stat, which is what put a
  KeyError inside a whole-pool scan on 10 September; and
* a row with text where a number belongs, which is what the shipped stats
  editor wrote before `normalise_stats()` existed.

Any GET route needing a URL parameter is skipped — this checks that the
plain screens render, not that every object exists.
"""

from __future__ import annotations

import json
import unittest

import db
import generate_users
from test_segment_efg_routes import RouteTestCase, app_module

# Screens that are supposed to take you somewhere else, or that end the
# session, rather than render. Skipped by name so a new one has to be
# added deliberately.
_NOT_A_PAGE = {
    "static", "logout",
}

# Admin and simulation scaffolding. Real, but not part of a person's
# journey, and several of them mutate the world just by being opened.
_SCAFFOLDING_PREFIXES = ("/admin", "/pool", "/demo", "/__")


def _plain_get_routes() -> list[str]:
    """Every GET route with no URL parameters."""
    out = []
    for rule in app_module.app.url_map.iter_rules():
        if rule.arguments or "GET" not in rule.methods:
            continue
        if rule.endpoint in _NOT_A_PAGE:
            continue
        if str(rule).startswith(_SCAFFOLDING_PREFIXES):
            continue
        out.append(str(rule))
    return sorted(set(out))


# Registered once, at import. The "/__" prefix keeps it out of
# _plain_get_routes(), so the walk never trips over it — and registering
# it here rather than inside a test avoids unpicking Flask's url_map,
# which has no supported way to remove a rule.
_BOOM_PATH = "/__smoke_boom"


@app_module.app.route(_BOOM_PATH)
def _smoke_boom():
    raise RuntimeError("deliberate — test_smoke.py")


class EveryScreenRendersTests(RouteTestCase):
    """The one test that fails when a page 500s, whatever the reason."""

    def seed(self, n=25):
        for u in generate_users.generate_users(n, seed=3):
            row = app_module.onboarding.build_user_row(
                user_id=u["user_id"], city=u["city"], gender=u["gender"],
                stats=u["stats"], visions=u["visions"], activities={})
            row["bgv_status"] = "verified"
            row["journey_state"] = "dating"
            row["preferences_json"] = json.dumps(u["preferences"], ensure_ascii=False)
            db.insert_row(self.conn, "User", row)

        # The shape the shipped editor wrote: text where a number belongs.
        victim = dict(db.fetch_one(self.conn, "User", id="u_0002"))
        stats = json.loads(victim["stats_json"])
        stats.update(weight_kg="58", height_cm="165", languages="English")
        victim["stats_json"] = json.dumps(stats)
        db.insert_row(self.conn, "User", victim)
        self.conn.commit()

    def register(self, gender, email, **extra):
        c = self.client
        c.post("/signup", data={"email": email})
        c.post("/onboarding/vision", data={
            "intimacy_kinds": ["Emotional", "Physical"],
            "other_keys": ["Kids"], "kids_route": ["Naturally"]})
        c.post("/onboarding/stats", data={
            "city": "Bangalore", "gender": gender, "age": "31",
            "education": "Master's", "nationality": "IN",
            "profession": "Engineering", "salary": "1800000",
            "diet": "Everything", "religion": "Hindu",
            "languages": ["English"], "cuisine": ["Thai"],
            "ethnicity": ["Indian"], **extra})
        c.post("/onboarding/chemistry", data={
            "act__Cooking": "good", "act__Yoga": "improve",
            "act__Tennis": "maybe", "act__Salsa": "no"})
        c.post("/onboarding/finish")

    def test_there_are_routes_to_walk(self):
        """A smoke test that silently walks nothing is the failure mode
        this file exists to stop happening twice."""
        self.assertGreater(len(_plain_get_routes()), 20)

    def _walk(self, label):
        broke = []
        for path in _plain_get_routes():
            response = self.client.get(path, follow_redirects=False)
            if response.status_code >= 500:
                broke.append(f"{path} → {response.status_code}")
        self.assertEqual(broke, [], f"{label}: screens returned a server error")

    def test_no_screen_500s_for_a_registrant_who_skipped_the_optional_stats(self):
        self.seed()
        self.register("female", "skipper@x.com")
        self._walk("she skipped height/weight/waist")

    def test_no_screen_500s_for_a_registrant_who_filled_them_in(self):
        """The other half: he has the levers that scan her row."""
        self.seed()
        self.register("female", "skipper@x.com")
        self.client.post("/logout")
        self.register("male", "filled@x.com",
                      height_cm="178", weight_kg="74", waist_in="32")
        self._walk("he filled them in, pool holds a skipper")

    def test_no_screen_500s_signed_out(self):
        self.seed()
        self._walk("signed out")

    def test_a_broken_screen_is_actually_caught(self):
        """The guard on the guard. If a 500 could slip past, every other
        test in this file is a green tick that means nothing.

        Also the standing check on the error handling added on the same
        day: what a broken screen shows is our page and a reference code,
        never Werkzeug's "Internal Server Error"."""
        try:
            app_module.app.config["PROPAGATE_EXCEPTIONS"] = False
            response = self.client.get(_BOOM_PATH)
            self.assertEqual(response.status_code, 500)
            body = response.get_data(as_text=True)
            self.assertNotIn("Internal Server Error", body)
            self.assertNotIn("Traceback", body)
            self.assertRegex(body, r"DC-[A-Z2-9]{4}-[A-Z2-9]{2}")
        finally:
            app_module.app.config.pop("PROPAGATE_EXCEPTIONS", None)

    def test_the_deliberately_broken_route_is_not_in_the_walk(self):
        self.assertNotIn(_BOOM_PATH, _plain_get_routes())


if __name__ == "__main__":
    unittest.main()
