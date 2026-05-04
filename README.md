# HTTP2MCP

An MCP server that turns any HTTP API into a callable MCP tool — no code required. Register endpoints at runtime, import from OpenAPI specs, and invoke them directly from any MCP client.

## Features

- **Register any HTTP API** as an MCP tool with a single call
- **OpenAPI import/export** — bulk-import from a 3.x spec (JSON or YAML)
- **Retry with backoff** — automatic retries on 5xx and network errors, with app-level defaults and per-tool overrides
- **JSON Schema validation** — validate inputs before dispatching
- **Per-tool metrics** — call count, success rate, p95 latency, persisted on graceful shutdown
- **Dual transport** — stdio (local) or Streamable HTTP (remote)
- **Persistent registry** — tools survive restarts via atomic JSON file

## Naming conventions

- `http2mcp_*` tool names are built-in management tools
- User-registered tools keep the names you choose

## Quick start

**Requirements:** Python 3.12+, [uv](https://docs.astral.sh/uv/)

```bash
uv sync --all-groups
uv run http2mcp --transport stdio   # local / VS Code
uv run http2mcp --transport sse    # remote, default 127.0.0.1:8000
```

### Configuration

Default config file path: `~/.http2mcp/config.toml`

```toml
[mcp]
work_dir = "~/.http2mcp" # Base directory for persistent state; tools.json and metrics.json live here
transport = "stdio"  # "stdio" or "sse"
host = "127.0.0.1" # Only for "sse" transport
port = 8000 # Only for "sse" transport
timeout_seconds = 45.0 # Default timeout for HTTP calls (can be overridden per tool)
retry_max_attempts = 5 # Default max retry attempts for failed HTTP calls (can be overridden per tool)
```

`config.toml` supports `${VAR_NAME}` placeholders inside string values. They are expanded from the current environment before TOML parsing.

The registry is stored at `<work_dir>/tools.json`, and metrics are stored at `<work_dir>/metrics.json`.

When a tool omits `timeout_seconds` or `retry_max_attempts`, the dispatcher uses the resolved app defaults at call time. Explicit tool values still win.

## MCP tools

| Tool                      | Description                                            |
| ------------------------- | ------------------------------------------------------ |
| `http2mcp_register_tool`  | Register an HTTP endpoint as an MCP tool               |
| `http2mcp_delete_tool`    | Remove a registered tool by name                       |
| `http2mcp_list_tools`     | List tools with optional tag filter and pagination     |
| `http2mcp_get_metrics`    | Per-tool call stats (count, success rate, p95 latency) |
| `http2mcp_import_openapi` | Bulk-import from an OpenAPI 3.x spec file              |
| `http2mcp_export_openapi` | Export all registered tools as an OpenAPI 3.1 spec     |

Registered tools are also exposed as first-class MCP tools callable by name.

There is no `http2mcp_update_tool` yet. To change a tool definition today, delete it and register it again.

## VS Code / Claude Desktop config

**stdio (recommended for local use):**

```json
{
    "servers": {
        "http2mcp": {
            "type": "stdio",
            "command": "uv",
            "args": ["run", "--directory", "/path/to/http2mcp", "http2mcp"]
        }
    }
}
```

**Streamable HTTP:**

```json
{
  "servers": {
    "http2mcp": {
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

## Project layout

```text
http2mcp/
├── config.py          # MCPConfig model and config loading logic
├── exceptions.py       # Custom exceptions (ToolNotFoundError, ValidationError, etc.)
├── http_client.py     # Async HTTP dispatcher with retry and schema validation
├── metrics.py         # Per-tool call metrics with save/load helpers
├── models.py          # Pydantic domain models (ToolDefinition, MetricEntry, …)
├── openapi.py         # OpenAPI 3.x import and export
├── registry.py        # In-memory + JSON-backed tool registry
├── server.py          # FastMCP app factory and CLI entry point
└── tools.py           # MCP tool handlers (@mcp.tool)
tests/
├── conftest.py
├── test_server.py
├── test_registry.py
├── test_http_client.py
├── test_metrics.py
├── test_openapi.py
└── test_tools.py
```

## Documentation

| Document                       | Description                                                          |
| ------------------------------ | -------------------------------------------------------------------- |
| [docs/guide.md](docs/guide.md) | Beginner-friendly guide — concepts, quick start, use cases           |
| [docs/spec.md](docs/spec.md)   | Full specification — implemented behavior, limits, and roadmap items |
| [docs/draft.md](docs/draft.md) | Working draft — current scope, requirement status, and open gaps     |

## Security notes

- Static request headers are stored in plain text in `<work_dir>/tools.json` unless you register `${VAR_NAME}` placeholders instead. Treat the work directory like secret material.
- The `api_key_hash` field exists in the model, but Phase 1 does not enforce API-key-based tool access yet.
- HTTP 4xx responses are returned as errors and are not retried. Network failures and HTTP 5xx responses are retried.

## Development

```bash
# Run tests
uv run pytest tests/

# Run tests with coverage
uv run pytest tests/ --cov=http2mcp --cov-report=term-missing

# Lint
uv run ruff check http2mcp/ tests/
uv run mypy http2mcp/ tests/

# Format
uv run ruff format http2mcp/ tests/

# Run the server (stdio transport for local development)
uv sync --all-groups
uv run http2mcp --transport stdio
```
