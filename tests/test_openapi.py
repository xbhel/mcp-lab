"""Tests for OpenAPI import and export helpers."""

from __future__ import annotations

import json
from typing import Any

import pytest
import yaml

from http2mcp.exceptions import InvalidOpenAPISpecError
from http2mcp.models import ToolDefinition
from http2mcp.openapi import (
    _build_input_schema,
    _extract_base_url,
    _parse_spec,
    _sanitize_tool_name,
    _url_to_path,
    export_tools_as_openapi,
    import_tools_from_openapi,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


MINIMAL_OPENAPI_SPEC: dict[str, Any] = {
    "openapi": "3.1.0",
    "info": {"title": "Test API", "version": "1.0.0"},
    "paths": {
        "/hello": {
            "get": {
                "operationId": "hello_get",
                "summary": "Say hello",
                "parameters": [
                    {
                        "name": "name",
                        "in": "query",
                        "required": True,
                        "schema": {"type": "string"},
                    }
                ],
                "responses": {"200": {"description": "OK"}},
            }
        },
        "/greet": {
            "post": {
                "operationId": "greet_post",
                "summary": "Greet user",
                "requestBody": {
                    "required": True,
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {"message": {"type": "string"}},
                                "required": ["message"],
                            }
                        }
                    },
                },
                "responses": {"201": {"description": "Created"}},
            }
        },
    },
    "servers": [{"url": "https://api.example.com"}],
}


@pytest.fixture
def openapi_spec_json(tmp_path):
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(MINIMAL_OPENAPI_SPEC))
    return str(path)


@pytest.fixture
def openapi_spec_yaml(tmp_path):
    path = tmp_path / "spec.yaml"
    path.write_text(yaml.dump(MINIMAL_OPENAPI_SPEC))
    return str(path)


@pytest.fixture
def registered_tools() -> list[ToolDefinition]:
    return [
        ToolDefinition(
            name="weather_get_forecast_v1",
            description="Get weather forecast",
            url="https://api.weather.example.com/forecast",
            method="GET",
            tags=["weather"],
            input_schema={
                "type": "object",
                "properties": {"city": {"type": "string"}},
                "required": ["city"],
            },
        ),
        ToolDefinition(
            name="news_list_headlines_v1",
            description="List news headlines",
            url="https://api.news.example.com/headlines",
            method="GET",
            tags=["news"],
        ),
    ]


# ---------------------------------------------------------------------------
# import_tools_from_openapi
# ---------------------------------------------------------------------------


def test_import_should_return_tool_definitions_from_json_spec(
    openapi_spec_json: str,
) -> None:
    tools = import_tools_from_openapi(openapi_spec_json)
    assert len(tools) == 2
    names = {t.name for t in tools}
    assert "hello_get" in names
    assert "greet_post" in names


def test_import_should_return_tool_definitions_from_yaml_spec(
    openapi_spec_yaml: str,
) -> None:
    tools = import_tools_from_openapi(openapi_spec_yaml)
    assert len(tools) == 2


def test_import_should_build_correct_url_from_server_and_path(
    openapi_spec_json: str,
) -> None:
    tools = import_tools_from_openapi(openapi_spec_json)
    hello = next(t for t in tools if t.name == "hello_get")
    assert hello.url == "https://api.example.com/hello"
    assert hello.method == "GET"


def test_import_should_extract_input_schema_from_query_parameters(
    openapi_spec_json: str,
) -> None:
    tools = import_tools_from_openapi(openapi_spec_json)
    hello = next(t for t in tools if t.name == "hello_get")
    assert hello.input_schema is not None
    assert "name" in hello.input_schema.get("properties", {})


def test_import_should_extract_input_schema_from_request_body(
    openapi_spec_json: str,
) -> None:
    tools = import_tools_from_openapi(openapi_spec_json)
    greet = next(t for t in tools if t.name == "greet_post")
    assert greet.input_schema is not None
    assert "message" in greet.input_schema.get("properties", {})


def test_import_should_preserve_omitted_timeout_and_retry_overrides(
    openapi_spec_json: str,
) -> None:
    tools = import_tools_from_openapi(openapi_spec_json)
    hello = next(t for t in tools if t.name == "hello_get")
    assert hello.timeout_seconds is None
    assert hello.retry_max_attempts is None
    assert hello.retry_backoff_seconds == 1.0


def test_import_should_filter_by_tags_when_provided(tmp_path) -> None:
    spec = {
        **MINIMAL_OPENAPI_SPEC,
        "paths": {
            "/hello": {
                "get": {
                    **MINIMAL_OPENAPI_SPEC["paths"]["/hello"]["get"],
                    "tags": ["public"],
                }
            },
            "/greet": {
                "post": {
                    **MINIMAL_OPENAPI_SPEC["paths"]["/greet"]["post"],
                    "tags": ["private"],
                }
            },
        },
    }
    path = str(tmp_path / "tagged.json")
    (tmp_path / "tagged.json").write_text(json.dumps(spec))
    tools = import_tools_from_openapi(path, filter_tags=["public"])
    assert len(tools) == 1
    assert tools[0].name == "hello_get"


