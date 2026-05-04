"""Integration tests for gateway_tools — MCP tool handlers end-to-end."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from http2mcp.config import MCPConfig
from http2mcp.http_client import HttpDispatcher
from http2mcp.metrics import MetricsCollector
from http2mcp.models import InvokeResult, ToolDefinition
from http2mcp.registry import ToolRegistry
from http2mcp.tools import register_mcp_tools

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
    return HttpDispatcher(client=MagicMock(spec=httpx.AsyncClient), config=MCPConfig())


@pytest.fixture
def metrics(tmp_path: Path) -> MetricsCollector:
    return MetricsCollector(tmp_path / "metrics.json")


@pytest.fixture
def mock_mcp():
    """Minimal FastMCP stub that captures registered tools."""
    mock = MagicMock()
    mock._registered_tools = {}

    def tool_decorator(**kwargs):
        def decorator(fn):
            mock._registered_tools[kwargs.get("name", fn.__name__)] = fn
            return fn

        return decorator

    mock.tool = tool_decorator
    mock.add_tool = MagicMock()
    return mock


# ---------------------------------------------------------------------------
# http2mcp_register_tool
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_register_tool_should_persist_and_return_success(
    registry: ToolRegistry,
    dispatcher: HttpDispatcher,
    metrics: MetricsCollector,
    mock_mcp,
) -> None:
    register_mcp_tools(mock_mcp, registry, dispatcher, metrics)
    handler = mock_mcp._registered_tools["http2mcp_register_tool"]

    from http2mcp.models import RegisterToolInput

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
async def test_register_tool_should_preserve_timeout_and_retry_omission_when_omitted(
    registry: ToolRegistry,
    dispatcher: HttpDispatcher,
    metrics: MetricsCollector,
    mock_mcp,
) -> None:
    register_mcp_tools(mock_mcp, registry, dispatcher, metrics)
    handler = mock_mcp._registered_tools["http2mcp_register_tool"]

    from http2mcp.models import RegisterToolInput

    params = RegisterToolInput(
        name="defaults_test_v1",
        description="Defaults test",
        url="https://example.com/test",
    )
    result = await handler(params)
    data = json.loads(result)
    assert data["success"] is True
    stored = registry.get("defaults_test_v1")
    assert stored is not None
    assert stored.method == "GET"
    assert stored.retry_max_attempts is None
    assert stored.retry_backoff_seconds == 1.0
    assert stored.timeout_seconds is None


@pytest.mark.asyncio
async def test_register_tool_should_return_error_on_duplicate(
    registry: ToolRegistry,
    dispatcher: HttpDispatcher,
    metrics: MetricsCollector,
    mock_mcp,
) -> None:
    register_mcp_tools(mock_mcp, registry, dispatcher, metrics)
    handler = mock_mcp._registered_tools["http2mcp_register_tool"]

    from http2mcp.models import RegisterToolInput

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


@pytest.mark.asyncio
async def test_register_tool_should_return_error_when_registry_write_fails(
    dispatcher: HttpDispatcher,
    metrics: MetricsCollector,
    mock_mcp,
) -> None:
    broken_registry = MagicMock()
    broken_registry.register.side_effect = RuntimeError("disk full")

    register_mcp_tools(mock_mcp, broken_registry, dispatcher, metrics)
    handler = mock_mcp._registered_tools["http2mcp_register_tool"]

    from http2mcp.models import RegisterToolInput

    result = await handler(
        RegisterToolInput(
            name="broken_tool_v1",
            description="Broken write path",
            url="https://example.com/broken",
        )
    )

    data = json.loads(result)
    assert data["success"] is False
    assert "Failed to register tool" in data["error"]


# ---------------------------------------------------------------------------
# http2mcp_delete_tool
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
    register_mcp_tools(mock_mcp, registry, dispatcher, metrics)
    handler = mock_mcp._registered_tools["http2mcp_delete_tool"]

    from http2mcp.models import DeleteToolInput

    result = await handler(DeleteToolInput(name="to_delete_v1"))
    data = json.loads(result)
    assert data["success"] is True
    assert registry.get("to_delete_v1") is None
    mock_mcp.remove_tool.assert_called_once_with("to_delete_v1")


@pytest.mark.asyncio
async def test_delete_tool_should_return_error_when_not_found(
    registry: ToolRegistry,
    dispatcher: HttpDispatcher,
    metrics: MetricsCollector,
    mock_mcp,
) -> None:
    register_mcp_tools(mock_mcp, registry, dispatcher, metrics)
    handler = mock_mcp._registered_tools["http2mcp_delete_tool"]

    from http2mcp.models import DeleteToolInput

    result = await handler(DeleteToolInput(name="nonexistent"))
    data = json.loads(result)
    assert data["success"] is False


# ---------------------------------------------------------------------------
# http2mcp_list_tools
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
    register_mcp_tools(mock_mcp, registry, dispatcher, metrics)
    handler = mock_mcp._registered_tools["http2mcp_list_tools"]

    from http2mcp.models import ListToolsInput

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

    register_mcp_tools(mock_mcp, registry, dispatcher, metrics)
    handler = mock_mcp._registered_tools["http2mcp_list_tools"]

    from http2mcp.models import ListToolsInput

    result = await handler(ListToolsInput())
    data = json.loads(result)
    assert data["items"][0]["call_count"] == 2


# ---------------------------------------------------------------------------
# http2mcp_get_metrics
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

    register_mcp_tools(mock_mcp, registry, dispatcher, metrics)
    handler = mock_mcp._registered_tools["http2mcp_get_metrics"]

    result = await handler()
    data = json.loads(result)
    assert "tool_x" in data
    assert data["tool_x"]["call_count"] == 2
    assert data["tool_x"]["success_count"] == 1
    assert data["tool_x"]["avg_latency_ms"] == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# http2mcp_import_openapi
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

    register_mcp_tools(mock_mcp, registry, dispatcher, metrics)
    handler = mock_mcp._registered_tools["http2mcp_import_openapi"]

    from http2mcp.models import ImportOpenAPIInput

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
    register_mcp_tools(mock_mcp, registry, dispatcher, metrics)
    handler = mock_mcp._registered_tools["http2mcp_import_openapi"]

    from http2mcp.models import ImportOpenAPIInput

    result = await handler(ImportOpenAPIInput(spec_path="/nonexistent/spec.json"))
    data = json.loads(result)
    assert data["success"] is False


@pytest.mark.asyncio
async def test_import_openapi_should_collect_failed_tools_when_registry_write_fails(
    dispatcher: HttpDispatcher,
    metrics: MetricsCollector,
    mock_mcp,
    tmp_path: Path,
) -> None:
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
    spec_file.write_text(json.dumps(spec))

    broken_registry = MagicMock()
    broken_registry.register.side_effect = RuntimeError("write failed")

    register_mcp_tools(mock_mcp, broken_registry, dispatcher, metrics)
    handler = mock_mcp._registered_tools["http2mcp_import_openapi"]

    from http2mcp.models import ImportOpenAPIInput

    result = await handler(ImportOpenAPIInput(spec_path=str(spec_file)))

    data = json.loads(result)
    assert data["success"] is True
    assert data["imported"] == []
    assert data["skipped_duplicates"] == []
    assert data["failed"] == [{"name": "hello_get", "error": "write failed"}]


@pytest.mark.asyncio
async def test_load_dynamic_tools_should_register_each_persisted_tool(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    import http2mcp.tools as tools_module

    mcp = MagicMock()
    registry = MagicMock()
    dispatcher = MagicMock()
    metrics = MetricsCollector(tmp_path / "metrics.json")
    persisted_tools = [
        ToolDefinition(
            name="weather_lookup",
            description="Weather lookup",
            url="https://example.com/weather",
        ),
        ToolDefinition(
            name="news_lookup",
            description="News lookup",
            url="https://example.com/news",
        ),
    ]
    registry.all.return_value = persisted_tools
    add_dynamic_tool = MagicMock()

    monkeypatch.setattr(tools_module, "_add_dynamic_tool", add_dynamic_tool)

    tools_module.load_dynamic_tools(mcp, registry, dispatcher, metrics)

    assert add_dynamic_tool.call_count == 2
    add_dynamic_tool.assert_any_call(mcp, persisted_tools[0], dispatcher, metrics)
    add_dynamic_tool.assert_any_call(mcp, persisted_tools[1], dispatcher, metrics)


@pytest.mark.asyncio
async def test_add_dynamic_tool_should_return_success_payload_and_record_metrics(
    tmp_path: Path,
) -> None:
    import http2mcp.tools as tools_module

    mcp = MagicMock()
    dispatcher = MagicMock()
    dispatcher.invoke = AsyncMock(
        return_value=InvokeResult(
            tool_name="weather_lookup",
            status_code=200,
            body={"temp_c": 18},
            latency_ms=12.345,
            retries=1,
        )
    )
    metrics = MetricsCollector(tmp_path / "metrics.json")
    tool = ToolDefinition(
        name="weather_lookup",
        description="Weather lookup",
        url="https://example.com/weather",
    )

    tools_module._add_dynamic_tool(mcp, tool, dispatcher, metrics)
    handler = mcp.add_tool.call_args.kwargs["fn"]

    result = await handler(city="Paris")

    data = json.loads(result)
    entry = metrics.get("weather_lookup")
    assert data == {
        "status_code": 200,
        "body": {"temp_c": 18},
        "latency_ms": 12.35,
        "retries": 1,
    }
    assert entry is not None
    assert entry.call_count == 1
    assert entry.success_count == 1
    dispatcher.invoke.assert_awaited_once_with(tool, {"city": "Paris"})


@pytest.mark.asyncio
async def test_add_dynamic_tool_should_return_error_payload_and_record_failure_metrics(
    tmp_path: Path,
) -> None:
    import http2mcp.tools as tools_module

    mcp = MagicMock()
    dispatcher = MagicMock()
    dispatcher.invoke = AsyncMock(
        return_value=InvokeResult(
            tool_name="weather_lookup",
            status_code=503,
            body="",
            latency_ms=9.876,
            retries=2,
            error="Service unavailable",
        )
    )
    metrics = MetricsCollector(tmp_path / "metrics.json")
    tool = ToolDefinition(
        name="weather_lookup",
        description="Weather lookup",
        url="https://example.com/weather",
    )

    tools_module._add_dynamic_tool(mcp, tool, dispatcher, metrics)
    handler = mcp.add_tool.call_args.kwargs["fn"]

    result = await handler(city="Paris")

    data = json.loads(result)
    entry = metrics.get("weather_lookup")
    assert data == {
        "error": "Service unavailable",
        "status_code": 503,
        "retries": 2,
        "tool": "weather_lookup",
    }
    assert entry is not None
    assert entry.call_count == 1
    assert entry.error_count == 1


# ---------------------------------------------------------------------------
# http2mcp_export_openapi
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
    register_mcp_tools(mock_mcp, registry, dispatcher, metrics)
    handler = mock_mcp._registered_tools["http2mcp_export_openapi"]

    from http2mcp.models import ExportOpenAPIInput

    result = await handler(ExportOpenAPIInput())
    spec = json.loads(result)
    assert spec["openapi"].startswith("3.")
    assert "paths" in spec
    assert spec["servers"][0]["url"] == "http://localhost:8000"
