"""Production startup guards for test-only behavior and missing settings."""
from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

import prod_guard
import service_entrypoint

REPO = Path(__file__).resolve().parent
TEST_SWITCH_VALUES = {
    "DHASHU_SIMULATED_CLOCK": "true",
    "DHASHU_TESTER_NO_OTP": "true",
    "DHASHU_IDENTITY_TEST_AUTO_APPROVE": "1",
    "DHASHU_IDENTITY_VERIFICATION_MODE": "simulation",
    "BETA_DATE_SIMULATION_ENABLED": "1",
    "DHASHU_ACCELERATED_TEST": "true",
    "DHASHU_ASYNC_TEST": "true",
    "DHASHU_FIXED_TEST_PAIRS": "01",
}


class ProductionGuardTests(unittest.TestCase):
    def test_each_test_switch_blocks_production_startup_and_logs_only_its_name(self):
        for name, value in TEST_SWITCH_VALUES.items():
            env = {"RAILWAY_ENVIRONMENT": "production", name: value}
            with self.subTest(name=name), self.assertLogs("dhashu.prod_guard", level="ERROR") as logs:
                with self.assertRaisesRegex(RuntimeError, name):
                    prod_guard.assert_safe_startup(env)
            self.assertTrue(any(name in line for line in logs.output))
            self.assertTrue(all(value not in line for line in logs.output))

    def test_inactive_switch_values_and_nonproduction_environment_are_allowed(self):
        env = {"RAILWAY_ENVIRONMENT": "staging"}
        env.update({name: "false" for name, kind in prod_guard.TEST_SWITCHES.items()
                    if kind == "truthy"})
        env["DHASHU_IDENTITY_VERIFICATION_MODE"] = "disabled"
        env["DHASHU_FIXED_TEST_PAIRS"] = "  "
        self.assertEqual(prod_guard.enabled_test_switches(env), [])
        prod_guard.assert_safe_startup(env)

    def test_service_entrypoint_checks_guard_before_database_or_exec(self):
        env = {"RAILWAY_ENVIRONMENT": "production", "DHASHU_ASYNC_TEST": "1"}
        with mock.patch.dict(os.environ, env, clear=True), \
                mock.patch.object(service_entrypoint, "init_schema") as init_schema, \
                mock.patch.object(service_entrypoint.os, "execvp") as execvp:
            with self.assertRaisesRegex(RuntimeError, "DHASHU_ASYNC_TEST"):
                service_entrypoint.main()
        init_schema.assert_not_called()
        execvp.assert_not_called()

    def test_fresh_service_start_without_settings_refuses_to_boot(self):
        env = {name: value for name, value in os.environ.items()
               if name in ("PATH", "HOME", "TMPDIR", "SYSTEMROOT")}
        env.pop("SECRET_KEY", None)
        env.pop("DATABASE_URL", None)
        result = subprocess.run([sys.executable, "service_entrypoint.py"], cwd=REPO,
                                env=env, capture_output=True, text=True, timeout=30)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("SECRET_KEY", result.stderr)
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
