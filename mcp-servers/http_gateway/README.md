# http-gateway MCP

An MCP server that turns any HTTP API into a callable MCP tool — no code required. Register endpoints at runtime, import from OpenAPI specs, and invoke them directly from any MCP client.

The current scope is simple: turn existing HTTP APIs into MCP tools at runtime.

## Features

- **Register any HTTP API** as an MCP tool with a single call
- **OpenAPI import/export** — bulk-import from a 3.x spec (JSON or YAML)
- **Retry with backoff** — automatic retries on 5xx and network errors (tenacity)
- **JSON Schema validation** — validate inputs before dispatching
- **Per-tool metrics** — call count, success rate, p95 latency
- **Dual transport** — stdio (local) or Streamable HTTP (remote)
- **Persistent registry** — tools survive restarts via atomic JSON file

## Scope and naming

- `http-gateway` is the current Phase 1 server name.
- `http-gateway-mcp` is the Python package name.
- `gateway_*` tool names are built-in management tools.
- User-registered tools keep the names you choose.

## Quick start

**Requirements:** Python 3.12+, [uv](https://docs.astral.sh/uv/)

```bash
cd mcp-servers/http_gateway
uv sync
uv run http-gateway --transport stdio   # local / VS Code
uv run http-gateway --transport http    # remote, default 127.0.0.1:8000
```

### Options

| Flag          | Default                      | Description                     |
| ------------- | ---------------------------- | ------------------------------- |
| `--transport` | `stdio`                      | `stdio` or `http`               |
| `--host`      | `127.0.0.1`                  | Bind host (HTTP transport only) |
| `--port`      | `8000`                       | Bind port (HTTP transport only) |
| `--storage`   | `~/.http_gateway/tools.json` | Registry file path              |

## MCP tools

| Tool                     | Description                                            |
| ------------------------ | ------------------------------------------------------ |
| `gateway_register_tool`  | Register an HTTP endpoint as an MCP tool               |
| `gateway_delete_tool`    | Remove a registered tool by name                       |
| `gateway_list_tools`     | List tools with optional tag filter and pagination     |
| `gateway_get_metrics`    | Per-tool call stats (count, success rate, p95 latency) |
| `gateway_import_openapi` | Bulk-import from an OpenAPI 3.x spec file              |
| `gateway_export_openapi` | Export all registered tools as an OpenAPI 3.1 spec     |

Registered tools are also exposed as first-class MCP tools callable by name.

There is no `gateway_update_tool` yet. To change a tool definition today, delete it and register it again.

## VS Code / Claude Desktop config

**stdio (recommended for local use):**

```json
{
  "mcpServers": {
    "http-gateway": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/mcp-servers/http_gateway", "http-gateway"]
    }
  }
}
```

**Streamable HTTP:**

```json
{
  "mcpServers": {
    "http-gateway": {
      "url": "http://127.0.0.1:8000/mcp"
    }
  }
}
```

## Project layout

```text
http_gateway/
├── models.py          # Pydantic domain models (ToolDefinition, MetricEntry, …)
├── registry.py        # In-memory + JSON-backed tool registry
├── http_client.py     # Async HTTP dispatcher with retry and schema validation
├── openapi.py         # OpenAPI 3.x import and export
├── metrics.py         # In-memory per-tool call metrics
├── gateway_tools.py   # MCP tool handlers (@mcp.tool)
└── server.py          # FastMCP app factory and CLI entry point
tests/
├── conftest.py
├── test_registry.py
├── test_http_client.py
├── test_metrics.py
├── test_openapi.py
└── test_gateway_tools.py
```

## Documentation

| Document | Description |
| --- | --- |
| [docs/http-gateway-guide.md](../../docs/http-gateway-guide.md) | Beginner-friendly guide — concepts, quick start, use cases |
| [docs/http-gateway-spec.md](../../docs/http-gateway-spec.md) | Full specification — implemented behavior, limits, and roadmap items |
| [docs/http-gateway-phase-scope-adr.md](../../docs/http-gateway-phase-scope-adr.md) | ADR — naming and scope for the current server |
| [docs/http-gateway-draft.md](../../docs/http-gateway-draft.md) | Working draft — current scope, requirement status, and open gaps |

## Security notes

- Static request headers are stored in plain text in the registry file by design today. Treat the storage path like secret material.
- The `api_key_hash` field exists in the model, but Phase 1 does not enforce API-key-based tool access yet.
- HTTP 4xx responses are returned as errors and are not retried. Network failures and HTTP 5xx responses are retried.

## Development

```bash
# Run tests
uv run pytest tests/

# Run tests with coverage
uv run pytest tests/ --cov=http_gateway --cov-report=term-missing

# Lint
uv run ruff check http_gateway/ tests/

# Format
uv run ruff format http_gateway/ tests/
```
