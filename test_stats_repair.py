"""The stats shapes the rest of the app depends on, and the repair.

2026-09-09 (evening), user's report: "Saving Stats -> then going to reach
UI is failing and leading to 'Internal Server Error'" and "Filters/Stats
you have just keyedin/unlocked is not getting updated."

Both came from the first stats editor, which stored whatever the form
sent — always a string. Two shapes broke, and the first one is nasty:
ONE corrupted row took REACH down for every OTHER user whose pool
contained it, so the error looked unrelated to whoever caused it.
"""

from __future__ import annotations

import json
import unittest

import db
import generate_users
import matching
import onboarding
import stats_edit as se

from test_segment_efg_routes import RouteTestCase, app_module


class NormaliseTests(unittest.TestCase):
    def test_a_number_stored_as_text_becomes_a_number(self):
        got = onboarding.normalise_stats({"weight_kg": "58", "height_cm": "165"})
        self.assertEqual(got["weight_kg"], 58)
        self.assertIsInstance(got["height_cm"], int)

    def test_a_list_stored_as_one_string_becomes_a_list(self):
        got = onboarding.normalise_stats({"languages": "English"})
        self.assertEqual(got["languages"], ["English"])

    def test_a_comma_joined_string_splits_back_into_its_parts(self):
        """How an older single-select rendered a list back at us."""
        got = onboarding.normalise_stats({"cuisine": "South Indian, Thai"})
        self.assertEqual(got["cuisine"], ["South Indian", "Thai"])

    def test_an_unrepairable_number_is_dropped_not_guessed(self):
        """A weight of "heavy" becomes absent, which reads as "not
        answered" everywhere — better than a number nobody chose."""
        self.assertNotIn("waist_in", onboarding.normalise_stats({"waist_in": "heavy"}))

    def test_a_capped_field_is_trimmed(self):
        got = onboarding.normalise_stats({"ethnicity": ["Indian", "Mixed", "European"]})
        self.assertEqual(got["ethnicity"], ["Indian", "Mixed"])

    def test_good_stats_pass_through_untouched(self):
        clean = {"age": 31, "weight_kg": 74, "languages": ["English", "Hindi"]}
        self.assertEqual(onboarding.normalise_stats(clean), clean)

    def test_it_is_applied_on_every_read(self):
        """The point of doing it here: rows already written to the
        deployed database are repaired as they load, with no migration."""
        row = {"id": "u1", "journey_state": "dating", "bgv_status": "verified",
               "stats_json": json.dumps({"city": "Bangalore", "gender": "female",
                                         "weight_kg": "58", "languages": "English"}),
               "vision_json": "[]", "skills_json": "{}", "preferences_json": "{}"}
        loaded = generate_users.from_user_row(row)
        self.assertEqual(loaded["stats"]["weight_kg"], 58)
        self.assertEqual(loaded["stats"]["languages"], ["English"])


class OneBadRowTests(unittest.TestCase):
    """The reason this mattered. Text where a number belongs does not
    break the person who saved it — it breaks the arithmetic REACH runs
    over the whole pool, for everyone else."""

    def setUp(self):
        self.pool = generate_users.generate_users(40, seed=11)

    def poisoned(self, **patch):
        pool = [dict(u) for u in self.pool]
        pool[3] = {**pool[3], "stats": {**pool[3]["stats"], **patch}}
        return pool

    def test_a_text_weight_used_to_break_the_pool(self):
        """Kept as a record of the failure mode: this is what a row looks
        like BEFORE normalise_stats sees it."""
        with self.assertRaises(TypeError):
            matching.suggest_range(self.poisoned(weight_kg="58"), "weight_kg")

    def test_normalising_the_row_repairs_the_pool(self):
        pool = [{**u, "stats": onboarding.normalise_stats(u["stats"])}
                for u in self.poisoned(weight_kg="58", height_cm="165")]
        self.assertIsNotNone(matching.suggest_range(pool, "weight_kg"))
        matching.whatif_deltas(pool[3], pool)          # must not raise


