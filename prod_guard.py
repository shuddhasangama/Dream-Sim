"""Refuse production startup when test-only switches are enabled.

The guard logs setting names only. It never logs values, which may contain
account identifiers or other operational data.
"""
from __future__ import annotations

import logging
import os

log = logging.getLogger("dhashu.prod_guard")

TRUTHY = frozenset({"1", "true", "yes", "on"})
TEST_SWITCHES = {
    "DHASHU_SIMULATED_CLOCK": "truthy",
    "DHASHU_TESTER_NO_OTP": "truthy",
    "DHASHU_IDENTITY_TEST_AUTO_APPROVE": "truthy",
    "DHASHU_IDENTITY_VERIFICATION_MODE": "simulation",
    "BETA_DATE_SIMULATION_ENABLED": "truthy",
    "DHASHU_ACCELERATED_TEST": "truthy",
    "DHASHU_ASYNC_TEST": "truthy",
    "DHASHU_FIXED_TEST_PAIRS": "nonempty",
}
PRODUCTION_ENVIRONMENTS = (
    "RAILWAY_ENVIRONMENT", "RAILWAY_ENVIRONMENT_NAME", "DHASHU_ENVIRONMENT",
    "APP_ENV", "ENVIRONMENT", "FLASK_ENV", "NODE_ENV",
)


def production(env=None) -> bool:
    """Whether the supplied environment explicitly identifies production."""
    env = os.environ if env is None else env
    return any(str(env.get(name, "")).strip().lower() in {"prod", "production"}
               for name in PRODUCTION_ENVIRONMENTS)


def enabled_test_switches(env=None) -> list[str]:
    """Return active test setting names in stable order, without their values."""
    env = os.environ if env is None else env
    active = []
    for name, kind in TEST_SWITCHES.items():
        value = str(env.get(name, "")).strip()
        if ((kind == "truthy" and value.lower() in TRUTHY)
                or (kind == "simulation" and value.lower() == "simulation")
                or (kind == "nonempty" and bool(value))):
            active.append(name)
    return sorted(active)


def assert_safe_startup(env=None) -> None:
    """Fail closed in production if any test-only behavior is configured."""
    env = os.environ if env is None else env
    if not production(env):
        return
    active = enabled_test_switches(env)
    if not active:
        return
    for name in active:
        log.error("Production startup refused: test-only setting %s is enabled", name)
    raise RuntimeError("Test-only settings are forbidden in production: " + ", ".join(active))
