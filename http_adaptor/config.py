from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

_ENV_VAR_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class MCPConfig(BaseModel):
    """Resolved flat configuration for the HTTP adaptor server."""

    model_config = ConfigDict(extra="forbid")

    storage_path: Path = Field(
        default=Path.home() / ".http_adaptor" / "tools.json",
        description=("Path to the tool registry file. Defaults to ~/.http_adaptor/tools.json."),
    )
    transport: Literal["stdio", "sse"] = Field(
        default="stdio",
        description="Public transport value used by the server entry point.",
    )
    host: str = Field(
        default="127.0.0.1",
        description="Host to bind when using SSE transport.",
        min_length=1,
    )
    port: int = Field(
        default=8000,
        description="Port to bind when using SSE transport.",
        ge=1,
        le=65535,
    )
    timeout_seconds: float = Field(
        default=30.0,
        description="Default timeout used when a tool does not set one explicitly.",
        gt=0,
        le=300.0,
    )
    retry_max_attempts: int = Field(
        default=3,
        description="Default retry count used when a tool does not set one explicitly.",
        ge=1,
        le=10,
    )


def load_mcp_config(path: Path | str) -> MCPConfig:
    """Load a config file and return a typed config object."""
    path = Path(path).expanduser()
    if not path.exists():
        return MCPConfig()  # Return defaults if config file is missing.

    with path.open("rb") as f:
        raw = tomllib.load(f)
    raw = _replace_env_vars(raw)

    mcp_section = raw.get("mcp", {})
    # Return defaults if no valid [mcp] section is present.
    if not isinstance(mcp_section, dict):
        return MCPConfig()

    return MCPConfig.model_validate(mcp_section)


def _resolve_match(m: re.Match[str]) -> str:
    env_name = m.group(1)
    env_value = os.getenv(env_name)
    if env_value is None:
        raise ValueError(f"Environment variable '{env_name}' referenced in config file is not set.")
    return env_value


def _replace_env_vars(obj: Any) -> Any:
    """Recursively replace ``${VAR}`` placeholders with environment variable values.

    Raises :class:`ValueError` if a referenced environment variable is not set.
    """
    if isinstance(obj, str):
        return _ENV_VAR_RE.sub(_resolve_match, obj)
    if isinstance(obj, list):
        return [_replace_env_vars(item) for item in obj]
    if isinstance(obj, dict):
        return {key: _replace_env_vars(value) for key, value in obj.items()}
    return obj