class UnlockTests(unittest.TestCase):
    """user's rule: "Filters/Stats you have just keyedin/unlocked is not
    getting updated. even after Stats - height, weight, waist have been
    updated." A lever exists only where the preference range does, and
    saving a stat never touched preferences."""

    BARE = {"fixed": {"dealbreakers": []}, "adjustable": {"age": [24, 36]}}

    def test_filling_in_a_stat_opens_its_lever(self):
        got = matching.unlock_levers_for(self.BARE, {"height_cm": 165, "weight_kg": 58})
        self.assertIn("height_cm", got["adjustable"])
        self.assertIn("weight_kg", got["adjustable"])

    def test_the_new_range_brackets_their_own_value(self):
        got = matching.unlock_levers_for(self.BARE, {"weight_kg": 58})["adjustable"]["weight_kg"]
        self.assertLess(got[0], 58)
        self.assertGreater(got[1], 58)

    def test_a_range_they_already_set_is_left_alone(self):
        """This opens doors; it does not redecorate."""
        mine = {"fixed": {"dealbreakers": []},
                "adjustable": {"age": [24, 36], "weight_kg": [50, 55]}}
        got = matching.unlock_levers_for(mine, {"weight_kg": 90})
        self.assertEqual(got["adjustable"]["weight_kg"], [50, 55])

    def test_an_unanswered_stat_opens_nothing(self):
        got = matching.unlock_levers_for(self.BARE, {"height_cm": None, "weight_kg": ""})
        self.assertNotIn("height_cm", got["adjustable"])
        self.assertNotIn("weight_kg", got["adjustable"])

    def test_it_does_not_mutate_what_it_was_given(self):
        matching.unlock_levers_for(self.BARE, {"weight_kg": 58})
        self.assertNotIn("weight_kg", self.BARE["adjustable"])

    def test_a_stat_that_backs_no_lever_opens_nothing(self):
        got = matching.unlock_levers_for(self.BARE, {"smoking": "Never"})
        self.assertEqual(set(got["adjustable"]), {"age"})


class SaveRouteTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        self.login(self.make_user("u1"))

    def stats(self):
        return json.loads(dict(db.fetch_one(self.conn, "User", id="u1"))["stats_json"])

    def prefs(self):
        return json.loads(dict(db.fetch_one(self.conn, "User", id="u1"))["preferences_json"])

    def test_saving_a_body_stat_unlocks_its_filter(self):
        self.client.post("/stats/save", data={"weight_kg": "70", "height_cm": "170"})
        adjustable = self.prefs().get("adjustable", {})
        self.assertIn("weight_kg", adjustable)
        self.assertIn("height_cm", adjustable)

    def test_a_multi_field_saves_every_pick(self):
        """user's rule: "language, Cuisine and budget can be
        multi-selectable"."""
        self.client.post("/stats/save", data={"languages": ["English", "Hindi", "Tamil"]})
        self.assertEqual(self.stats()["languages"], ["English", "Hindi", "Tamil"])

    def test_a_multi_field_is_never_stored_as_a_bare_string(self):
        self.client.post("/stats/save", data={"cuisine": ["Thai"]})
        self.assertIsInstance(self.stats()["cuisine"], list)

    def test_ethnicity_is_capped_at_two(self):
        """user's rule: "Ethnicity - maximum of 2 selectable"."""
        self.client.post("/stats/save", data={"ethnicity": ["Indian", "Mixed", "European"]})
        self.assertNotIn("ethnicity", self.stats())
        self.assertIn("form-error", self.client.get("/stats").get_data(as_text=True))

    def test_two_ethnicities_are_fine(self):
        self.client.post("/stats/save", data={"ethnicity": ["Indian", "Mixed"]})
        self.assertEqual(self.stats()["ethnicity"], ["Indian", "Mixed"])

    def test_the_screen_offers_them_as_chips_not_a_dropdown(self):
        body = self.client.get("/stats").get_data(as_text=True)
        self.assertIn("multi-field", body)
        self.assertIn('name="languages" value="English"', body.replace("\n", " ").replace("  ", " "))


