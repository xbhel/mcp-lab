"""ToolRegistry — CRUD, persistence, grouping, and pagination.

Tools are stored as a JSON array in a human-editable file on disk.
All writes are atomic (write-then-rename) to prevent corruption.
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

from http_adaptor.exceptions import DuplicateToolError, ToolNotFoundError
from http_adaptor.models import PaginatedToolList, ToolDefinition


class ToolRegistry:
    """In-memory registry backed by a JSON file.

    Thread safety: not guaranteed — intended for single-process MCP server use.
    """

    def __init__(self, storage_path: Path | str) -> None:
        self._path = Path(storage_path)
        self._tools: dict[str, ToolDefinition] = {}
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register(self, tool: ToolDefinition) -> None:
        """Add a new tool. Raises DuplicateToolError if name exists."""
        if tool.name in self._tools:
            raise DuplicateToolError(tool.name)
        self._tools[tool.name] = tool
        self._save()

    def delete(self, name: str) -> None:
        """Remove a tool by name. Raises ToolNotFoundError if absent."""
        if name not in self._tools:
            raise ToolNotFoundError(name)
        del self._tools[name]
        self._save()

    def get(self, name: str) -> ToolDefinition | None:
        """Return a tool by name, or None if not found."""
        return self._tools.get(name)

    def all(self) -> list[ToolDefinition]:
        """Return all registered tools in insertion order."""
        return list(self._tools.values())

    def list_tools(
        self,
        *,
        tags: list[str] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> PaginatedToolList:
        """Return a paginated, optionally tag-filtered list of tools."""
        items = list(self._tools.values())

        if tags:
            tag_set = set(tags)
            items = [t for t in items if tag_set.intersection(t.tags)]

        total = len(items)
        page = items[offset : offset + limit]
        has_more = total > offset + len(page)

        return PaginatedToolList(
            total=total,
            count=len(page),
            offset=offset,
            has_more=has_more,
            next_offset=(offset + len(page)) if has_more else None,
            items=page,
        )

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self) -> None:
        """Load tools from the JSON file. Raises ValueError on corruption."""
        if not self._path.exists():
            return
        raw = self._path.read_text(encoding="utf-8")
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"Registry storage file is corrupted at '{self._path}': {exc}"
            ) from exc

        if not isinstance(data, list):
            raise TypeError(
                f"Registry storage file is corrupted at '{self._path}': "
                "expected a JSON array at the top level."
            )

        for item in data:
            tool = ToolDefinition.model_validate(item)
            self._tools[tool.name] = tool

    def _save(self) -> None:
        """Atomically persist the current registry to the JSON file."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = [t.model_dump(mode="json") for t in self._tools.values()]

        # Atomic write: write to a temp file in the same directory then rename
        tmp_fd, tmp_path = tempfile.mkstemp(
            dir=self._path.parent, prefix=".tools_tmp_", suffix=".json"
        )
        try:
            with open(tmp_fd, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, default=str)
            Path(tmp_path).replace(self._path)
        except Exception:
            Path(tmp_path).unlink(missing_ok=True)
            raise
