"""MetricsCollector — in-memory per-tool call metrics with optional persistence."""

from __future__ import annotations

import json
from pathlib import Path

from http2mcp.models import MetricEntry


class MetricsCollector:
    """Thread-unsafe in-memory store for per-tool call metrics.

    Suitable for single-process async MCP server use.
    """

    def __init__(self, storage_path: Path) -> None:
        self._data: dict[str, MetricEntry] = {}
        self._storage_path = storage_path

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

    def save(self, path: Path) -> None:
        """Persist all metrics to a JSON file at *path*."""
        payload = {name: entry.model_dump() for name, entry in self._data.items()}
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload), encoding="utf-8")
        tmp.replace(path)

    def load(self, path: Path) -> None:
        """Restore metrics from a JSON file. Silently skips when the file is absent."""
        if not path.exists():
            return
        raw = json.loads(path.read_text(encoding="utf-8"))
        self._data = {name: MetricEntry.model_validate(entry) for name, entry in raw.items()}
