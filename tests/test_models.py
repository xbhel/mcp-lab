from __future__ import annotations

import pytest

from http2mcp.models import InvokeResult, MetricEntry, ToolDefinition


def test_tool_definition_should_raise_when_method_is_invalid() -> None:
    with pytest.raises(ValueError, match="Invalid HTTP method"):
        ToolDefinition(
            name="invalid_method_tool",
            description="Invalid method",
            url="https://example.com/tool",
            method="TRACE",
        )


def test_tool_definition_should_raise_when_url_is_not_http_or_https() -> None:
    with pytest.raises(ValueError, match="URL must start with 'http://' or 'https://'"):
        ToolDefinition(
            name="invalid_url_tool",
            description="Invalid URL",
            url="ftp://example.com/tool",
        )


def test_metric_entry_avg_latency_should_return_zero_when_no_calls_recorded() -> None:
    entry = MetricEntry(tool_name="tool_x")
    assert entry.avg_latency_ms == 0.0


def test_metric_entry_p95_latency_should_return_zero_when_no_samples() -> None:
    entry = MetricEntry(tool_name="tool_x")
    assert entry.p95_latency_ms == 0.0


def test_invoke_result_should_report_failure_when_status_is_non_2xx() -> None:
    result = InvokeResult(
        tool_name="tool_x",
        status_code=500,
        body="",
        latency_ms=1.0,
        error="boom",
    )
    assert result.is_success is False
