"""Signing key, auth-default, and local-only database configuration tests."""
from __future__ import annotations

import os
import unittest
from unittest import mock

from flask import Flask

import auth
import auth_delivery
import db
import local_harness
import security_config
import signup_verification


class SecretKeyTests(unittest.TestCase):
    def test_secret_key_requires_32_characters(self):
        for value in (None, "", "short", " " * 40):
            env = {} if value is None else {"SECRET_KEY": value}
            with self.subTest(length=None if value is None else len(value)):
                with self.assertRaisesRegex(RuntimeError, "SECRET_KEY"):
                    security_config.require_secret_key(env)
        key = "k" * 32
        self.assertEqual(security_config.require_secret_key({"SECRET_KEY": key}), key)

    def test_signup_verification_has_no_embedded_key_fallback(self):
        for env in ({}, {"SECRET_KEY": "too-short"}):
            with mock.patch.dict(os.environ, env, clear=True):
                with self.assertRaisesRegex(RuntimeError, "SECRET_KEY"):
                    signup_verification._pepper()


class AuthConfigurationTests(unittest.TestCase):
    def test_missing_auth_setting_defaults_on(self):
        app = Flask("auth-default")
        app.secret_key = "test-only-secret-key-at-least-32-characters"
        with mock.patch.dict(os.environ, {
            "SECRET_KEY": app.secret_key,
            "AUTH_PUBLIC_ORIGIN": "https://app.example.test",
        }, clear=True), mock.patch.object(auth_delivery, "configured", return_value=True):
            auth.register_auth(app, lambda: None)
        self.assertTrue(app.config["AUTH_ENABLED"])

    def test_explicit_auth_off_requires_local_harness_flag(self):
        app = Flask("auth-off-refused")
        with mock.patch.dict(os.environ, {"AUTH_ENABLED": "0"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "DHASHU_LOCAL_HARNESS=1"):
                auth.register_auth(app, lambda: None)

    def test_auth_off_is_localhost_only_and_fails_closed_without_harness(self):
        app = Flask("auth-local-only")
        app.config.update(AUTH_ENABLED=False, LOCAL_HARNESS_ACTIVE=True)
        env = {"AUTH_ENABLED": "0", "DHASHU_LOCAL_HARNESS": "1"}
        with mock.patch.dict(os.environ, env, clear=True):
            with app.test_request_context("/", headers={"Host": "localhost"},
                                          environ_base={"REMOTE_ADDR": "127.0.0.1"}):
                self.assertFalse(auth.enabled())
            with app.test_request_context("/", headers={"Host": "outside.example"},
                                          environ_base={"REMOTE_ADDR": "127.0.0.1"}):
                self.assertTrue(auth.enabled())
        with mock.patch.dict(os.environ, {"AUTH_ENABLED": "0"}, clear=True):
            with app.test_request_context("/", headers={"Host": "localhost"},
                                          environ_base={"REMOTE_ADDR": "127.0.0.1"}):
                self.assertTrue(auth.enabled())


class DatabaseConfigurationTests(unittest.TestCase):
    def test_default_database_requires_postgresql_outside_local_harness(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "DATABASE_URL"):
                db.get_connection()

    def test_non_postgresql_url_is_rejected_outside_local_harness(self):
        with mock.patch.dict(os.environ, {"DATABASE_URL": "sqlite:///tmp/dream.db"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "PostgreSQL"):
                db.get_connection()

    def test_sqlite_is_available_to_the_explicit_local_harness(self):
        with mock.patch.dict(os.environ, {"AUTH_ENABLED": "0", "DHASHU_LOCAL_HARNESS": "1"}, clear=True):
            self.assertTrue(local_harness.active())
            conn = db.get_connection()
            try:
                self.assertEqual(conn.execute("SELECT 1").fetchone()[0], 1)
            finally:
                conn.close()

    def test_explicit_in_memory_database_remains_local_for_isolated_tests(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            conn = db.get_connection(":memory:")
            try:
                self.assertEqual(conn.execute("SELECT 1").fetchone()[0], 1)
            finally:
                conn.close()


if __name__ == "__main__":
    unittest.main()
