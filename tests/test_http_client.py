"""Tests for HttpDispatcher — HTTP invocation, retry, validation, error handling."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
import respx
from httpx import Response

from http_adaptor.config import MCPConfig
from http_adaptor.http_client import HttpDispatcher
from http_adaptor.models import ToolDefinition

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def get_tool() -> ToolDefinition:
    return ToolDefinition(
        name="echo_get_v1",
        description="GET echo",
        url="https://httpbin.example.com/get",
        method="GET",
        retry_max_attempts=1,
    )


@pytest.fixture
def post_tool() -> ToolDefinition:
    return ToolDefinition(
        name="echo_post_v1",
        description="POST echo",
        url="https://httpbin.example.com/post",
        method="POST",
        input_schema={
            "type": "object",
            "properties": {"message": {"type": "string"}},
            "required": ["message"],
        },
        retry_max_attempts=1,
    )


@pytest.fixture
def dispatcher() -> HttpDispatcher:
    return HttpDispatcher(client=httpx.AsyncClient(), config=MCPConfig())


# ---------------------------------------------------------------------------
# invoke — happy paths
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_invoke_should_return_json_body_on_200(
    dispatcher: HttpDispatcher, get_tool: ToolDefinition
) -> None:
    respx.get("https://httpbin.example.com/get").mock(
        return_value=Response(200, json={"status": "ok"})
    )
    result = await dispatcher.invoke(get_tool, params={})
    assert result.is_success
    assert result.status_code == 200
    assert result.body == {"status": "ok"}


@pytest.mark.asyncio
@respx.mock
async def test_invoke_should_return_raw_text_when_response_is_not_json(
    dispatcher: HttpDispatcher, get_tool: ToolDefinition
) -> None:
    respx.get("https://httpbin.example.com/get").mock(
        return_value=Response(200, text="plain text response")
    )
    result = await dispatcher.invoke(get_tool, params={})
    assert result.is_success
    assert result.body == "plain text response"


@pytest.mark.asyncio
@respx.mock
async def test_invoke_should_pass_query_params_for_get_request(
    dispatcher: HttpDispatcher, get_tool: ToolDefinition
) -> None:
    route = respx.get("https://httpbin.example.com/get").mock(
        return_value=Response(200, json={"args": {"q": "test"}})
    )
    await dispatcher.invoke(get_tool, params={"q": "test"})
    assert route.called


@pytest.mark.asyncio
@respx.mock
async def test_invoke_should_send_json_body_for_post_request(
    dispatcher: HttpDispatcher, post_tool: ToolDefinition
) -> None:
    route = respx.post("https://httpbin.example.com/post").mock(
        return_value=Response(200, json={"json": {"message": "hello"}})
    )
    await dispatcher.invoke(post_tool, params={"message": "hello"})
    assert route.called


# ---------------------------------------------------------------------------
# JSON Schema validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invoke_should_raise_validation_error_when_required_field_missing(
    dispatcher: HttpDispatcher, post_tool: ToolDefinition
) -> None:
    result = await dispatcher.invoke(post_tool, params={})  # missing "message"
    assert not result.is_success
    assert result.error is not None
    assert "message" in result.error.lower()


@pytest.mark.asyncio
async def test_invoke_should_succeed_when_input_matches_schema(
    dispatcher: HttpDispatcher, post_tool: ToolDefinition
) -> None:
    with respx.mock:
        respx.post("https://httpbin.example.com/post").mock(
            return_value=Response(200, json={"ok": True})
        )
        result = await dispatcher.invoke(post_tool, params={"message": "hello"})
    assert result.is_success


# ---------------------------------------------------------------------------
# HTTP errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_invoke_should_return_error_result_on_404(
    dispatcher: HttpDispatcher, get_tool: ToolDefinition
) -> None:
    respx.get("https://httpbin.example.com/get").mock(
        return_value=Response(404, json={"detail": "not found"})
    )
    result = await dispatcher.invoke(get_tool, params={})
    assert not result.is_success
    assert result.status_code == 404
    assert result.error is not None
    assert len(result.error) > 0


@pytest.mark.asyncio
@respx.mock
async def test_invoke_should_return_error_result_on_500(
    dispatcher: HttpDispatcher, get_tool: ToolDefinition
) -> None:
    respx.get("https://httpbin.example.com/get").mock(
        return_value=Response(500, text="Internal Server Error")
    )
    result = await dispatcher.invoke(get_tool, params={})
    assert not result.is_success
    assert result.status_code == 500


# ---------------------------------------------------------------------------
# Retry behaviour
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_invoke_should_retry_on_5xx_and_succeed_on_second_attempt(
    dispatcher: HttpDispatcher,
) -> None:
    tool = ToolDefinition(
        name="flaky_v1",
        description="Flaky service",
        url="https://flaky.example.com/api",
        method="GET",
        retry_max_attempts=3,
        retry_backoff_seconds=0.01,  # fast for tests
    )
    call_count = 0

    def flaky_response(request):  # noqa: ANN001
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            return Response(503)
        return Response(200, json={"ok": True})

    respx.get("https://flaky.example.com/api").mock(side_effect=flaky_response)
    result = await dispatcher.invoke(tool, params={})
    assert result.is_success
    assert result.retries >= 1


@pytest.mark.asyncio
@respx.mock
async def test_invoke_should_return_error_after_exhausting_all_retries(
    dispatcher: HttpDispatcher,
) -> None:
    tool = ToolDefinition(
        name="always_fail_v1",
        description="Always fails",
        url="https://failing.example.com/api",
        method="GET",
        retry_max_attempts=2,
        retry_backoff_seconds=0.01,
    )
    respx.get("https://failing.example.com/api").mock(
        return_value=Response(503)
    )
    result = await dispatcher.invoke(tool, params={})
    assert not result.is_success


# ---------------------------------------------------------------------------
# Static headers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_invoke_should_include_static_headers_in_request(
    dispatcher: HttpDispatcher,
) -> None:
    tool = ToolDefinition(
        name="auth_tool_v1",
        description="Authenticated tool",
        url="https://secure.example.com/data",
        method="GET",
        headers={"X-Custom-Header": "my-value"},
        retry_max_attempts=1,
    )
    route = respx.get("https://secure.example.com/data").mock(
        return_value=Response(200, json={})
    )
    await dispatcher.invoke(tool, params={})
    assert route.calls[0].request.headers["X-Custom-Header"] == "my-value"


# ---------------------------------------------------------------------------
# retries count semantics
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@respx.mock
async def test_invoke_should_report_correct_retry_count_after_5xx_exhaustion(
    dispatcher: HttpDispatcher,
) -> None:
    tool = ToolDefinition(
        name="always_5xx_v1",
        description="Always 5xx",
        url="https://fail.example.com/api",
        method="GET",
        retry_max_attempts=3,
        retry_backoff_seconds=0.01,
    )
    respx.get("https://fail.example.com/api").mock(return_value=Response(503))
    result = await dispatcher.invoke(tool, params={})
    assert not result.is_success
    assert result.retries == 2  # 3 attempts → 2 retries


@pytest.mark.asyncio
async def test_send_request_should_use_app_default_timeout_when_tool_omits_timeout(
) -> None:
    client = MagicMock(spec=httpx.AsyncClient)
    request = httpx.Request("GET", "https://defaults.example.com/data")
    client.request = AsyncMock(
        return_value=Response(200, json={"ok": True}, request=request)
    )
    dispatcher = HttpDispatcher(
        client=client,
        config=MCPConfig(timeout_seconds=12.5, retry_max_attempts=3),
    )
    tool = ToolDefinition(
        name="default_timeout_v1",
        description="Uses app timeout",
        url="https://defaults.example.com/data",
        method="GET",
        retry_max_attempts=1,
        timeout_seconds=None,
    )

    result = await dispatcher._send_request(tool, params={})

    assert result.is_success
    client.request.assert_awaited_once()
    _, kwargs = client.request.call_args
    assert kwargs["timeout"] == 12.5


@pytest.mark.asyncio
async def test_invoke_should_use_app_default_retry_count_when_tool_omits_retry_override(
) -> None:
    client = MagicMock(spec=httpx.AsyncClient)
    request = httpx.Request("GET", "https://flaky.example.com/defaults")
    client.request = AsyncMock(
        side_effect=[
            Response(503, request=request),
            Response(200, json={"ok": True}, request=request),
        ]
    )
    dispatcher = HttpDispatcher(
        client=client,
        config=MCPConfig(timeout_seconds=30.0, retry_max_attempts=2),
    )
    tool = ToolDefinition(
        name="default_retry_v1",
        description="Uses app retry count",
        url="https://flaky.example.com/defaults",
        method="GET",
        retry_max_attempts=None,
        retry_backoff_seconds=0.01,
    )

    result = await dispatcher.invoke(tool, params={})

    assert result.is_success
    assert result.retries == 1
    assert client.request.await_count == 2


# ---------------------------------------------------------------------------
# _parse_body helper
# ---------------------------------------------------------------------------


def test_parse_body_should_return_dict_for_json_response() -> None:
    from http_adaptor.http_client import _parse_body

    resp = httpx.Response(200, json={"key": "val"})
    assert _parse_body(resp) == {"key": "val"}


def test_parse_body_should_return_text_for_non_json_response() -> None:
    from http_adaptor.http_client import _parse_body

    resp = httpx.Response(200, text="plain")
    assert _parse_body(resp) == "plain"
