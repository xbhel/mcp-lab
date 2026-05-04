"""Tests for MetricsCollector — per-tool call tracking."""

from __future__ import annotations

from pathlib import Path

import pytest

from http2mcp.metrics import MetricsCollector
from http2mcp.models import MetricEntry

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def collector(tmp_path: Path) -> MetricsCollector:
    return MetricsCollector(tmp_path / "metrics.json")


# ---------------------------------------------------------------------------
# record_call
# ---------------------------------------------------------------------------


def test_record_call_should_increment_call_count_on_success(
    collector: MetricsCollector,
) -> None:
    collector.record_call("my_tool", latency_ms=42.0, success=True)
    entry = collector.get("my_tool")
    assert entry is not None
    assert entry.call_count == 1
    assert entry.success_count == 1
    assert entry.error_count == 0


def test_record_call_should_increment_error_count_on_failure(
    collector: MetricsCollector,
) -> None:
    collector.record_call("my_tool", latency_ms=10.0, success=False)
    entry = collector.get("my_tool")
    assert entry is not None
    assert entry.call_count == 1
    assert entry.error_count == 1
    assert entry.success_count == 0


def test_record_call_should_accumulate_latency(
    collector: MetricsCollector,
) -> None:
    collector.record_call("my_tool", latency_ms=100.0, success=True)
    collector.record_call("my_tool", latency_ms=200.0, success=True)
    entry = collector.get("my_tool")
    assert entry is not None
    assert entry.avg_latency_ms == pytest.approx(150.0)


def test_record_call_should_track_multiple_tools_independently(
    collector: MetricsCollector,
) -> None:
    collector.record_call("tool_a", latency_ms=10.0, success=True)
    collector.record_call("tool_b", latency_ms=20.0, success=False)
    tool_a = collector.get("tool_a")
    tool_b = collector.get("tool_b")
    assert tool_a is not None
    assert tool_b is not None
    assert tool_a.success_count == 1
    assert tool_b.error_count == 1


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


def test_get_should_return_none_for_unknown_tool(
    collector: MetricsCollector,
) -> None:
    assert collector.get("unknown") is None


def test_get_should_return_metric_entry_after_first_call(
    collector: MetricsCollector,
) -> None:
    collector.record_call("my_tool", latency_ms=5.0, success=True)
    entry = collector.get("my_tool")
    assert isinstance(entry, MetricEntry)


# ---------------------------------------------------------------------------
# all_metrics
# ---------------------------------------------------------------------------


def test_all_metrics_should_return_empty_dict_when_no_calls_recorded(
    collector: MetricsCollector,
) -> None:
    assert collector.all_metrics() == {}


def test_all_metrics_should_return_all_tracked_tools(
    collector: MetricsCollector,
) -> None:
    collector.record_call("tool_a", latency_ms=10.0, success=True)
    collector.record_call("tool_b", latency_ms=20.0, success=True)
    metrics = collector.all_metrics()
    assert "tool_a" in metrics
    assert "tool_b" in metrics


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------


def test_reset_should_clear_all_metrics(collector: MetricsCollector) -> None:
    collector.record_call("my_tool", latency_ms=10.0, success=True)
    collector.reset()
    assert collector.all_metrics() == {}


# ---------------------------------------------------------------------------
# computed properties on MetricEntry
# ---------------------------------------------------------------------------


def test_success_rate_should_be_zero_when_no_calls_recorded() -> None:
    entry = MetricEntry(tool_name="t")
    assert entry.success_rate == 0.0


def test_p95_latency_should_return_correct_percentile() -> None:
    entry = MetricEntry(tool_name="t", latency_samples=list(range(1, 101)))
    # 95th percentile of 1..100 is 95
    assert entry.p95_latency_ms == 95.0


# ---------------------------------------------------------------------------
# T-01: persistence (save / load)
# ---------------------------------------------------------------------------


def test_save_should_write_metrics_to_json_file(
    collector: MetricsCollector, tmp_path
) -> None:
    collector.record_call("tool_a", latency_ms=10.0, success=True)
    collector.record_call("tool_b", latency_ms=5.0, success=False)

    path = tmp_path / "metrics.json"
    collector.save(path)

    assert path.exists()
    import json
    data = json.loads(path.read_text())
    assert "tool_a" in data
    assert "tool_b" in data
    assert data["tool_a"]["call_count"] == 1


def test_load_should_restore_metrics_from_json_file(
    collector: MetricsCollector, tmp_path
) -> None:
    collector.record_call("tool_a", latency_ms=20.0, success=True)
    collector.record_call("tool_a", latency_ms=30.0, success=True)
    path = tmp_path / "metrics.json"
    collector.save(path)

    fresh = MetricsCollector(path)
    fresh.load(path)

    entry = fresh.get("tool_a")
    assert entry is not None
    assert entry.call_count == 2
    assert entry.success_count == 2


def test_load_should_be_a_no_op_when_file_does_not_exist(
    tmp_path,
) -> None:
    missing_path = tmp_path / "missing.json"
    fresh = MetricsCollector(missing_path)
    fresh.load(missing_path)
    assert fresh.all_metrics() == {}
