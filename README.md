# http-adaptor MCP

An MCP server that turns any HTTP API into a callable MCP tool — no code required. Register endpoints at runtime, import from OpenAPI specs, and invoke them directly from any MCP client.

The current scope is simple: turn existing HTTP APIs into MCP tools at runtime.

## Features

- **Register any HTTP API** as an MCP tool with a single call
- **OpenAPI import/export** — bulk-import from a 3.x spec (JSON or YAML)
- **Retry with backoff** — automatic retries on 5xx and network errors, with app-level defaults and per-tool overrides
- **JSON Schema validation** — validate inputs before dispatching
- **Per-tool metrics** — call count, success rate, p95 latency
- **Dual transport** — stdio (local) or Streamable HTTP (remote)
- **Persistent registry** — tools survive restarts via atomic JSON file

## Scope and naming

- `http-adaptor` is the current Phase 1 server name.
- `http-adaptor-mcp` is the Python package name.
- `adaptor_*` tool names are built-in management tools.
- User-registered tools keep the names you choose.

## Quick start

**Requirements:** Python 3.12+, [uv](https://docs.astral.sh/uv/)

```bash
cd mcp_servers/http_adaptor
uv sync
uv run http-adaptor --transport stdio   # local / VS Code
uv run http-adaptor --transport sse    # remote, default 127.0.0.1:8000
```

### Configuration

Configuration is resolved in this order:

1. explicit CLI or `create_app(...)` arguments
2. environment variables
3. config file values
4. built-in defaults

Default config file path: `~/.http_adaptor/config.toml`

```toml
storage_path = "${HTTP_ADAPTOR_STORAGE_PATH}"
transport = "http"
host = "127.0.0.1"
port = 8000
timeout_seconds = 45.0
retry_max_attempts = 5
```

`config.toml` supports `${VAR_NAME}` placeholders inside string values. They are expanded from the current environment before TOML parsing.

When a tool omits `timeout_seconds` or `retry_max_attempts`, the dispatcher uses the resolved app defaults at call time. Explicit tool values still win.

## MCP tools

| Tool                     | Description                                            |
| ------------------------ | ------------------------------------------------------ |
| `adaptor_register_tool`  | Register an HTTP endpoint as an MCP tool               |
| `adaptor_delete_tool`    | Remove a registered tool by name                       |
| `adaptor_list_tools`     | List tools with optional tag filter and pagination     |
| `adaptor_get_metrics`    | Per-tool call stats (count, success rate, p95 latency) |
| `adaptor_import_openapi` | Bulk-import from an OpenAPI 3.x spec file              |
| `adaptor_export_openapi` | Export all registered tools as an OpenAPI 3.1 spec     |

Registered tools are also exposed as first-class MCP tools callable by name.

There is no `adaptor_update_tool` yet. To change a tool definition today, delete it and register it again.

## VS Code / Claude Desktop config

**stdio (recommended for local use):**

```json
{
  "mcpServers": {
    "http-adaptor": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/mcp_servers/http_adaptor", "http-adaptor"]
    }
  }
}
```

**Streamable HTTP:**

```json
{
  "mcpServers": {
    "http-adaptor": {
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

## Project layout

```text
http_adaptor/
├── models.py          # Pydantic domain models (ToolDefinition, MetricEntry, …)
├── registry.py        # In-memory + JSON-backed tool registry
├── http_client.py     # Async HTTP dispatcher with retry and schema validation
├── openapi.py         # OpenAPI 3.x import and export
├── metrics.py         # In-memory per-tool call metrics
├── tools.py           # MCP tool handlers (@mcp.tool)
└── server.py          # FastMCP app factory and CLI entry point
tests/
├── conftest.py
├── test_server.py
├── test_registry.py
├── test_http_client.py
├── test_metrics.py
├── test_openapi.py
└── test_gateway_tools.py
```

## Documentation

| Document | Description |
| --- | --- |
| [docs/guide.md](docs/guide.md) | Beginner-friendly guide — concepts, quick start, use cases |
| [docs/spec.md](docs/spec.md) | Full specification — implemented behavior, limits, and roadmap items |
| [docs/draft.md](docs/draft.md) | Working draft — current scope, requirement status, and open gaps |

## Security notes

- Static request headers are stored in plain text in the registry file by design today. Treat the storage path like secret material.
- The `api_key_hash` field exists in the model, but Phase 1 does not enforce API-key-based tool access yet.
- HTTP 4xx responses are returned as errors and are not retried. Network failures and HTTP 5xx responses are retried.

## Development

```bash
# Run tests
uv run pytest tests/

# Run tests with coverage
uv run pytest tests/ --cov=http_adaptor --cov-report=term-missing

# Lint
uv run ruff check http_adaptor/ tests/

# Format
uv run ruff format http_adaptor/ tests/

uv sync --all-groups
uv run http-gateway --transport stdio
```
