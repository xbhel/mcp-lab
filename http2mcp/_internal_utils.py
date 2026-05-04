"""Shared internal utilities for http2mcp."""

from __future__ import annotations

import os
import re
from typing import Any

_ENV_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


def substitute_env_vars(obj: Any, strict: bool = True) -> Any:
    """Recursively substitute ${VAR} placeholders with environment variables.

    Raises:
        ValueError: if referenced environment variable is not set.
    """

    def _resolve_match(m: re.Match[str]) -> str:
        env_name = m.group(1)
        env_value = os.getenv(env_name)

        if env_value is None:
            if strict:
                raise ValueError(f"Missing required environment variable: {env_name}")
            return m.group(0)  # leave placeholder as-is

        return env_value

    if isinstance(obj, str):
        return _ENV_VAR_RE.sub(_resolve_match, obj)

    if isinstance(obj, list):
        return [substitute_env_vars(item, strict) for item in obj]

    if isinstance(obj, dict):
        return {k: substitute_env_vars(v, strict) for k, v in obj.items()}

    return obj