if __name__ == "__main__":
    unittest.main()


class VisionScreenTests(RouteTestCase):
    """2026-09-09 (evening), user's report: "Why does Clicking on the
    Vision doesn't show the User's vision preference."

    Because it never did. The screen rendered the RELATIONSHIP-stage
    detail entries — a different vocabulary from the sign-up goals, and
    empty for anyone who has not reached that stage — so a dating user
    saw six cards saying "Nothing added yet" and none of their answers.
    """

    def make_with_vision(self, user_id, journey_state="dating"):
        row = app_module.onboarding.build_user_row(
            user_id=user_id, city="Bangalore", gender="female",
            stats={"age": 30, "education": "Master's", "nationality": "IN",
                   "profession": "Engineering", "income_band": "₹₹ · 12L – 25L"},
            visions=app_module.onboarding.build_visions(
                ["Emotional", "Physical"], ["Kids", "Travel together"],
                None, ["Adoption"], ["Road trips"]),
            activities={})
        row["bgv_status"] = "verified"
        row["journey_state"] = journey_state
        db.insert_row(self.conn, "User", row)
        self.conn.commit()
        self.login(user_id)

    def page(self):
        import re
        return re.sub(r"\s+", " ", self.client.get("/vision").get_data(as_text=True))

    def test_it_shows_the_goals_chosen_at_signup(self):
        self.make_with_vision("u_v")
        body = self.page()
        for goal in ("Intimacy", "Kids", "Travel together"):
            with self.subTest(goal=goal):
                self.assertIn(goal, body)

    def test_it_shows_each_goal_s_sub_options(self):
        self.make_with_vision("u_v")
        body = self.page()
        self.assertIn("Adoption", body)
        self.assertIn("Road trips", body)
        self.assertIn("Emotional · Physical", body)

    def test_the_relationship_detail_is_hidden_while_dating(self):
        """Six empty boxes above the thing the person came to see."""
        self.make_with_vision("u_v")
        self.assertNotIn("Detail you have added together", self.page())

    def test_it_appears_once_they_are_in_a_relationship(self):
        self.make_with_vision("u_r", journey_state="relationship")
        self.assertIn("Detail you have added together", self.page())


class BudgetIsAListNowTests(unittest.TestCase):
    """2026-09-10: budget became multi-select, and two things downstream
    still assumed one band.

    The dangerous one was the bill clause. With a list on one side,
    `b in bands` was False, that side dropped out of the comparison
    entirely, and the clause took the OTHER person's band — the higher
    one — which is precisely the harm lower_budget() exists to prevent.
    """

    def setUp(self):
        import date_alignment
        self.da = date_alignment
        self.bands = date_alignment.options_for("budget", "Bangalore")

    def test_the_lower_band_still_wins_when_one_side_is_a_list(self):
        low, mid, high = self.bands[1], self.bands[2], self.bands[3]
        self.assertEqual(self.da.lower_budget([low, mid], high, "Bangalore"), low)
        self.assertEqual(self.da.lower_budget(high, [low, mid], "Bangalore"), low)

    def test_and_when_both_sides_are_lists(self):
        low, mid, high = self.bands[1], self.bands[2], self.bands[3]
        self.assertEqual(self.da.lower_budget([mid, high], [low, high], "Bangalore"), low)

    def test_a_scalar_still_works(self):
        """Rows written before the change still hold a bare string."""
        self.assertEqual(
            self.da.lower_budget(self.bands[1], self.bands[2], "Bangalore"), self.bands[1])

    def test_neither_side_answering_is_still_none(self):
        self.assertIsNone(self.da.lower_budget(None, [], "Bangalore"))

    def test_the_alignment_screen_accepts_a_list(self):
        """It used to str() the value, so ["a", "b"] became the text
        "['a', 'b']", failed the membership check, and refused a
        perfectly good answer with "Pick a budget band"."""
        got = self.da.validate(
            {"budget": [self.bands[1], self.bands[2]], "diet": "Everything",
             "cuisine": ["Thai"]}, "Bangalore")
        self.assertTrue(got["ok"], got["error"])
        self.assertEqual(got["stats"]["budget"], [self.bands[1], self.bands[2]])

    def test_it_still_refuses_an_empty_or_bogus_budget(self):
        for value in ([], ["not a band"], ""):
            with self.subTest(value=value):
                got = self.da.validate(
                    {"budget": value, "diet": "Everything", "cuisine": ["Thai"]},
                    "Bangalore")
                self.assertFalse(got["ok"])


