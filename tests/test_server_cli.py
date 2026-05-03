from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

import http_adaptor.server as server
from http_adaptor.config import MCPConfig


def test_main_should_run_sse_when_transport_is_sse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = MCPConfig(
        transport="stdio",
        host="127.0.0.2",
        port=8123,
    )
    app = MagicMock()
    load_config = MagicMock(return_value=config)
    build_app = MagicMock(return_value=app)

    monkeypatch.setattr(server, "load_mcp_config", load_config)
    monkeypatch.setattr(server, "create_app", build_app)
    monkeypatch.setattr(
        sys,
        "argv",
        ["http-adaptor", "--transport", "sse"],
    )

    server.main()

    load_config.assert_called_once()
    build_app.assert_called_once_with(config)
    app.run.assert_called_once_with(transport="sse")


def test_main_should_run_stdio_when_transport_is_stdio(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = MCPConfig(
        transport="stdio",
        host="127.0.0.1",
        port=8000,
    )
    app = MagicMock()

    monkeypatch.setattr(server, "load_mcp_config", MagicMock(return_value=config))
    monkeypatch.setattr(server, "create_app", MagicMock(return_value=app))
    monkeypatch.setattr(sys, "argv", ["http-adaptor"])

    server.main()

    app.run.assert_called_once_with(transport="stdio")
