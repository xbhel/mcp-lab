from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from http2mcp._internal_utils import substitute_env_vars

DEFAULT_WORK_DIR = Path.home() / ".http2mcp"
DEFAULT_CONFIG_PATH = DEFAULT_WORK_DIR / "config.toml"


class MCPConfig(BaseModel):
    """Resolved flat configuration for the HTTP adaptor server."""

    model_config = ConfigDict(extra="forbid")

    work_dir: Path = Field(
        default=DEFAULT_WORK_DIR,
        description="Base directory for persistent server state. Defaults to ~/.http2mcp.",
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

    @property
    def tools_storage_path(self) -> Path:
        """Return the resolved path to the tool registry JSON file."""
        return self.work_dir / "tools.json"

    @property
    def metrics_storage_path(self) -> Path:
        """Return the resolved path to the metrics JSON file."""
        return self.work_dir / "metrics.json"


def load_mcp_config(path: Path | str | None = None) -> MCPConfig:
    """Load MCP configuration from a TOML file and return a validated config object."""

    config_path = Path(path).expanduser() if path else DEFAULT_CONFIG_PATH

    # Use defaults if no explicit config file exists
    if path is None and not config_path.exists():
        return MCPConfig()

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found at {config_path}")

    with config_path.open("rb") as config_file:
        raw = tomllib.load(config_file)

    conf = substitute_env_vars(raw)
    mcp_section = conf.get("mcp")

    # Fallback to defaults if [mcp] section is missing or malformed
    if not isinstance(mcp_section, dict):
        return MCPConfig()

    return MCPConfig.model_validate(mcp_section)
