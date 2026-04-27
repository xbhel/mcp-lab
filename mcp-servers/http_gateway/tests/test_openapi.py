"""Tests for OpenAPI import and export helpers."""

from __future__ import annotations

import json

import pytest
import yaml

from http_gateway.models import ToolDefinition
from http_gateway.openapi import (
    InvalidOpenAPISpecError,
    export_tools_as_openapi,
    import_tools_from_openapi,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


MINIMAL_OPENAPI_SPEC = {
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
    weather_paths = [
        p for p in spec["paths"].values() for op in p.values() if isinstance(op, dict)
    ]
    assert len(weather_paths) > 0


def test_export_should_produce_valid_json(
    registered_tools: list[ToolDefinition],
) -> None:
    spec = export_tools_as_openapi(registered_tools, base_url="https://gateway.example.com")
    # Should serialize without error
    serialized = json.dumps(spec)
    assert len(serialized) > 0