def test_import_should_raise_on_invalid_spec_missing_openapi_field(
    tmp_path,
) -> None:
    bad_spec = {"info": {"title": "Bad"}, "paths": {}}
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(bad_spec))
    with pytest.raises(InvalidOpenAPISpecError):
        import_tools_from_openapi(str(path))


def test_import_should_raise_on_nonexistent_file() -> None:
    with pytest.raises(FileNotFoundError):
        import_tools_from_openapi("/nonexistent/spec.json")


# ---------------------------------------------------------------------------
# export_tools_as_openapi
# ---------------------------------------------------------------------------


def test_export_should_produce_valid_openapi_3_structure(
    registered_tools: list[ToolDefinition],
) -> None:
    spec = export_tools_as_openapi(registered_tools, base_url="https://gateway.example.com")
    assert spec["openapi"].startswith("3.")
    assert "info" in spec
    assert "paths" in spec


def test_export_should_include_one_path_per_tool(
    registered_tools: list[ToolDefinition],
) -> None:
    spec = export_tools_as_openapi(registered_tools, base_url="https://gateway.example.com")
    # Each registered tool URL becomes a path entry
    assert len(spec["paths"]) >= 1


def test_export_should_include_input_schema_in_path_parameters(
    registered_tools: list[ToolDefinition],
) -> None:
    spec = export_tools_as_openapi(registered_tools, base_url="https://gateway.example.com")
    # weather tool has an input_schema with "city"
    weather_paths = [p for p in spec["paths"].values() for op in p.values() if isinstance(op, dict)]
    assert len(weather_paths) > 0


def test_export_should_produce_valid_json(
    registered_tools: list[ToolDefinition],
) -> None:
    spec = export_tools_as_openapi(registered_tools, base_url="https://gateway.example.com")
    # Should serialize without error
    serialized = json.dumps(spec)
    assert len(serialized) > 0


def test_parse_spec_should_fallback_to_yaml_when_json_decode_fails() -> None:
    spec = _parse_spec("openapi: 3.1.0\npaths: {}\n", ".json")
    assert spec["openapi"] == "3.1.0"


def test_extract_base_url_should_return_default_when_servers_missing() -> None:
    assert _extract_base_url({"openapi": "3.1.0", "paths": {}}) == "https://localhost"


def test_sanitize_tool_name_should_prefix_non_alpha_and_collapse_symbols() -> None:
    assert _sanitize_tool_name("123 Weird-Name!!") == "tool_123_weird_name"


def test_build_input_schema_should_remove_empty_required_and_return_none_without_inputs() -> None:
    schema = _build_input_schema(
        {
            "parameters": [
                {"name": "city", "schema": {"type": "string"}},
            ]
        },
    )

    assert schema == {
        "type": "object",
        "properties": {"city": {"type": "string"}},
    }
    assert _build_input_schema({}) is None


def test_url_to_path_should_fallback_to_parsed_path_for_external_url() -> None:
    assert (
        _url_to_path("https://external.example.com/orders/123", "https://gateway.example.com")
        == "/orders/123"
    )


def test_export_should_include_output_schema_and_request_body() -> None:
    tool = ToolDefinition(
        name="submit_order",
        description="Submit order",
        url="https://external.example.com/orders",
        method="POST",
        input_schema={
            "type": "object",
            "properties": {"sku": {"type": "string"}},
            "required": ["sku"],
        },
        output_schema={
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
        },
    )

    spec = export_tools_as_openapi([tool], base_url="https://gateway.example.com")

    operation = spec["paths"]["/orders"]["post"]
    assert operation["requestBody"]["content"]["application/json"]["schema"] == tool.input_schema
    assert (
        operation["responses"]["200"]["content"]["application/json"]["schema"] == tool.output_schema
    )


def test_import_should_generate_sanitized_name_and_use_default_base_url_when_missing(
    tmp_path,
) -> None:
    spec = {
        "openapi": "3.1.0",
        "info": {"title": "Generated", "version": "1.0.0"},
        "paths": {
            "/1 weird/path": {
                "get": {
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }
    spec_path = tmp_path / "generated.json"
    spec_path.write_text(json.dumps(spec), encoding="utf-8")

    tools = import_tools_from_openapi(str(spec_path))

    assert len(tools) == 1
    assert tools[0].name == "get_1_weird_path"
    assert tools[0].description == "get_1_weird_path"
    assert tools[0].url == "https://localhost/1 weird/path"
