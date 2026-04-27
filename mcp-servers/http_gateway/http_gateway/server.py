"""http-gateway MCP server entry point.

Supports two transports selectable via --transport flag:
  stdio   — local process, single client (VS Code, Claude Desktop)
  http    — Streamable HTTP, remote multi-client deployment

Usage:
    uv run http-gateway --transport stdio
    uv run http-gateway --transport http --port 8000 --host 0.0.0.0
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from http_gateway.gateway_tools import register_gateway_tools
from http_gateway.http_client import HttpDispatcher
from http_gateway.metrics import MetricsCollector
from http_gateway.registry import ToolRegistry

# ---------------------------------------------------------------------------
# Logging — write to stderr only (stdout is reserved for stdio MCP transport)
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("http_gateway")

# ---------------------------------------------------------------------------
# Default storage path
# ---------------------------------------------------------------------------
DEFAULT_STORAGE_PATH = Path.home() / ".http_gateway" / "tools.json"


def create_app(
    storage_path: Path | None = None,
    host: str = "127.0.0.1",
    port: int = 8000,
) -> FastMCP:
    """Create and configure the FastMCP application.

    Args:
        storage_path: Path to the tools.json registry file.
                      Defaults to ~/.http_gateway/tools.json.
        host: Host to bind when using HTTP transport.
        port: Port to listen on when using HTTP transport.

    Returns:
        Configured FastMCP instance ready to run.
    """
    path = storage_path or DEFAULT_STORAGE_PATH

    # Initialise dependencies
    registry = ToolRegistry(storage_path=path)
    dispatcher = HttpDispatcher()
    metrics = MetricsCollector()

    # Create the MCP server
    mcp = FastMCP(
        "http_gateway_mcp",
        host=host,
        port=port,
        instructions=(
            "This MCP server acts as an HTTP-to-MCP gateway. "
            "Use gateway_register_tool to add any HTTP API as a callable MCP tool. "
            "Use gateway_list_tools to see all registered tools. "
            "Use gateway_import_openapi to bulk-import from an OpenAPI spec. "
            "Registered tools are invocable directly by their name."
        ),
    )

    # Register management tools
    register_gateway_tools(mcp, registry, dispatcher, metrics)

    # Load persisted tools as dynamic MCP tools
    loaded = 0
    for tool in registry.all():
        try:
            from http_gateway.gateway_tools import _add_dynamic_tool

            _add_dynamic_tool(mcp, tool, dispatcher, metrics)
            loaded += 1
        except Exception as exc:
            logger.warning("Failed to load tool '%s': %s", tool.name, exc)

    logger.info("http-gateway started: %d tool(s) loaded from '%s'", loaded, path)

    return mcp


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="http-gateway — HTTP-to-MCP adapter server",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="MCP transport: 'stdio' for local use, 'http' for remote deployment.",
    )
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="Host to bind when using HTTP transport.",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8000,
        help="Port to listen on when using HTTP transport.",
    )
    parser.add_argument(
        "--storage",
        default=None,
        help="Path to tools.json registry file.",
    )
    args = parser.parse_args()

    storage_path = Path(args.storage) if args.storage else None
    mcp = create_app(storage_path=storage_path, host=args.host, port=args.port)

    if args.transport == "stdio":
        logger.info("Starting http-gateway via stdio transport")
        mcp.run(transport="stdio")
    else:
        logger.info("Starting http-gateway via HTTP transport on %s:%d", args.host, args.port)
        mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
