"""Integration tests for gateway_tools — MCP tool handlers end-to-end."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from http_gateway.gateway_tools import register_gateway_tools
from http_gateway.http_client import HttpDispatcher
from http_gateway.metrics import MetricsCollector
from http_gateway.models import ToolDefinition
from http_gateway.registry import ToolRegistry

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_storage(tmp_path: Path) -> Path:
    return tmp_path / "tools.json"


@pytest.fixture
def registry(tmp_storage: Path) -> ToolRegistry:
    return ToolRegistry(storage_path=tmp_storage)


@pytest.fixture
def dispatcher() -> HttpDispatcher:
    return HttpDispatcher()


@pytest.fixture
def metrics() -> MetricsCollector:
    return MetricsCollector()


@pytest.fixture
def mock_mcp():
    """Minimal FastMCP stub that captures registered tools."""
    from unittest.mock import MagicMock

    mock = MagicMock()
    mock._registered_tools: dict = {}

    def tool_decorator(**kwargs):
        def decorator(fn):
            mock._registered_tools[kwargs.get("name", fn.__name__)] = fn
            return fn
        return decorator

    mock.tool = tool_decorator
    mock.add_tool = MagicMock()
    return mock


# ---------------------------------------------------------------------------
# gateway_register_tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_tool_should_persist_and_return_success(
    registry: ToolRegistry,
    dispatcher: HttpDispatcher,
    metrics: MetricsCollector,
    mock_mcp,
) -> None:
    register_gateway_tools(mock_mcp, registry, dispatcher, metrics)
    handler = mock_mcp._registered_tools["gateway_register_tool"]

    from http_gateway.gateway_tools import RegisterToolInput
    params = RegisterToolInput(
        name="test_get_v1",
        description="Test GET endpoint",
        url="https://example.com/test",
        method="GET",
    )
    result = await handler(params)
    data = json.loads(result)
    assert data["success"] is True
    assert data["tool_name"] == "test_get_v1"
    assert registry.get("test_get_v1") is not None


@pytest.mark.asyncio
async def test_register_tool_should_return_error_on_duplicate(
    registry: ToolRegistry,
    dispatcher: HttpDispatcher,
    metrics: MetricsCollector,
    mock_mcp,
) -> None:
    register_gateway_tools(mock_mcp, registry, dispatcher, metrics)
    handler = mock_mcp._registered_tools["gateway_register_tool"]

    from http_gateway.gateway_tools import RegisterToolInput
    params = RegisterToolInput(
        name="test_get_v1",
        description="Test",
        url="https://example.com/test",
    )
    await handler(params)
    result = await handler(params)
    data = json.loads(result)
    assert data["success"] is False
    assert "already registered" in data["error"]


# ---------------------------------------------------------------------------
# gateway_delete_tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_tool_should_remove_tool_and_return_success(
    registry: ToolRegistry,
    dispatcher: HttpDispatcher,
    metrics: MetricsCollector,
    mock_mcp,
) -> None:
    registry.register(
        ToolDefinition(
            name="to_delete_v1",
            description="Delete me",
            url="https://example.com/delete",
        )
    )
    register_gateway_tools(mock_mcp, registry, dispatcher, metrics)
    handler = mock_mcp._registered_tools["gateway_delete_tool"]

    from http_gateway.gateway_tools import DeleteToolInput
    result = await handler(DeleteToolInput(name="to_delete_v1"))
    data = json.loads(result)
    assert data["success"] is True
    assert registry.get("to_delete_v1") is None


@pytest.mark.asyncio
async def test_delete_tool_should_return_error_when_not_found(
    registry: ToolRegistry,
    dispatcher: HttpDispatcher,
    metrics: MetricsCollector,
    mock_mcp,
) -> None:
    register_gateway_tools(mock_mcp, registry, dispatcher, metrics)
    handler = mock_mcp._registered_tools["gateway_delete_tool"]

    from http_gateway.gateway_tools import DeleteToolInput
    result = await handler(DeleteToolInput(name="nonexistent"))
    data = json.loads(result)
    assert data["success"] is False


# ---------------------------------------------------------------------------
# gateway_list_tools
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_tools_should_return_registered_tools(
    registry: ToolRegistry,
    dispatcher: HttpDispatcher,
    metrics: MetricsCollector,
    mock_mcp,
) -> None:
    registry.register(
        ToolDefinition(
            name="weather_v1",
            description="Weather",
            url="https://api.weather.com/forecast",
            tags=["weather"],
        )
    )
    register_gateway_tools(mock_mcp, registry, dispatcher, metrics)
    handler = mock_mcp._registered_tools["gateway_list_tools"]

    from http_gateway.gateway_tools import ListToolsInput
    result = await handler(ListToolsInput())
    data = json.loads(result)
    assert data["total"] == 1
    assert data["items"][0]["name"] == "weather_v1"


@pytest.mark.asyncio
async def test_list_tools_should_include_call_count_from_metrics(
    registry: ToolRegistry,
    dispatcher: HttpDispatcher,
    metrics: MetricsCollector,
    mock_mcp,
) -> None:
    registry.register(
        ToolDefinition(
            name="my_api_v1",
            description="My API",
            url="https://api.example.com/endpoint",
        )
    )
    metrics.record_call("my_api_v1", latency_ms=100.0, success=True)
    metrics.record_call("my_api_v1", latency_ms=200.0, success=False)

    register_gateway_tools(mock_mcp, registry, dispatcher, metrics)
    handler = mock_mcp._registered_tools["gateway_list_tools"]

    from http_gateway.gateway_tools import ListToolsInput
    result = await handler(ListToolsInput())
    data = json.loads(result)
    assert data["items"][0]["call_count"] == 2


# ---------------------------------------------------------------------------
# gateway_get_metrics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_metrics_should_return_per_tool_stats(
    registry: ToolRegistry,
    dispatcher: HttpDispatcher,
    metrics: MetricsCollector,
    mock_mcp,
) -> None:
    metrics.record_call("tool_x", latency_ms=50.0, success=True)
    metrics.record_call("tool_x", latency_ms=150.0, success=False)

    register_gateway_tools(mock_mcp, registry, dispatcher, metrics)
    handler = mock_mcp._registered_tools["gateway_get_metrics"]

    result = await handler()
    data = json.loads(result)
    assert "tool_x" in data
    assert data["tool_x"]["call_count"] == 2
    assert data["tool_x"]["success_count"] == 1
    assert data["tool_x"]["avg_latency_ms"] == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# gateway_import_openapi
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_import_openapi_should_register_tools_from_valid_spec(
    registry: ToolRegistry,
    dispatcher: HttpDispatcher,
    metrics: MetricsCollector,
    mock_mcp,
    tmp_path: Path,
) -> None:
    import json as json_mod

    spec = {
        "openapi": "3.1.0",
        "info": {"title": "Test", "version": "1.0.0"},
        "paths": {
            "/hello": {
                "get": {
                    "operationId": "hello_get",
                    "summary": "Say hello",
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
        "servers": [{"url": "https://api.example.com"}],
    }
    spec_file = tmp_path / "spec.json"
    spec_file.write_text(json_mod.dumps(spec))

    register_gateway_tools(mock_mcp, registry, dispatcher, metrics)
    handler = mock_mcp._registered_tools["gateway_import_openapi"]

    from http_gateway.gateway_tools import ImportOpenAPIInput
    result = await handler(ImportOpenAPIInput(spec_path=str(spec_file)))
    data = json.loads(result)
    assert data["success"] is True
    assert "hello_get" in data["imported"]
    assert registry.get("hello_get") is not None


@pytest.mark.asyncio
async def test_import_openapi_should_return_error_on_missing_file(
    registry: ToolRegistry,
    dispatcher: HttpDispatcher,
    metrics: MetricsCollector,
    mock_mcp,
) -> None:
    register_gateway_tools(mock_mcp, registry, dispatcher, metrics)
    handler = mock_mcp._registered_tools["gateway_import_openapi"]

    from http_gateway.gateway_tools import ImportOpenAPIInput
    result = await handler(ImportOpenAPIInput(spec_path="/nonexistent/spec.json"))
    data = json.loads(result)
    assert data["success"] is False


# ---------------------------------------------------------------------------
# gateway_export_openapi
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_export_openapi_should_include_all_registered_tools(
    registry: ToolRegistry,
    dispatcher: HttpDispatcher,
    metrics: MetricsCollector,
    mock_mcp,
) -> None:
    registry.register(
        ToolDefinition(
            name="export_test_v1",
            description="Export test",
            url="https://api.example.com/export",
        )
    )
    register_gateway_tools(mock_mcp, registry, dispatcher, metrics)
    handler = mock_mcp._registered_tools["gateway_export_openapi"]

    from http_gateway.gateway_tools import ExportOpenAPIInput
    result = await handler(ExportOpenAPIInput())
    spec = json.loads(result)
    assert spec["openapi"].startswith("3.")
    assert "paths" in spec
