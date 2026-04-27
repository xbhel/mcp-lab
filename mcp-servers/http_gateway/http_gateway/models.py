"""Domain models for http-gateway MCP server.

All modules share these Pydantic models as the single source of truth
for data shapes, validation rules, and serialization.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class HttpMethod(str):
    """Valid HTTP methods."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"

    ALLOWED = frozenset({"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD"})


# ---------------------------------------------------------------------------
# Core domain models
# ---------------------------------------------------------------------------


class ToolDefinition(BaseModel):
    """Persisted definition of a single registered HTTP API tool."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
        extra="forbid",
    )

    name: str = Field(
        ...,
        description=(
            "MCP tool name in snake_case, optionally versioned with suffix e.g. "
            "'weather_get_forecast_v1'. Must be unique within the registry."
        ),
        min_length=1,
        max_length=128,
        pattern=r"^[a-z][a-z0-9_]*$",
    )
    description: str = Field(
        ...,
        description="Human-readable description shown to LLMs and users.",
        min_length=1,
        max_length=1024,
    )
    url: str = Field(
        ...,
        description="Target HTTP endpoint URL.",
        min_length=1,
    )
    method: str = Field(
        default="GET",
        description="HTTP method: GET, POST, PUT, PATCH, DELETE, HEAD.",
    )
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="Static headers to include in every request.",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="User-defined tags for grouping and filtering.",
        max_length=20,
    )
    input_schema: dict[str, Any] | None = Field(
        default=None,
        description="JSON Schema object describing expected input parameters.",
    )
    output_schema: dict[str, Any] | None = Field(
        default=None,
        description="JSON Schema object describing the expected response shape.",
    )
    api_key_hash: str | None = Field(
        default=None,
        description="bcrypt hash of the required API key. None means no auth required.",
    )
    retry_max_attempts: int = Field(
        default=3,
        description="Maximum number of retry attempts on transient failures.",
        ge=1,
        le=10,
    )
    retry_backoff_seconds: float = Field(
        default=1.0,
        description="Initial backoff delay in seconds for exponential retry.",
        gt=0,
        le=60.0,
    )
    timeout_seconds: float = Field(
        default=30.0,
        description="Request timeout in seconds.",
        gt=0,
        le=300.0,
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp when the tool was registered.",
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        description="UTC timestamp of the last update.",
    )

    @field_validator("method")
    @classmethod
    def validate_method(cls, v: str) -> str:
        upper = v.upper()
        if upper not in HttpMethod.ALLOWED:
            raise ValueError(
                f"Invalid HTTP method '{v}'. Must be one of: "
                + ", ".join(sorted(HttpMethod.ALLOWED))
            )
        return upper

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not (v.startswith("http://") or v.startswith("https://")):
            raise ValueError(f"URL must start with 'http://' or 'https://'. Got: '{v}'")
        return v


class MetricEntry(BaseModel):
    """Per-tool call metrics collected in memory."""

    model_config = ConfigDict(validate_assignment=True)

    tool_name: str
    call_count: int = 0
    success_count: int = 0
    error_count: int = 0
    total_latency_ms: float = 0.0
    latency_samples: list[float] = Field(default_factory=list)

    @property
    def avg_latency_ms(self) -> float:
        """Average latency across all calls."""
        if self.call_count == 0:
            return 0.0
        return self.total_latency_ms / self.call_count

    @property
    def success_rate(self) -> float:
        """Success rate as a float between 0.0 and 1.0."""
        if self.call_count == 0:
            return 0.0
        return self.success_count / self.call_count

    @property
    def p95_latency_ms(self) -> float:
        """95th-percentile latency. Returns 0.0 when no samples."""
        if not self.latency_samples:
            return 0.0
        sorted_samples = sorted(self.latency_samples)
        idx = max(0, int(len(sorted_samples) * 0.95) - 1)
        return sorted_samples[idx]


class InvokeResult(BaseModel):
    """Result returned after invoking a registered HTTP API tool."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str
    status_code: int
    body: str | dict[str, Any]
    latency_ms: float
    retries: int = 0
    error: str | None = None

    @property
    def is_success(self) -> bool:
        return self.error is None and 200 <= self.status_code < 300


class PaginatedToolList(BaseModel):
    """Paginated response for listing registered tools."""

    model_config = ConfigDict(extra="forbid")

    total: int
    count: int
    offset: int
    has_more: bool
    next_offset: int | None
    items: list[ToolDefinition]
