import argparse
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

import httpx
from mcp.server import FastMCP

from http2mcp.config import MCPConfig, load_mcp_config
from http2mcp.http_client import HttpDispatcher
from http2mcp.metrics import MetricsCollector
from http2mcp.registry import ToolRegistry
from http2mcp.tools import load_dynamic_tools, register_mcp_tools

# Logging — write to stderr only (stdout is reserved for stdio MCP transport)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("http2mcp")


type Lifespan = Callable[[FastMCP[Any]], AbstractAsyncContextManager[None]]


def create_app(config: MCPConfig) -> FastMCP:
    """Create a configured FastMCP app from resolved configuration sources."""

    return FastMCP(
        "http2mcp_mcp",
        host=config.host,
        port=config.port,
        lifespan=create_server_runtime(config),
        instructions=(
            "HTTP-to-MCP adapter server. "
            "Register HTTP APIs with http2mcp_register_tool, "
            "list tools with http2mcp_list_tools, "
            "or bulk import APIs with http2mcp_import_openapi. "
            "Registered tools become directly invocable by name."
        ),
    )


def create_server_runtime(
    config: MCPConfig,
) -> Lifespan:
    """Initialize and return the server runtime context."""

    @asynccontextmanager
    async def lifespan(app: FastMCP) -> AsyncIterator[None]:
        metrics = MetricsCollector(config.metrics_storage_path)
        registry = ToolRegistry(storage_path=config.tools_storage_path)
        metrics_path = config.metrics_storage_path
        metrics.load(metrics_path)

        async with httpx.AsyncClient() as client:
            dispatcher = HttpDispatcher(client=client, config=config)
            register_mcp_tools(app, registry, dispatcher, metrics)
            load_dynamic_tools(app, registry, dispatcher, metrics)
            yield
            metrics.save(metrics_path)

        logger.info("http-adaptor shutdown: httpx client closed.")

    return lifespan


def main() -> None:
    """Entry point for running the server."""

    parser = argparse.ArgumentParser(
        description="http2mcp - HTTP-to-MCP adapter server",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--config",
        default=None,
        help="path to http2mcp config file (default: ~/.http2mcp/config.toml).",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default=None,
        help="transport to use for the MCP server (default: stdio).",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="host to bind the MCP server (default: 127.0.0.1).",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="port to bind the MCP server (default: 8000).",
    )

    args = parser.parse_args()

    mcp_config = load_mcp_config(args.config)
    host = args.host or mcp_config.host
    port = args.port or mcp_config.port
    transport = args.transport or mcp_config.transport

    app = create_app(mcp_config.model_copy(update={"host": host, "port": port}))

    logger.info(f"Starting server with transport '{transport}' on {host}:{port}")
    app.run(transport=transport)
