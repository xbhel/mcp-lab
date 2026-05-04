"""Tests for ToolRegistry — CRUD, persistence, grouping, and pagination."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from http2mcp.exceptions import DuplicateToolError, ToolNotFoundError
from http2mcp.models import ToolDefinition
from http2mcp.registry import ToolRegistry

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_registry_path(tmp_path: Path) -> Path:
    return tmp_path / "tools.json"


@pytest.fixture
def registry(tmp_registry_path: Path) -> ToolRegistry:
    return ToolRegistry(storage_path=tmp_registry_path)


@pytest.fixture
def tool_def() -> ToolDefinition:
    return ToolDefinition(
        name="weather_get_forecast_v1",
        description="Get weather forecast",
        url="https://api.weather.example.com/forecast",
        method="GET",
        tags=["weather", "public"],
    )


@pytest.fixture
def another_tool_def() -> ToolDefinition:
    return ToolDefinition(
        name="news_list_headlines_v1",
        description="List top news headlines",
        url="https://api.news.example.com/headlines",
        method="GET",
        tags=["news"],
    )


# ---------------------------------------------------------------------------
# register
# ---------------------------------------------------------------------------


def test_register_should_add_tool_to_registry(
    registry: ToolRegistry, tool_def: ToolDefinition
) -> None:
    registry.register(tool_def)
    assert registry.get("weather_get_forecast_v1") == tool_def


def test_register_should_raise_when_tool_name_already_exists(
    registry: ToolRegistry, tool_def: ToolDefinition
) -> None:
    registry.register(tool_def)
    with pytest.raises(DuplicateToolError, match="weather_get_forecast_v1"):
        registry.register(tool_def)


def test_register_should_persist_tool_to_json_file(
    registry: ToolRegistry, tool_def: ToolDefinition, tmp_registry_path: Path
) -> None:
    registry.register(tool_def)
    data = json.loads(tmp_registry_path.read_text())
    assert any(t["name"] == "weather_get_forecast_v1" for t in data)


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


def test_delete_should_remove_tool_from_registry(
    registry: ToolRegistry, tool_def: ToolDefinition
) -> None:
    registry.register(tool_def)
    registry.delete("weather_get_forecast_v1")
    assert registry.get("weather_get_forecast_v1") is None


def test_delete_should_raise_when_tool_not_found(registry: ToolRegistry) -> None:
    with pytest.raises(ToolNotFoundError, match="unknown_tool"):
        registry.delete("unknown_tool")


def test_delete_should_persist_removal_to_json_file(
    registry: ToolRegistry, tool_def: ToolDefinition, tmp_registry_path: Path
) -> None:
    registry.register(tool_def)
    registry.delete("weather_get_forecast_v1")
    data = json.loads(tmp_registry_path.read_text())
    assert not any(t["name"] == "weather_get_forecast_v1" for t in data)


# ---------------------------------------------------------------------------
# list / pagination
# ---------------------------------------------------------------------------


def test_list_should_return_all_registered_tools(
    registry: ToolRegistry,
    tool_def: ToolDefinition,
    another_tool_def: ToolDefinition,
) -> None:
    registry.register(tool_def)
    registry.register(another_tool_def)
    result = registry.list_tools()
    assert result.total == 2
    assert len(result.items) == 2


def test_list_should_paginate_with_limit_and_offset(
    registry: ToolRegistry,
    tool_def: ToolDefinition,
    another_tool_def: ToolDefinition,
) -> None:
    registry.register(tool_def)
    registry.register(another_tool_def)
    result = registry.list_tools(limit=1, offset=0)
    assert result.count == 1
    assert result.has_more is True
    assert result.next_offset == 1


def test_list_should_return_empty_when_no_tools_registered(
    registry: ToolRegistry,
) -> None:
    result = registry.list_tools()
    assert result.total == 0
    assert result.items == []
    assert result.has_more is False


# ---------------------------------------------------------------------------
# filter by tags
# ---------------------------------------------------------------------------


def test_list_should_filter_by_single_tag(
    registry: ToolRegistry,
    tool_def: ToolDefinition,
    another_tool_def: ToolDefinition,
) -> None:
    registry.register(tool_def)
    registry.register(another_tool_def)
    result = registry.list_tools(tags=["weather"])
    assert result.total == 1
    assert result.items[0].name == "weather_get_forecast_v1"


def test_list_should_return_empty_when_no_tools_match_tag(
    registry: ToolRegistry, tool_def: ToolDefinition
) -> None:
    registry.register(tool_def)
    result = registry.list_tools(tags=["nonexistent"])
    assert result.total == 0


# ---------------------------------------------------------------------------
# load from disk
# ---------------------------------------------------------------------------


def test_registry_should_load_persisted_tools_on_init(
    tmp_registry_path: Path, tool_def: ToolDefinition
) -> None:
    # Persist via first registry instance
    r1 = ToolRegistry(storage_path=tmp_registry_path)
    r1.register(tool_def)

    # Second instance loads from the same file
    r2 = ToolRegistry(storage_path=tmp_registry_path)
    assert r2.get("weather_get_forecast_v1") is not None


def test_registry_should_start_empty_when_storage_file_missing(
    tmp_registry_path: Path,
) -> None:
    registry = ToolRegistry(storage_path=tmp_registry_path)
    assert registry.list_tools().total == 0


def test_registry_should_raise_on_corrupted_storage_file(
    tmp_registry_path: Path,
) -> None:
    tmp_registry_path.write_text("NOT VALID JSON")
    with pytest.raises(ValueError, match="corrupted"):
        ToolRegistry(storage_path=tmp_registry_path)
