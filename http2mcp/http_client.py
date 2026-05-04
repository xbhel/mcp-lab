"""HttpDispatcher — invoke registered HTTP API tools via httpx + tenacity.

Responsibilities:
- Validate input params against the tool's JSON Schema (if provided)
- Dispatch the HTTP request with correct method, headers, params/body
- Retry on 5xx responses and transient network errors
- Return a structured InvokeResult with LLM-friendly error messages
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import httpx
import jsonschema
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from http2mcp._internal_utils import substitute_env_vars
from http2mcp.models import InvokeResult, ToolDefinition

if TYPE_CHECKING:
    from http2mcp.config import MCPConfig


def _resolve_header_secrets(headers: dict[str, str]) -> dict[str, str]:
    """Expand ${VAR_NAME} placeholders in header values from environment variables.

    Placeholders that reference an unset variable are left unchanged.
    """
    return substitute_env_vars(headers, strict=False)  # type: ignore[no-any-return]


def _build_llm_error(exc: Exception) -> str:
    """Convert an exception into a concise, LLM-friendly error string."""
    if isinstance(exc, httpx.TimeoutException):
        return (
            "Request timed out. The remote API did not respond in time. "
            "Please retry or check the service."
        )

    if isinstance(exc, httpx.ConnectError):
        return f"Could not connect to the remote API: {exc}. Check the URL and network."

    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        messages = {
            400: "Bad request — the API rejected the input parameters.",
            401: "Unauthorized — the API requires authentication. Provide a valid API key.",
            403: "Forbidden — you do not have permission to call this API.",
            404: "Not found — the API endpoint does not exist. Check the URL.",
            429: "Rate limited — too many requests. Wait before retrying.",
            500: "Internal server error — the remote API encountered an error.",
            502: "Bad gateway — the remote API is unavailable.",
            503: "Service unavailable — the remote API is temporarily down.",
        }
        return messages.get(code, f"HTTP {code} error from the remote API.")

    return f"Unexpected error: {type(exc).__name__}: {exc}"


def _validate_input(params: dict[str, Any], schema: dict[str, Any] | None) -> str | None:
    """Validate params against a JSON Schema. Returns an error string or None."""
    if schema is None:
        return None
    try:
        jsonschema.validate(instance=params, schema=schema)
    except jsonschema.ValidationError as exc:
        field = exc.json_path or exc.absolute_path or "input"
        return (
            f"Input validation failed: '{field}' — {exc.message}. "
            "Please fix the parameter and retry."
        )
    return None


def _parse_body(response: httpx.Response) -> str | dict[str, Any]:
    """Parse an HTTP response body as a JSON dict or plain text string."""
    content_type = response.headers.get("content-type", "")
    if "application/json" in content_type:
        try:
            return response.json()  # type: ignore[no-any-return]
        except Exception:
            return response.text
    return response.text


class _RetryableError(Exception):
    """Raised when the remote API returns a 5xx response.

    Signals tenacity to schedule a retry. The embedded result holds the last
    failed response so it can be returned if all retries are exhausted.
    """

    def __init__(self, result: InvokeResult) -> None:
        self.result = result


class HttpDispatcher:
    """Dispatches HTTP requests for registered MCP tools."""

    def __init__(self, client: httpx.AsyncClient, config: MCPConfig) -> None:
        self._client = client
        self._config = config

    def _effective_retry_max_attempts(self, tool: ToolDefinition) -> int:
        if tool.retry_max_attempts is not None:
            return tool.retry_max_attempts
        return self._config.retry_max_attempts

    def _effective_timeout_seconds(self, tool: ToolDefinition) -> float:
        if tool.timeout_seconds is not None:
            return tool.timeout_seconds
        return self._config.timeout_seconds

    async def invoke(self, tool: ToolDefinition, params: dict[str, Any]) -> InvokeResult:
        """Invoke the tool's HTTP API and return a structured result.

        Validates input, dispatches the request with retry logic,
        and always returns an InvokeResult (never raises).
        """
        validation_error = _validate_input(params, tool.input_schema)
        if validation_error:
            return InvokeResult(
                tool_name=tool.name,
                status_code=422,
                body="",
                latency_ms=0.0,
                error=validation_error,
            )
        try:
            return await self._dispatch(tool, params)
        except Exception as exc:
            return InvokeResult(
                tool_name=tool.name,
                status_code=0,
                body="",
                latency_ms=0.0,
                error=_build_llm_error(exc),
            )

    async def _dispatch(self, tool: ToolDefinition, params: dict[str, Any]) -> InvokeResult:
        """Retry-aware dispatcher. Tenacity owns both 5xx and network-error retries.

        Returns a clean InvokeResult for all retryable outcomes. Unexpected
        exceptions propagate to invoke() for final handling.
        """
        last_attempt = 0
        try:
            async for attempt in AsyncRetrying(
                retry=retry_if_exception_type(
                    (_RetryableError, httpx.TimeoutException, httpx.ConnectError)
                ),
                stop=stop_after_attempt(self._effective_retry_max_attempts(tool)),
                wait=wait_exponential(multiplier=tool.retry_backoff_seconds, min=0.1, max=30.0),
                reraise=True,
            ):
                with attempt:
                    last_attempt = attempt.retry_state.attempt_number
                    return await self._send_request(tool, params, last_attempt - 1)
        except _RetryableError as exc:
            return exc.result
        except (httpx.TimeoutException, httpx.ConnectError) as exc:
            return InvokeResult(
                tool_name=tool.name,
                status_code=0,
                body="",
                latency_ms=0.0,
                retries=last_attempt - 1,
                error=_build_llm_error(exc),
            )
        raise AssertionError("unreachable")  # pragma: no cover

    async def _send_request(
        self, tool: ToolDefinition, params: dict[str, Any], retries: int
    ) -> InvokeResult:
        """Execute a single HTTP request and return a structured result.

        Raises _RetryableError on 5xx so tenacity can schedule a retry.
        4xx responses are returned directly without retry.
        """
        start = time.perf_counter()
        method = tool.method.upper()
        kwargs: dict[str, Any] = {"headers": _resolve_header_secrets(tool.headers)}

        if method in ("GET", "HEAD", "DELETE"):
            kwargs["params"] = params
        else:
            kwargs["json"] = params

        response = await self._client.request(
            method,
            tool.url,
            timeout=self._effective_timeout_seconds(tool),
            **kwargs,
        )
        latency_ms = (time.perf_counter() - start) * 1000
        body = _parse_body(response)

        if response.status_code >= 500 or response.status_code == 429:
            error_msg = _build_llm_error(
                httpx.HTTPStatusError(message="", request=response.request, response=response)
            )
            raise _RetryableError(
                InvokeResult(
                    tool_name=tool.name,
                    status_code=response.status_code,
                    body=body,
                    latency_ms=latency_ms,
                    error=error_msg,
                    retries=retries,
                )
            )

        if response.status_code >= 400:
            error_msg = _build_llm_error(
                httpx.HTTPStatusError(message="", request=response.request, response=response)
            )
            return InvokeResult(
                tool_name=tool.name,
                status_code=response.status_code,
                body=body,
                latency_ms=latency_ms,
                error=error_msg,
                retries=retries,
            )

        return InvokeResult(
            tool_name=tool.name,
            status_code=response.status_code,
            body=body,
            latency_ms=latency_ms,
            retries=retries,
        )
