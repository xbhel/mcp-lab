# ADR: Use http-gateway as the Single Project Name

**Status:** Accepted  
**Date:** 2026-04-28  
**Related guide:** [http-gateway-guide.md](./http-gateway-guide.md)  
**Related spec:** [http-gateway-spec.md](./http-gateway-spec.md)  
**Related draft:** [http-gateway-draft.md](./http-gateway-draft.md)

## Context

This repository implements one server that turns existing HTTP APIs into MCP tools at runtime.

Without an explicit naming and scope decision, the docs blur three different things:

- the concrete server that exists today,
- naming across the package, runtime identifier, and docs,
- and draft notes that were broader than the implemented scope.

That makes the docs harder to use and risks presenting roadmap items as implemented behavior.

## Decision

- Use `http-gateway` as the project and server name for the implementation that exists in this repository today.
- Use `http-gateway-mcp` as the Python package name.
- Keep the documented scope limited to turning existing HTTP APIs into MCP tools at runtime.
- Require the guide, specification, and draft to describe that implemented behavior consistently.

## Consequences

- README files must index the guide, spec, ADR, and draft together.
- The specification must describe the implemented server as the source of truth.
- The draft must review requirements and clearly label each item as implemented, partial, or planned.
- Security and operational gaps such as plain-text header storage and missing access control must stay visible in the docs.

## Implementation Plan

- Update [README.md](../README.md) to expose a complete docs index for the current server.
- Update [mcp-servers/http_gateway/README.md](../mcp-servers/http_gateway/README.md) to explain naming, scope, and operational caveats.
- Update [http-gateway-guide.md](./http-gateway-guide.md) to make the management-tool model and current scope clearer.
- Update [http-gateway-spec.md](./http-gateway-spec.md) to separate implemented behavior from roadmap items.
- Rewrite [http-gateway-draft.md](./http-gateway-draft.md) as an English working draft tied to the real implementation.

## Verification

- [x] The root README links to the guide, spec, ADR, and draft.
- [x] The package README uses the same naming and scope language as the guide and spec.
- [x] The specification clearly states that the server turns existing HTTP APIs into MCP tools at runtime.
- [x] The draft labels each original requirement as implemented, partial, or planned.

## Non-goals

- Renaming the existing package or runtime identifier.
- Defining a secret-management implementation.
