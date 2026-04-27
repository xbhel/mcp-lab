"""HttpDispatcher — invoke registered HTTP API tools via httpx + tenacity.

Responsibilities:
- Validate input params against the tool's JSON Schema (if provided)
- Dispatch the HTTP request with correct method, headers, params/body
- Retry on 5xx responses and transient network errors
- Return a structured InvokeResult with LLM-friendly error messages
"""

from __future__ import annotations

import time
from typing import Any

import httpx
import jsonschema
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from http_gateway.models import InvokeResult, ToolDefinition


def _is_retryable_response(result: InvokeResult) -> bool:
    """Retry if the HTTP response is a 5xx error."""
    return result.status_code >= 500 and result.error is not None


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


class HttpDispatcher:
    """Dispatches HTTP requests for registered MCP tools."""

    async def invoke(self, tool: ToolDefinition, params: dict[str, Any]) -> InvokeResult:
        """Invoke the tool's HTTP API and return a structured result.

        Validates input, dispatches the request with retry logic,
        and always returns an InvokeResult (never raises).
        """
        # 1. JSON Schema validation
        validation_error = _validate_input(params, tool.input_schema)
        if validation_error:
            return InvokeResult(
                tool_name=tool.name,
                status_code=422,
                body="",
                latency_ms=0.0,
                error=validation_error,
            )

        # 2. Build the retry-wrapped invocation
        attempt_count = 0

        async def _dispatch_with_retry() -> InvokeResult:
            nonlocal attempt_count

            @retry(
                retry=(retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError))),
                stop=stop_after_attempt(tool.retry_max_attempts),
                wait=wait_exponential(multiplier=tool.retry_backoff_seconds, min=0.1, max=30.0),
                reraise=True,
            )
            async def _call() -> tuple[InvokeResult, int]:
                nonlocal attempt_count
                start = time.perf_counter()
                attempt_count += 1

                async with httpx.AsyncClient(timeout=tool.timeout_seconds) as client:
                    method = tool.method.upper()
                    kwargs: dict[str, Any] = {"headers": tool.headers}

                    if method in ("GET", "HEAD", "DELETE"):
                        kwargs["params"] = params
                    else:
                        kwargs["json"] = params

                    response = await client.request(method, tool.url, **kwargs)
                    latency_ms = (time.perf_counter() - start) * 1000

                    # Parse body
                    content_type = response.headers.get("content-type", "")
                    if "application/json" in content_type:
                        try:
                            body: str | dict = response.json()
                        except Exception:
                            body = response.text
                    else:
                        body = response.text

                    # Treat 5xx as errors (may be retried by outer logic)
                    if response.status_code >= 500:
                        error_msg = _build_llm_error(
                            httpx.HTTPStatusError(
                                message="",
                                request=response.request,
                                response=response,
                            )
                        )
                        return InvokeResult(
                            tool_name=tool.name,
                            status_code=response.status_code,
                            body=body,
                            latency_ms=latency_ms,
                            retries=attempt_count - 1,
                            error=error_msg,
                        ), attempt_count

                    # 4xx — not retried, return structured error
                    if response.status_code >= 400:
                        error_msg = _build_llm_error(
                            httpx.HTTPStatusError(
                                message="",
                                request=response.request,
                                response=response,
                            )
                        )
                        return InvokeResult(
                            tool_name=tool.name,
                            status_code=response.status_code,
                            body=body,
                            latency_ms=latency_ms,
                            retries=0,
                            error=error_msg,
                        ), attempt_count

                    return InvokeResult(
                        tool_name=tool.name,
                        status_code=response.status_code,
                        body=body,
                        latency_ms=latency_ms,
                        retries=attempt_count - 1,
                    ), attempt_count

            # Retry 5xx: wrap in a loop with tenacity for HTTP-level retries
            last_result: InvokeResult | None = None
            for attempt in range(tool.retry_max_attempts):
                try:
                    result, _ = await _call()
                except (httpx.TimeoutException, httpx.ConnectError) as exc:
                    latency_ms = 0.0
                    return InvokeResult(
                        tool_name=tool.name,
                        status_code=0,
                        body="",
                        latency_ms=latency_ms,
                        retries=attempt,
                        error=_build_llm_error(exc),
                    )

                if result.status_code < 500:
                    return result

                last_result = InvokeResult(
                    tool_name=tool.name,
                    status_code=result.status_code,
                    body=result.body,
                    latency_ms=result.latency_ms,
                    retries=attempt,
                    error=result.error,
                )

            return last_result  # type: ignore[return-value]

        try:
            return await _dispatch_with_retry()
        except Exception as exc:
            return InvokeResult(
                tool_name=tool.name,
                status_code=0,
                body="",
                latency_ms=0.0,
                error=_build_llm_error(exc),
            )
