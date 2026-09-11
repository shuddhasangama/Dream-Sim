"""API integration checks against an isolated database and Flask session."""
import json
from unittest import mock

import db
import generate_users
from test_segment_efg_routes import RouteTestCase, app_module


class ApiTests(RouteTestCase):
    def setUp(self):
        super().setUp()
        for name, user in zip(("owner", "other"), generate_users.generate_users(2, seed=11)):
            row = app_module.onboarding.build_user_row(
                user_id=name, city=user["city"], gender=user["gender"],
                stats=user["stats"], visions=user["visions"], activities={})
            row["bgv_status"] = "verified"
            row["journey_state"] = "dating"
            row["preferences_json"] = json.dumps(user["preferences"])
            db.insert_row(self.conn, "User", row)
        self.conn.commit()
        self.login("owner")

    def test_health_does_not_open_database(self):
        with mock.patch.object(db, "get_connection", side_effect=AssertionError("DB accessed")):
            response = self.client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json, {"data": {"status": "ok", "api_version": "v1"}, "error": None})

    def test_signed_out_and_stale_sessions_return_json_not_redirects(self):
        for user_id in (None, "deleted"):
            with self.client.session_transaction() as session:
                session.clear()
                if user_id:
                    session["user_id"] = user_id
            for path in ("me", "profile", "reach", "reach/ignore", "reach/show-all", "reach/widen", "reach/set-range"):
                method = self.client.post if "/" in path else self.client.get
                response = method("/api/v1/" + path)
                self.assertEqual(response.status_code, 401)
                self.assertEqual(response.json["error"]["code"], "authentication_required")
                self.assertNotIn("Location", response.headers)

    def test_own_profile_allowlist_and_identity(self):
        me = self.client.get("/api/v1/me").json["data"]
        self.assertEqual(me, {"user_id": "owner", "journey_state": "dating", "bgv_status": "verified"})
        response = self.client.get("/api/v1/profile?user_id=other")
        self.assertEqual(response.json["data"]["user_id"], "owner")
        self.assertEqual(set(response.json["data"]), {"user_id", "city", "gender", "age_band", "stats", "visions", "preferences", "journey_state", "bgv_status"})
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_reach_state_matches_web_actions_and_verification_scope(self):
        for status in ("pending", "verified"):
            self.conn.execute("UPDATE User SET bgv_status = ? WHERE id = ?", (status, "owner"))
            self.conn.commit()
            web = self.client.post("/reach/show-all", json={"ignore": False})
            api = self.client.get("/api/v1/reach")
            self.assertEqual(api.status_code, 200)
            self.assertEqual(api.json["data"], web.json)
            self.assertEqual(api.json["data"]["counting_unverified"], status == "pending")

    def test_all_mutations_persist_and_match_web(self):
        cases = [("ignore", {"filter": "age", "ignore": True}),
                 ("show-all", {"ignore": True}),
                 ("widen", {"lever": "age"}),
                 ("set-range", {"lever": "age", "min": 25, "max": 40})]
        for action, payload in cases:
            with self.subTest(action=action):
                original = db.fetch_one(self.conn, "User", id="owner")["preferences_json"]
                web = self.client.post("/reach/" + action, json=payload)
                expected = db.fetch_one(self.conn, "User", id="owner")["preferences_json"]
                self.conn.execute("UPDATE User SET preferences_json = ? WHERE id = ?", (original, "owner"))
                self.conn.commit()
                api = self.client.post("/api/v1/reach/" + action, json=payload)
                self.assertEqual(api.status_code, 200)
                self.assertEqual(api.json["data"], web.json)
                self.assertEqual(db.fetch_one(self.conn, "User", id="owner")["preferences_json"], expected)
                self.assertEqual(api.json["data"], self.client.get("/api/v1/reach").json["data"])

    def test_invalid_requests_do_not_mutate_preferences(self):
        original = db.fetch_one(self.conn, "User", id="owner")["preferences_json"]
        cases = [("ignore", []), ("ignore", None), ("ignore", {}),
                 ("ignore", {"filter": [], "ignore": True}),
                 ("ignore", {"filter": "unknown", "ignore": True}),
                 ("ignore", {"filter": "age", "ignore": "false"}),
                 ("show-all", {"ignore": 1}),
                 ("widen", {"lever": "unknown"}),
                 ("widen", {"lever": []}),
                 ("set-range", {"lever": "age", "min": 40, "max": 20}),
                 ("set-range", {"lever": "age", "min": True, "max": 40}),
                 ("set-range", {"lever": "age", "min": "25", "max": 40}),
                 ("set-range", {"lever": "age", "min": float("nan"), "max": 40}),
                 ("set-range", {"lever": "age", "min": 25, "max": float("inf")}),
                 ("set-range", {"lever": "unknown", "min": 25, "max": 40}),
                 ("show-all", {"ignore": True, "user_id": "other"})]
        for action, payload in cases:
            with self.subTest(action=action, payload=payload):
                response = self.client.post("/api/v1/reach/" + action, data=json.dumps(payload), content_type="application/json")
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json["error"]["code"], "validation_error")
        self.assertEqual(db.fetch_one(self.conn, "User", id="owner")["preferences_json"], original)

    def test_bad_json_and_media_type(self):
        response = self.client.post("/api/v1/reach/show-all", data="{", content_type="application/json")
        self.assertEqual(response.status_code, 400)
        response = self.client.post("/api/v1/reach/show-all", data={"ignore": "true"})
        self.assertEqual(response.status_code, 415)

    def assert_reach_locked(self):
        self.assertEqual(self.client.get("/api/v1/reach").status_code, 403)
        for action in ("ignore", "show-all", "widen", "set-range"):
            response = self.client.post("/api/v1/reach/" + action, json={})
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json["error"]["code"], "reach_locked")

    def test_later_stages_block_reach(self):
        for stage in ("relationship", "engaged", "married"):
            self.conn.execute("UPDATE User SET journey_state = ? WHERE id = ?", (stage, "owner"))
            self.conn.commit()
            self.assert_reach_locked()

    def test_mutual_lockin_blocks_reach_during_dating(self):
        self.make_lockin("owner", "other")
        self.assert_reach_locked()

    def test_routing_errors_are_consistent_json(self):
        for response, status in ((self.client.get("/api/v1/missing"), 404),
                                 (self.client.post("/api/v1/me"), 405)):
            self.assertEqual(response.status_code, status)
            self.assertIsNone(response.json["data"])
            self.assertIsInstance(response.json["error"], dict)
        self.assertIn("GET", self.client.post("/api/v1/me").headers["Allow"])

    def test_unexpected_error_uses_existing_incident_handler(self):
        with mock.patch.object(app_module, "load_user", side_effect=RuntimeError("private diagnostic")):
            response = self.client.get("/api/v1/me")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json["error"]["code"], "internal_error")
        self.assertTrue(response.json["error"]["reference"])
        self.assertNotIn("private diagnostic", response.get_data(as_text=True))

    def test_web_authentication_still_redirects(self):
        with self.client.session_transaction() as session:
            session.clear()
        self.assertEqual(self.client.get("/reach").status_code, 302)

    def test_unavailable_levers_rejected_without_unlocking_or_mutation(self):
        row = db.fetch_one(self.conn, "User", id="owner")
        preferences = json.loads(row["preferences_json"])
        preferences["adjustable"].pop("height_cm", None)
        self.conn.execute("UPDATE User SET preferences_json = ? WHERE id = ?",
                          (json.dumps(preferences), "owner"))
        self.conn.commit()
        for action, payload in (("widen", {"lever": "height_cm"}),
                                ("set-range", {"lever": "height_cm", "min": 160, "max": 190})):
            with self.subTest(action=action):
                response = self.client.post("/api/v1/reach/" + action, json=payload)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json["error"]["code"], "validation_error")
                self.assertEqual(json.loads(db.fetch_one(self.conn, "User", id="owner")["preferences_json"]), preferences)
