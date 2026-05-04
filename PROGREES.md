# Progress

## Completed

- [x] Create a new HTTP API tool
- [x] Delete an HTTP API tool
- [x] Query all registered tools
- [x] Group tools by tags
- [x] Invoke registered APIs through MCP
- [x] Monitor call metrics — in-memory; persisted to `metrics.json` on shutdown and reloaded on startup (T-01)
- [x] Define APIs with JSON Schema
- [x] Support OpenAPI + JSON Schema — import 3.x; export 3.1
- [x] Validate inputs before dispatch
- [x] Export registered APIs
- [x] Friendly error handling — LLM-friendly messages for validation, HTTP, and network failures
- [x] Retry failed requests — network errors, HTTP 5xx, and HTTP 429 retried with exponential backoff (T-08)
- [x] Generate tool definitions from OpenAPI

---

## In Progress / Planned

- [ ] **Access control** (T-02) — `api_key_hash` exists on the model, but registration inputs and invocation-time verification are not implemented yet
- [ ] **Secret storage hardening** (T-06) — `${VAR_NAME}` placeholders can avoid persisting secrets, but plain-text static headers are still written to disk when provided directly
- [ ] **Update tool** (T-04) — No public `http2mcp_update_tool` is exposed yet
- [ ] **Structured call log** (Priority: Low) — no per-invocation logging beyond in-memory metrics (spec T-03)
- [ ] **Concurrency and thread safety** (Priority: Low) — single-process asyncio is currently sufficient; evaluate before any multi-client HTTP deployment (spec T-05)
- [ ] **OpenAPI v2 support** (Priority: Low) — only OpenAPI 3.x is supported; Swagger 2.0 import not implemented (spec T-07)