class OpenReachDuringRegistrationTests(RouteTestCase):
    """2026-09-10, user's report: "Clicking on Open REACH during
    registration is failing. Also, can you look this up from both men and
    women. Also it is failing to bring the keyed in/updated stats being
    visible in REACH."

    All three are the same cause. A brand-new registrant's REACH runs
    whatif_deltas() and suggest_range() over the WHOLE pool — so a single
    corrupted row anywhere in it breaks the screen for the newcomer, in
    both genders, and neither their keyed-in stats nor their unlocked
    filters ever render.
    """

    def seed(self, n=40, poison=True):
        for u in generate_users.generate_users(n, seed=42):
            row = app_module.onboarding.build_user_row(
                user_id=u["user_id"], city=u["city"], gender=u["gender"],
                stats=u["stats"], visions=u["visions"], activities={})
            row["bgv_status"] = "verified"
            row["journey_state"] = "dating"
            row["preferences_json"] = json.dumps(u["preferences"], ensure_ascii=False)
            db.insert_row(self.conn, "User", row)
        if poison:
            # exactly what the shipped editor wrote
            victim = dict(db.fetch_one(self.conn, "User", id="u_0004"))
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
        with c.session_transaction() as sess:
            return sess.get("user_id")

    def test_a_new_registrant_can_open_reach_in_either_gender(self):
        self.seed()
        for gender in ("female", "male"):
            with self.subTest(gender=gender):
                self.register(gender, f"{gender}@x.com")
                self.assertEqual(self.client.get("/reach").status_code, 200)
                self.client.post("/logout")

    def test_the_dashboard_offers_it_before_verification(self):
        """"during registration" — the button is on the Dashboard the
        moment the wizard finishes, before BGV has run."""
        self.seed()
        self.register("female", "f@x.com")
        self.assertIn("Open REACH", self.client.get("/dashboard").get_data(as_text=True))

    def test_stats_keyed_in_at_signup_are_visible_in_reach(self):
        self.seed()
        self.register("female", "f@x.com",
                      height_cm="170", weight_kg="68", waist_in="30")
        body = self.client.get("/reach").get_data(as_text=True)
        for value in ("170", "68", "30"):
            with self.subTest(value=value):
                self.assertIn(f"You: {value}", body)

    def test_stats_added_later_appear_too(self):
        """The other half of the report — updated, not just keyed in."""
        self.seed()
        self.register("female", "f@x.com")
        before = self.client.get("/reach").get_data(as_text=True)
        self.assertNotIn("You: 170", before)

        self.client.post("/stats/save", data={
            "height_cm": "170", "weight_kg": "68", "waist_in": "30"})
        after = self.client.get("/reach").get_data(as_text=True)
        for value in ("170", "68", "30"):
            with self.subTest(value=value):
                self.assertIn(f"You: {value}", after)

    def test_a_multi_budget_does_not_block_registration(self):
        """budget went multi-select on 2026-09-09 (evening); this is the
        path that was never exercised end to end."""
        self.seed()
        bands = app_module.locale_defaults.budget_bands_for("Bangalore")
        user_id = self.register("male", "m@x.com", budget=[bands[1], bands[2]])
        self.assertIsNotNone(user_id)
        stored = json.loads(dict(db.fetch_one(self.conn, "User", id=user_id))["stats_json"])
        self.assertEqual(stored["budget"], [bands[1], bands[2]])
        self.assertEqual(self.client.get("/reach").status_code, 200)
