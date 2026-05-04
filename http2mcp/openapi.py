"""OpenAPI import and export helpers.

Import: parse an OpenAPI 3.x spec (JSON or YAML) from a file path
        and return a list of ToolDefinition instances.
Export: convert a list of ToolDefinition instances into an OpenAPI 3.1
        spec dict suitable for serialization to JSON or YAML.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import yaml

from http2mcp.exceptions import InvalidOpenAPISpecError
from http2mcp.models import HttpMethod, ToolDefinition

# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


def import_tools_from_openapi(
    spec_path: str,
    *,
    filter_tags: list[str] | None = None,
    base_url_override: str | None = None,
) -> list[ToolDefinition]:
    """Parse an OpenAPI 3.x spec file and return ToolDefinition list.

    Args:
        spec_path: Absolute or relative path to the spec file (.json or .yaml/.yml).
        filter_tags: If provided, only operations tagged with one of these are imported.
        base_url_override: Override the server base URL from the spec.

    Returns:
        List of ToolDefinition instances, one per operation.

    Raises:
        FileNotFoundError: If the file does not exist.
        InvalidOpenAPISpecError: If the file is not a valid OpenAPI 3.x spec.
    """
    path = Path(spec_path)
    if not path.exists():
        raise FileNotFoundError(f"OpenAPI spec file not found: '{spec_path}'")

    raw = path.read_text(encoding="utf-8")
    spec = _parse_spec(raw, path.suffix)
    _validate_openapi_spec(spec)

    base_url = base_url_override or _extract_base_url(spec)
    filter_tag_set = set(filter_tags) if filter_tags else None

    tools: list[ToolDefinition] = []
    for path_str, path_item in spec.get("paths", {}).items():
        for method, operation in path_item.items():
            if method.upper() not in HttpMethod.__members__:
                continue
            if not isinstance(operation, dict):
                continue

            op_tags = set(operation.get("tags", []))
            if filter_tag_set and not filter_tag_set.intersection(op_tags):
                continue

            operation_id = operation.get("operationId")
            if not operation_id:
                # Generate a name from method + path
                operation_id = (method + path_str).lower().replace("/", "_").strip("_")

            # Sanitize: must match ^[a-z][a-z0-9_]*$
            safe_name = _sanitize_tool_name(operation_id)

            description = operation.get("summary") or operation.get("description") or safe_name
            url = urljoin(base_url.rstrip("/") + "/", path_str.lstrip("/"))

            input_schema = _build_input_schema(operation)

            tools.append(
                ToolDefinition(
                    name=safe_name,
                    description=description[:1024],
                    url=url,
                    method=method.upper(),
                    tags=list(op_tags),
                    input_schema=input_schema,
                )
            )

    return tools


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def export_tools_as_openapi(
    tools: list[ToolDefinition],
    *,
    base_url: str = "https://localhost",
    title: str = "http2mcp MCP Tools",
    version: str = "1.0.0",
) -> dict[str, Any]:
    """Export registered tools as an OpenAPI 3.1 spec dict.

    Args:
        tools: List of registered ToolDefinition instances.
        base_url: The base server URL to include in the spec.
        title: API title for the spec info block.
        version: API version string.

    Returns:
        A dict representing a valid OpenAPI 3.1 document.
    """
    paths: dict[str, Any] = defaultdict(dict)

    for tool in tools:
        # Derive a path from the tool URL relative to base_url
        path_key = _url_to_path(tool.url, base_url)
        method = tool.method.lower()

        operation: dict[str, Any] = {
            "operationId": tool.name,
            "summary": tool.description,
            "tags": tool.tags,
            "responses": {"200": {"description": "Successful response"}},
        }

        if tool.input_schema:
            if method in ("get", "head", "delete"):
                # Represent input schema properties as query parameters
                props = tool.input_schema.get("properties", {})
                required = set(tool.input_schema.get("required", []))
                operation["parameters"] = [
                    {
                        "name": name,
                        "in": "query",
                        "required": name in required,
                        "schema": schema,
                    }
                    for name, schema in props.items()
                ]
            else:
                operation["requestBody"] = {
                    "required": True,
                    "content": {"application/json": {"schema": tool.input_schema}},
                }

        if tool.output_schema:
            operation["responses"]["200"]["content"] = {
                "application/json": {"schema": tool.output_schema}
            }

        paths[path_key][method] = operation

    return {
        "openapi": "3.1.0",
        "info": {"title": title, "version": version},
        "servers": [{"url": base_url}],
        "paths": dict(paths),
    }


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _parse_spec(raw: str, suffix: str) -> dict[str, Any]:
    if suffix in (".yaml", ".yml"):
        return yaml.safe_load(raw)  # type: ignore[no-any-return]
    try:
        return json.loads(raw)  # type: ignore[no-any-return]
    except json.JSONDecodeError:
        return yaml.safe_load(raw)  # type: ignore[no-any-return]


def _validate_openapi_spec(spec: dict[str, Any]) -> None:
    if not isinstance(spec, dict) or "openapi" not in spec:
        raise InvalidOpenAPISpecError(
            "Invalid OpenAPI spec: missing required 'openapi' field. "
            "Ensure the file conforms to OpenAPI 3.x."
        )


def _extract_base_url(spec: dict[str, Any]) -> str:
    servers = spec.get("servers", [])
    if servers and isinstance(servers[0], dict):
        return str(servers[0].get("url", "https://localhost"))
    return "https://localhost"


def _sanitize_tool_name(name: str) -> str:
    """Convert an operationId into a valid MCP tool name (snake_case)."""
    # Replace non-alphanumeric with underscore, lowercase
    sanitized = re.sub(r"[^a-z0-9_]", "_", name.lower())
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    if not sanitized or not sanitized[0].isalpha():
        sanitized = "tool_" + sanitized
    return sanitized[:128]


def _build_input_schema(operation: dict[str, Any]) -> dict[str, Any] | None:
    """Build a JSON Schema from operation parameters or requestBody."""
    # requestBody takes precedence over query/path parameters
    body_schema: dict[str, Any] | None = (
        operation.get("requestBody", {})
        .get("content", {})
        .get("application/json", {})
        .get("schema")
    )
    if body_schema is not None:
        return body_schema

    properties: dict[str, Any] = {}
    required: list[str] = []

    for param in operation.get("parameters", []):
        name = param.get("name")
        if name:
            properties[name] = param.get("schema", {"type": "string"})
            if param.get("required"):
                required.append(name)

    if not properties:
        return None

    schema: dict[str, Any] = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def _url_to_path(url: str, base_url: str) -> str:
    """Extract the path portion of url relative to base_url."""
    base = base_url.rstrip("/")
    if url.startswith(base):
        path = url[len(base) :]
        return path if path.startswith("/") else "/" + path
    # Fallback: extract path from url
    parsed = urlparse(url)
    return parsed.path or "/"
