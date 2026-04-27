# http-gateway Guide

**Specification:** [http-gateway-spec.md](./http-gateway-spec.md)  
**ADR:** [http-gateway-phase-scope-adr.md](./http-gateway-phase-scope-adr.md)  
**Draft:** [http-gateway-draft.md](./http-gateway-draft.md)  
**Source code:** [mcp-servers/http_gateway/](../mcp-servers/http_gateway/)

> 💡 This guide assumes no prior MCP experience. If you already know the basics, jump to [Quick Start](#3-quick-start).

---

## 1. Overview

`http-gateway` is an **MCP server** that lets you turn any HTTP API into a tool that an AI assistant can call — without writing any code.

You register your HTTP APIs once (by name, URL, and method), and the gateway exposes them as MCP tools automatically. From that point on, any LLM connected to the gateway can discover and call those APIs on your behalf.

**Think of it as a universal remote control for HTTP APIs — one that your AI can operate.**

`http-gateway` has one job in this repository: turn existing HTTP APIs into MCP tools at runtime.

### 1.1 Names you'll see

- `http-gateway`: the server in this repository.
- `gateway_*`: built-in management tools such as `gateway_register_tool` and `gateway_list_tools`.
- Your registered tool names: the runtime MCP tools you add, such as `get_weather_forecast`.

---

## 2. Prerequisites

Before you start, you'll need:

- **Python 3.12+** — check with `python --version`
- **uv** — the package manager used for this project ([install guide](https://docs.astral.sh/uv/))
- A terminal (PowerShell, bash, etc.)
- An HTTP API you'd like to expose (or you can follow along with `httpbin.org`)

---

## 3. Quick Start

```bash
# 1. Go to the project directory
cd mcp-servers/http_gateway

# 2. Install dependencies
uv sync

# 3. Start the server (stdio mode, for local use)
uv run http-gateway

# Or, start with HTTP transport (for remote/multi-client use)
uv run http-gateway --transport http --host 127.0.0.1 --port 8000
```

Once running, point your MCP client (e.g. VS Code Copilot or Claude Desktop) at the server, and you're ready to go.

> 🔑 **VS Code config** (`mcp.json`):

```json
{
  "mcpServers": {
    "http-gateway": {
      "command": "uv",
      "args": ["run", "--directory", "mcp-servers/http_gateway", "http-gateway"]
    }
  }
}
```

---

## 4. Core Concepts

Before diving in, here are the five key ideas:

### 🔧 Tool

An **MCP tool** is a named action that an LLM can invoke. In http-gateway, each tool maps to one HTTP API endpoint. When an LLM calls the tool, http-gateway fires the matching HTTP request and returns the result.

### 🧰 Management Tools

The built-in management tools all use the `gateway_` prefix. They let you register, delete, list, import, export, and inspect tools. The tools you register do not need that prefix; they use whatever names you choose.

### 📋 Registry

The **registry** is the list of all your registered HTTP API tools. It's stored in `~/.http_gateway/tools.json` and automatically loaded every time the server starts.

### 🚀 Dispatcher

The **dispatcher** is the component that actually fires HTTP requests. It handles retries on failures, validates your input against a JSON Schema (if you provided one), and always returns a clear, human-readable result — even when something goes wrong.

### 📊 Metrics

The gateway tracks **metrics** for every tool call: how many times it was called, how many succeeded, average response time, and more. This helps you see which tools are healthy and which are struggling.

---

## 5. Architecture Overview

Here's how data flows when an LLM calls a registered HTTP tool:

```mermaid
sequenceDiagram
    participant LLM as 🤖 LLM (Copilot / Claude)
    participant MCP as MCP Client
    participant GW as http-gateway (MCP Server)
    participant API as 🌐 Remote HTTP API

    LLM->>MCP: 1: Call tool "weather_forecast" with params
    MCP->>GW: 2: MCP tool invocation (stdio or HTTP)
    GW->>GW: 3: Validate input against JSON Schema
    GW->>API: 4: Send HTTP GET /forecast?city=Paris
    API-->>GW: 5: 200 OK { "temp": 18, "condition": "cloudy" }
    GW->>GW: 6: Record metrics (latency, success)
    GW-->>MCP: 7: Return result as JSON
    MCP-->>LLM: 8: Tool result delivered
```

  The same flow also depends on the registry and metrics components behind the scenes. The full component view lives in the specification.

The gateway also exposes **management tools** — these let the LLM (or you) register, delete, list, and inspect tools without restarting the server.

The management tools always use the `gateway_` prefix. The runtime tools created from your APIs keep the names you registered.

---

## 6. How to Use It: Step by Step

### Step 1 — Register an HTTP API as a tool

Use the `gateway_register_tool` tool (via your MCP client):

```json
{
  "name": "get_joke",
  "description": "Fetch a random programming joke",
  "url": "https://official-joke-api.appspot.com/jokes/programming/random",
  "method": "GET"
}
```

The tool is immediately available and persisted to disk.

### Step 2 — Ask the LLM to call it

Tell your AI: *"Use the get_joke tool to fetch a joke."*  
The LLM will invoke `get_joke`, and the gateway will fire the HTTP request, then return the result.

### Step 3 — List your registered tools

Use `gateway_list_tools` to see everything in the registry:

```json
{ "limit": 20 }
```

You can also filter by tag: `{ "tags": ["weather", "public"] }`.

The list view is intentionally compact. It shows discovery metadata and live call counts, but not stored headers or full schemas.

### Step 4 — Import from OpenAPI (bulk registration)

If you have an OpenAPI spec file, you can import all operations at once:

```json
{
  "spec_path": "/path/to/my-api.yaml",
  "filter_tags": ["public"]
}
```

This creates one MCP tool per API operation automatically.

### Step 5 — Check metrics

Use `gateway_get_metrics` to see call stats for all your tools:

```json
{
  "get_joke": {
    "call_count": 12,
    "success_count": 11,
    "success_rate": 0.92,
    "avg_latency_ms": 340,
    "p95_latency_ms": 610
  }
}
```

Metrics live in memory only, so they reset when the server restarts.

---

## 7. Real-World Use Cases

| Use case | How |
| --- | --- |
| **Connect a private REST API to Copilot** | Register your internal API endpoints using `gateway_register_tool` |
| **Import an entire OpenAPI service** | Use `gateway_import_openapi` to bulk-register all endpoints from a spec file |
| **Add auth headers automatically** | Set `headers: { "Authorization": "Bearer TOKEN" }` at registration time |
| **Monitor API health from the LLM** | Ask the LLM to call `gateway_get_metrics` and summarize slow or failing tools |
| **Share your tool catalog** | Use `gateway_export_openapi` to export your registered tools as an OpenAPI spec |

---

## 8. Security Considerations

⚠️ A few things to keep in mind when using http-gateway:

1. **Never put secrets in tool names or descriptions.** Those fields are meant for discovery and should stay safe to show to users and LLMs.

2. **Treat the registry file as secret material if you use auth headers.** Static headers are stored in plain text in `tools.json` today.

3. **Do not rely on `api_key_hash` yet.** The field exists in the model, but Phase 1 does not enforce API-key-based tool access. See [T-02 in the spec](./http-gateway-spec.md#8-todo--open-questions).

4. **Prefer HTTPS endpoints.** The dispatcher will call `http://` URLs too, but plain HTTP traffic is unencrypted.

5. **Use stdio transport for local use.** When running locally, stdio keeps communication on your machine. HTTP transport opens a network port, so bind carefully.

---

## 9. Common Pitfalls

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Tool not found after restart | Tools *are* persisted — check your `--storage` path | Run with same `--storage` path each time |
| Input validation error (422) | The params you sent don't match `input_schema` | Check the schema or send the required fields |
| "Not found — the API endpoint does not exist" | Wrong URL registered | Delete and re-register with the correct URL |
| Timeout on every call | Remote API is slow | Increase `timeout_seconds` at registration |
| `DuplicateToolError` on import | Tool name already registered | Use `filter_tags` to skip unwanted operations, or delete the old tool first |
| Metrics show 0 after restart | Metrics are in-memory only | This is expected behavior — persistence is a planned feature |
| Need to change a tool definition | There is no update tool yet | Delete the tool and register it again |

---

## 10. Tips and Best Practices

- **Name tools clearly.** Use snake_case names that describe what the tool does: `get_weather_forecast`, not `api1`. The LLM uses the name and description to decide when to call it.

- **Always add a description.** A good description helps the LLM know *when* and *how* to use the tool. Include the main parameters and what the result looks like.

- **Use `input_schema` for important tools.** If your API has required parameters, define them with a JSON Schema. The gateway will catch bad inputs before they ever hit the remote API.

- **Add tags for organization.** When you have many tools, tags make it easy to find related ones with `gateway_list_tools { "tags": [...] }`.

- **Use version suffixes for evolving APIs.** If an API changes, register the new version as `my_tool_v2` and keep `my_tool_v1` running until you're ready to migrate.

- **Set a realistic timeout.** The default is 30 seconds. For fast APIs, set it lower (e.g. 5s) to fail quickly. For slow batch jobs, raise it to 120s.

- **Remember what gets retried.** Network failures and HTTP 5xx responses are retried. HTTP 4xx responses are returned immediately because they usually indicate a bad request or missing auth.

---

## 11. Next Steps

Now that you know the basics, here's what to explore next:

- 📖 Read the full [Specification](./http-gateway-spec.md) to understand all fields, validation rules, and the complete tool API
- 🧭 Read the [ADR](./http-gateway-phase-scope-adr.md) if you want the naming and scope rationale behind the current docs
- 🗺️ Check the [draft](./http-gateway-draft.md) for the current requirement status and remaining gaps
- 🔌 Connect to a real API — try registering a public REST API like [JSONPlaceholder](https://jsonplaceholder.typicode.com/)
- 📦 Import a full OpenAPI spec with `gateway_import_openapi` to bulk-register dozens of endpoints
- 🛡️ Follow [T-02 in the spec](./http-gateway-spec.md#8-todo--open-questions) for updates on the API key access control feature
- 🤝 Contribute — check the open TODOs in the spec for good first issues (metrics persistence, update tool, secret storage)
