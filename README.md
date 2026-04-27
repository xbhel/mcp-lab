# MCP Servers

A monorepo of [Model Context Protocol](https://modelcontextprotocol.io) servers built with Python and [FastMCP](https://github.com/jlowin/fastmcp).

The current flagship server is `http-gateway`, which turns existing HTTP APIs into MCP tools at runtime.

## Servers

| Server | Description | Docs |
| --- | ---- | --- |
| [`http-gateway`](mcp-servers/http_gateway/) | Turn any HTTP API into an MCP tool at runtime | [README](mcp-servers/http_gateway/README.md) · [Guide](docs/http-gateway-guide.md) · [Spec](docs/http-gateway-spec.md) · [ADR](docs/http-gateway-phase-scope-adr.md) |

## Documentation

| Document | Description |
| --- | --- |
| [docs/http-gateway-guide.md](docs/http-gateway-guide.md) | Beginner-friendly guide — concepts, quick start, use cases |
| [docs/http-gateway-spec.md](docs/http-gateway-spec.md) | Full specification — implemented behavior, limits, and roadmap items |
| [docs/http-gateway-phase-scope-adr.md](docs/http-gateway-phase-scope-adr.md) | ADR — naming and scope for the current server |
| [docs/http-gateway-draft.md](docs/http-gateway-draft.md) | Working draft — current scope, requirement status, and open gaps |

## Repo layout

```text
mcp-servers/
└── http_gateway/       # Phase 1 HTTP-to-MCP gateway server
docs/                   # Guides, specifications, ADRs, and roadmap drafts
AGENTS.md               # AI agent guidelines for this repo
```

## Development

Each server is an independent Python package managed with [uv](https://docs.astral.sh/uv/). Navigate into the server directory and use `uv` to install and run:

```bash
cd mcp-servers/http_gateway
uv sync
uv run http-gateway --transport stdio
```

Start with the package README for day-to-day use, then move to the guide and spec when you need more detail. Use the ADR and draft when you want the naming decision, current scope, and open gaps in one place.
