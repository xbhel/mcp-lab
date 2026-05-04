from __future__ import annotations

import logging
from pathlib import Path
from typing import cast
from unittest.mock import MagicMock

import httpx
import pytest
from mcp.server.fastmcp import FastMCP

import http2mcp.server as server
from http2mcp.config import MCPConfig
from http2mcp.models import ToolDefinition


class _AsyncClientContext:
    def __init__(self, client: object) -> None:
        self._client = client

    async def __aenter__(self) -> object:
        return self._client

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


@pytest.mark.asyncio
async def test_create_server_runtime_lifespan_should_setup_registry_dispatcher_and_register_tools(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = cast("FastMCP", MagicMock(spec=FastMCP))
    config = MCPConfig(
        work_dir=tmp_path,
        transport="sse",
        host="127.0.0.10",
        port=8123,
        timeout_seconds=45.0,
        retry_max_attempts=5,
    )
    persisted_tool = ToolDefinition(
        name="weather_lookup",
        description="Get the weather for a city.",
        url="https://example.com/weather",
    )
    registry = MagicMock()
    registry.all.return_value = [persisted_tool]
    shared_client = object()
    dispatcher = object()
    metrics = MagicMock()
    tool_registry_cls = MagicMock(return_value=registry)
    dispatcher_cls = MagicMock(return_value=dispatcher)
    metrics_cls = MagicMock(return_value=metrics)
    register_mcp_tools = MagicMock()
    load_dynamic_tools = MagicMock()

    monkeypatch.setattr(server, "ToolRegistry", tool_registry_cls)
    monkeypatch.setattr(server, "HttpDispatcher", dispatcher_cls)
    monkeypatch.setattr(server, "MetricsCollector", metrics_cls)
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        MagicMock(return_value=_AsyncClientContext(shared_client)),
    )
    monkeypatch.setattr(server, "register_mcp_tools", register_mcp_tools)
    monkeypatch.setattr(server, "load_dynamic_tools", load_dynamic_tools)

    lifespan = server.create_server_runtime(config=config)

    async with lifespan(app):
        pass

    metrics_cls.assert_called_once_with(config.metrics_storage_path)
    metrics.load.assert_called_once_with(config.metrics_storage_path)
    metrics.save.assert_called_once_with(config.metrics_storage_path)
    tool_registry_cls.assert_called_once_with(storage_path=config.tools_storage_path)
    dispatcher_cls.assert_called_once_with(client=shared_client, config=config)
    register_mcp_tools.assert_called_once_with(app, registry, dispatcher, metrics)
    load_dynamic_tools.assert_called_once_with(
        app,
        registry,
        dispatcher,
        metrics,
    )


def test_create_app_should_create_fastmcp_with_correct_host_and_port(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    config = MCPConfig(
        work_dir=tmp_path,
        transport="sse",
        host="127.0.0.2",
        port=9100,
        timeout_seconds=55.0,
        retry_max_attempts=4,
    )
    fastmcp_app = MagicMock(spec=FastMCP)
    fastmcp_cls = MagicMock(return_value=fastmcp_app)
    lifespan_fn = MagicMock()
    create_runtime = MagicMock(return_value=lifespan_fn)

    monkeypatch.setattr(server, "FastMCP", fastmcp_cls)
    monkeypatch.setattr(server, "create_server_runtime", create_runtime)

    app = server.create_app(config)

    assert app is fastmcp_app
    create_runtime.assert_called_once_with(config)
    _, kwargs = fastmcp_cls.call_args
    assert kwargs["host"] == config.host
    assert kwargs["port"] == config.port
    assert kwargs["lifespan"] is lifespan_fn


@pytest.mark.asyncio
async def test_create_server_runtime_lifespan_should_log_shutdown_after_client_closes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    app = cast("FastMCP", MagicMock(spec=FastMCP))
    config = MCPConfig(work_dir=tmp_path)

    monkeypatch.setattr(server, "MetricsCollector", MagicMock(return_value=MagicMock()))
    monkeypatch.setattr(server, "ToolRegistry", MagicMock())
    monkeypatch.setattr(server, "HttpDispatcher", MagicMock())
    monkeypatch.setattr(server, "register_mcp_tools", MagicMock())
    monkeypatch.setattr(server, "load_dynamic_tools", MagicMock())
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        MagicMock(return_value=_AsyncClientContext(object())),
    )

    lifespan = server.create_server_runtime(config=config)

    with caplog.at_level(logging.INFO, logger="http2mcp"):
        async with lifespan(app):
            pass

    assert any("shutdown" in record.message for record in caplog.records)
