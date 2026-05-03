"""Domain models for http-adaptor MCP server.

All modules share these Pydantic models as the single source of truth
for data shapes, validation rules, and serialization.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class HttpMethod(StrEnum):
    """Valid HTTP methods."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"


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
    retry_max_attempts: int | None = Field(
        default=None,
        description=(
            "Maximum number of retry attempts on transient failures. "
            "When omitted, the app-level default is used."
        ),
        ge=1,
        le=10,
    )
    retry_backoff_seconds: float = Field(
        default=1.0,
        description="Initial backoff delay in seconds for exponential retry.",
        gt=0,
        le=60.0,
    )
    timeout_seconds: float | None = Field(
        default=None,
        description=(
            "Request timeout in seconds. When omitted, the app-level default is used."
        ),
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
        if upper not in HttpMethod.__members__:
            raise ValueError(
                f"Invalid HTTP method '{v}'. Must be one of: "
                + ", ".join(sorted(HttpMethod.__members__.keys()))
            )
        return upper

    @field_validator("url")
    @classmethod
    def validate_url(cls, v: str) -> str:
        if not (v.startswith(("http://", "https://"))):
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

    total: int
    count: int
    offset: int
    has_more: bool
    next_offset: int | None
    items: list[ToolDefinition]


# ---------------------------------------------------------------------------
# MCP tool input models
# ---------------------------------------------------------------------------


class RegisterToolInput(BaseModel):
    """Input for registering a new HTTP API as an MCP tool."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(
        ...,
        description=(
            "MCP tool name in snake_case, e.g. 'weather_get_forecast_v1'. "
            "Must be unique. Use a version suffix for multiple versions."
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
    url: str = Field(..., description="Target HTTP endpoint URL (must start with http/https).")
    method: str = Field(
        default="GET",
        description="HTTP method: GET, POST, PUT, PATCH, DELETE, HEAD.",
    )
    headers: dict[str, str] = Field(
        default_factory=dict,
        description="Static headers to include in every request, e.g. Authorization.",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="User-defined tags for grouping, e.g. ['weather', 'public'].",
    )
    input_schema: dict[str, Any] | None = Field(
        default=None,
        description="JSON Schema object describing expected input parameters.",
    )
    output_schema: dict[str, Any] | None = Field(
        default=None,
        description="JSON Schema object describing the expected response shape.",
    )
    retry_max_attempts: int | None = Field(
        default=None,
        description=(
            "Max retry attempts on transient failures (1-10). Uses the app default when omitted."
        ),
        ge=1,
        le=10,
    )
    retry_backoff_seconds: float = Field(
        default=1.0,
        description="Initial retry backoff delay in seconds. Defaults to 1.0.",
        gt=0,
        le=60.0,
    )
    timeout_seconds: float | None = Field(
        default=None,
        description="Request timeout in seconds. Uses the app default when omitted.",
        gt=0,
        le=300.0,
    )


class DeleteToolInput(BaseModel):
    """Input for deleting a registered tool by name."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(..., description="Name of the registered tool to delete.")


class ListToolsInput(BaseModel):
    """Input for listing registered tools with optional tag filtering."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    tags: list[str] | None = Field(
        default=None,
        description="Filter tools by these tags. Returns tools matching ANY tag.",
    )
    limit: int = Field(
        default=50,
        description="Maximum number of tools to return (1-100).",
        ge=1,
        le=100,
    )
    offset: int = Field(
        default=0,
        description="Pagination offset.",
        ge=0,
    )


class ImportOpenAPIInput(BaseModel):
    """Input for importing tools from an OpenAPI 3.x specification file."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    spec_path: str = Field(
        ...,
        description="Absolute path to the OpenAPI 3.x spec file (.json or .yaml).",
    )
    filter_tags: list[str] | None = Field(
        default=None,
        description="Only import operations tagged with one of these. Imports all if omitted.",
    )
    base_url_override: str | None = Field(
        default=None,
        description="Override the server base URL from the spec.",
    )


class ExportOpenAPIInput(BaseModel):
    """Input for exporting all registered tools as an OpenAPI 3.1 spec."""

    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    base_url: str = Field(
        default="http://localhost:8000",
        description="Base server URL to include in the exported spec.",
    )
    title: str = Field(
        default="http-adaptor MCP Tools",
        description="API title for the spec info block.",
    )
