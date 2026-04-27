"""MetricsCollector — in-memory per-tool call metrics.

Metrics are intentionally in-memory only for Phase 1.
They reset on server restart. Persistence can be added in a later phase.
"""

from __future__ import annotations

from http_gateway.models import MetricEntry


class MetricsCollector:
    """Thread-unsafe in-memory store for per-tool call metrics.

    Suitable for single-process async MCP server use.
    """

    def __init__(self) -> None:
        self._data: dict[str, MetricEntry] = {}

    def record_call(self, tool_name: str, *, latency_ms: float, success: bool) -> None:
        """Record one invocation result for the given tool."""
        if tool_name not in self._data:
            self._data[tool_name] = MetricEntry(tool_name=tool_name)

        entry = self._data[tool_name]
        entry.call_count += 1
        entry.total_latency_ms += latency_ms
        entry.latency_samples.append(latency_ms)

        if success:
            entry.success_count += 1
        else:
            entry.error_count += 1

    def get(self, tool_name: str) -> MetricEntry | None:
        """Return metrics for a specific tool, or None if never called."""
        return self._data.get(tool_name)

    def all_metrics(self) -> dict[str, MetricEntry]:
        """Return a snapshot of all tracked tool metrics."""
        return dict(self._data)

    def reset(self) -> None:
        """Clear all collected metrics."""
        self._data.clear()
