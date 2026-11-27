"""Security-sensitive settings shared by application entry points."""
from __future__ import annotations

import os


def require_secret_key(env=None) -> str:
    """Return the configured Flask/session signing key or refuse startup/use."""
    env = os.environ if env is None else env
    value = env.get("SECRET_KEY")
    if not isinstance(value, str) or len(value) < 32 or not value.strip():
        raise RuntimeError("SECRET_KEY must be configured with at least 32 characters.")
    return value
