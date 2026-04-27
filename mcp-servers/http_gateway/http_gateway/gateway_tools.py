"""MCP tool handlers for http-gateway.

This module registers all MCP tools using @mcp.tool. Each handler is a thin
layer that validates inputs, delegates to the appropriate service module, and
formats the response for LLM consumption.

Tools:
    gateway_register_tool   — Register a new HTTP API as an MCP tool
    gateway_delete_tool     — Remove a registered tool by name
    gateway_list_tools      — List registered tools with optional tag filter
    gateway_get_metrics     — Retrieve per-tool call metrics
    gateway_import_openapi  — Import tools from an OpenAPI spec
    gateway_export_openapi  — Export all tools as an OpenAPI spec

Dynamic tools (one per registered HTTP API) are added at startup via
server.py, not here.
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field

from http_gateway.http_client import HttpDispatcher
from http_gateway.metrics import MetricsCollector
from http_gateway.models import ToolDefinition
from http_gateway.openapi import (
    InvalidOpenAPISpecError,
    export_tools_as_openapi,
    import_tools_from_openapi,
)
from http_gateway.registry import DuplicateToolError, ToolNotFoundError, ToolRegistry

# ---------------------------------------------------------------------------
# Input models
# ---------------------------------------------------------------------------


class RegisterToolInput(BaseModel):
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
    retry_max_attempts: int = Field(
        default=3,
        description="Max retry attempts on transient failures (1–10).",
        ge=1,
        le=10,
    )
    retry_backoff_seconds: float = Field(
        default=1.0,
        description="Initial retry backoff delay in seconds.",
        gt=0,
        le=60.0,
    )
    timeout_seconds: float = Field(
        default=30.0,
        description="Request timeout in seconds.",
        gt=0,
        le=300.0,
    )


class DeleteToolInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(..., description="Name of the registered tool to delete.")


class ListToolsInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    tags: list[str] | None = Field(
        default=None,
        description="Filter tools by these tags. Returns tools matching ANY tag.",
    )
    limit: int = Field(
        default=50,
        description="Maximum number of tools to return (1–100).",
        ge=1,
        le=100,
    )
    offset: int = Field(
        default=0,
        description="Pagination offset.",
        ge=0,
    )


class ImportOpenAPIInput(BaseModel):
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
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    base_url: str = Field(
        default="https://gateway.localhost",
        description="Base server URL to include in the exported spec.",
    )
    title: str = Field(
        default="http-gateway MCP Tools",
        description="API title for the spec info block.",
    )


# ---------------------------------------------------------------------------
# Tool registration factory
# ---------------------------------------------------------------------------


def register_gateway_tools(
    mcp: FastMCP,
    registry: ToolRegistry,
    dispatcher: HttpDispatcher,
    metrics: MetricsCollector,
) -> None:
    """Register all gateway management tools on the given FastMCP instance."""

    @mcp.tool(
        name="gateway_register_tool",
        annotations=ToolAnnotations(
            title="Register HTTP API as MCP Tool",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def gateway_register_tool(params: RegisterToolInput) -> str:
        """Register a new HTTP API endpoint as an MCP tool.

        After registration, the tool becomes immediately available for invocation
        via its unique name. The definition is persisted to disk and survives
        server restarts.

        Args:
            params (RegisterToolInput): Tool definition including name, URL,
                method, description, optional JSON Schema, tags, retry config.

        Returns:
            str: JSON confirmation with the registered tool name and metadata.
        """
        try:
            tool = ToolDefinition(**params.model_dump())
            registry.register(tool)
            # Dynamically add the invocable tool to MCP
            _add_dynamic_tool(mcp, tool, dispatcher, metrics)
            return json.dumps(
                {
                    "success": True,
                    "message": f"Tool '{tool.name}' registered successfully.",
                    "tool_name": tool.name,
                },
                indent=2,
            )
        except DuplicateToolError as exc:
            return json.dumps({"success": False, "error": str(exc)}, indent=2)
        except Exception as exc:
            return json.dumps(
                {"success": False, "error": f"Failed to register tool: {exc}"}, indent=2
            )

    @mcp.tool(
        name="gateway_delete_tool",
        annotations=ToolAnnotations(
            title="Delete Registered MCP Tool",
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )
    async def gateway_delete_tool(params: DeleteToolInput) -> str:
        """Remove a registered HTTP API tool by name.

        The tool is immediately removed from the MCP tool list and its
        definition is deleted from disk. Clients will receive a
        tools/list_changed notification.

        Args:
            params (DeleteToolInput): The name of the tool to delete.

        Returns:
            str: JSON confirmation or error.
        """
        try:
            registry.delete(params.name)
            return json.dumps(
                {
                    "success": True,
                    "message": f"Tool '{params.name}' deleted successfully.",
                },
                indent=2,
            )
        except ToolNotFoundError as exc:
            return json.dumps({"success": False, "error": str(exc)}, indent=2)

    @mcp.tool(
        name="gateway_list_tools",
        annotations=ToolAnnotations(
            title="List Registered MCP Tools",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def gateway_list_tools(params: ListToolsInput) -> str:
        """List all registered HTTP API tools with optional tag filtering.

        Returns a paginated list including tool name, description, URL,
        method, tags, and invocation count from metrics.

        Args:
            params (ListToolsInput): Optional tag filter and pagination params.

        Returns:
            str: JSON paginated list of tool summaries.
        """
        result = registry.list_tools(
            tags=params.tags,
            limit=params.limit,
            offset=params.offset,
        )
        all_metrics = metrics.all_metrics()
        items = []
        for tool in result.items:
            m = all_metrics.get(tool.name)
            items.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "url": tool.url,
                    "method": tool.method,
                    "tags": tool.tags,
                    "call_count": m.call_count if m else 0,
                    "success_rate": round(m.success_rate, 4) if m else None,
                }
            )
        return json.dumps(
            {
                "total": result.total,
                "count": result.count,
                "offset": result.offset,
                "has_more": result.has_more,
                "next_offset": result.next_offset,
                "items": items,
            },
            indent=2,
        )

    @mcp.tool(
        name="gateway_get_metrics",
        annotations=ToolAnnotations(
            title="Get Tool Call Metrics",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def gateway_get_metrics() -> str:
        """Return per-tool invocation metrics.

        Metrics include: call count, success count, error count,
        average latency (ms), and 95th-percentile latency (ms).
        Metrics are in-memory only and reset on server restart.

        Returns:
            str: JSON dict mapping tool name to metric summary.
        """
        data = {}
        for name, entry in metrics.all_metrics().items():
            data[name] = {
                "call_count": entry.call_count,
                "success_count": entry.success_count,
                "error_count": entry.error_count,
                "success_rate": round(entry.success_rate, 4),
                "avg_latency_ms": round(entry.avg_latency_ms, 2),
                "p95_latency_ms": round(entry.p95_latency_ms, 2),
            }
        return json.dumps(data, indent=2)

    @mcp.tool(
        name="gateway_import_openapi",
        annotations=ToolAnnotations(
            title="Import Tools from OpenAPI Spec",
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=True,
        ),
    )
    async def gateway_import_openapi(params: ImportOpenAPIInput) -> str:
        """Import HTTP API tools from an OpenAPI 3.x specification file.

        Parses the spec and auto-registers each operation as an MCP tool.
        Operations are skipped if their name conflicts with an existing tool.

        Args:
            params (ImportOpenAPIInput): Path to OpenAPI spec, optional tag
                filter, and optional base URL override.

        Returns:
            str: JSON summary of imported, skipped, and failed tools.
        """
        try:
            tools = import_tools_from_openapi(
                params.spec_path,
                filter_tags=params.filter_tags,
                base_url_override=params.base_url_override,
            )
        except FileNotFoundError as exc:
            return json.dumps({"success": False, "error": str(exc)}, indent=2)
        except InvalidOpenAPISpecError as exc:
            return json.dumps({"success": False, "error": str(exc)}, indent=2)

        imported, skipped, failed = [], [], []
        for tool in tools:
            try:
                registry.register(tool)
                _add_dynamic_tool(mcp, tool, dispatcher, metrics)
                imported.append(tool.name)
            except DuplicateToolError:
                skipped.append(tool.name)
            except Exception as exc:
                failed.append({"name": tool.name, "error": str(exc)})

        return json.dumps(
            {
                "success": True,
                "imported": imported,
                "skipped_duplicates": skipped,
                "failed": failed,
                "summary": (
                    f"Imported {len(imported)}, skipped {len(skipped)}, "
                    f"failed {len(failed)} out of {len(tools)} operations."
                ),
            },
            indent=2,
        )

    @mcp.tool(
        name="gateway_export_openapi",
        annotations=ToolAnnotations(
            title="Export Tools as OpenAPI Spec",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    async def gateway_export_openapi(params: ExportOpenAPIInput) -> str:
        """Export all registered tools as an OpenAPI 3.1 specification.

        Useful for integrating the gateway with other systems or generating
        client SDKs.

        Args:
            params (ExportOpenAPIInput): Base URL and title for the spec.

        Returns:
            str: OpenAPI 3.1 spec serialized as a JSON string.
        """
        all_tools = registry.all()
        spec = export_tools_as_openapi(
            all_tools,
            base_url=params.base_url,
            title=params.title,
        )
        return json.dumps(spec, indent=2)


# ---------------------------------------------------------------------------
# Dynamic tool loader
# ---------------------------------------------------------------------------


def load_dynamic_tools(
    mcp: FastMCP,
    registry: ToolRegistry,
    dispatcher: HttpDispatcher,
    metrics: MetricsCollector,
) -> None:
    """Register one MCP tool per entry in the registry at startup."""
    for tool in registry.all():
        _add_dynamic_tool(mcp, tool, dispatcher, metrics)


def _add_dynamic_tool(
    mcp: FastMCP,
    tool: ToolDefinition,
    dispatcher: HttpDispatcher,
    metrics: MetricsCollector,
) -> None:
    """Dynamically add a single registered HTTP API as an MCP tool."""
    import time

    tool_name = tool.name
    tool_description = tool.description

    # Build an async handler for this tool
    async def _handler(**kwargs: Any) -> str:
        params = dict(kwargs)
        start = time.perf_counter()
        result = await dispatcher.invoke(tool, params)
        latency_ms = (time.perf_counter() - start) * 1000
        metrics.record_call(tool_name, latency_ms=latency_ms, success=result.is_success)

        if not result.is_success:
            return json.dumps(
                {
                    "error": result.error,
                    "status_code": result.status_code,
                    "retries": result.retries,
                    "tool": tool_name,
                },
                indent=2,
            )
        return json.dumps(
            {
                "status_code": result.status_code,
                "body": result.body,
                "latency_ms": round(result.latency_ms, 2),
                "retries": result.retries,
            },
            indent=2,
        )

    # Use FastMCP's add_tool with a custom function and schema
    mcp.add_tool(
        fn=_handler,
        name=tool_name,
        description=tool_description,
    )
