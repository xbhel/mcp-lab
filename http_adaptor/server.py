import argparse
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

import httpx
from mcp.server import FastMCP

from http_adaptor.config import MCPConfig, load_mcp_config
from http_adaptor.http_client import HttpDispatcher
from http_adaptor.metrics import MetricsCollector
from http_adaptor.registry import ToolRegistry
from http_adaptor.tools import load_dynamic_tools, register_mcp_tools

# Logging — write to stderr only (stdout is reserved for stdio MCP transport)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("http_gateway")


def create_app(config: MCPConfig) -> FastMCP:
    """Create a configured FastMCP app from resolved configuration sources."""

    return FastMCP(
        "http_adaptor_mcp",
        host=config.host,
        port=config.port,
        lifespan=create_server_runtime(config),
        instructions=(
            "HTTP-to-MCP adapter server. "
            "Register HTTP APIs with adapter_register_tool, "
            "list tools with adapter_list_tools, "
            "or bulk import APIs with adapter_import_openapi. "
            "Registered tools become directly invocable by name."
        ),
    )


type Lifespan = Callable[[FastMCP[Any]], AbstractAsyncContextManager[None]]


def create_server_runtime(
    config: MCPConfig,
) -> Lifespan:
    """Initialize and return the server runtime context."""

    @asynccontextmanager
    async def lifespan(app: FastMCP) -> AsyncIterator[None]:
        metrics = MetricsCollector()
        registry = ToolRegistry(storage_path=config.storage_path)

        async with httpx.AsyncClient() as client:
            dispatcher = HttpDispatcher(client=client, config=config)
            register_mcp_tools(app, registry, dispatcher, metrics)
            load_dynamic_tools(app, registry, dispatcher, metrics)
            yield
            # Cleanup happens automatically when exiting the context managers.

        logger.info("http-adaptor shutdown: httpx client closed.")

    return lifespan


def main() -> None:
    """Entry point for running the server."""

    parser = argparse.ArgumentParser(
        description="http-adaptor - HTTP-to-MCP adapter server",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--config",
        default="~/.http_adaptor/config.toml",
        help="path to http_adaptor config file (default: ~/.http_adaptor/config.toml).",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default=None,
        help="transport to use for the MCP server (overrides config file).",
    )
    args = parser.parse_args()
    mcp_config = load_mcp_config(args.config)
    transport = args.transport or mcp_config.transport
    app = create_app(mcp_config)

    logger.info(
        "Starting http-adaptor with transport '%s' on %s:%d",
        transport,
        mcp_config.host,
        mcp_config.port,
    )
    app.run(transport=transport)
