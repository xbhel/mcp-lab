"""Public exceptions for http-adaptor."""

from __future__ import annotations


class InvalidOpenAPISpecError(ValueError):
    """Raised when the provided file is not a valid OpenAPI spec."""


class ToolNotFoundError(KeyError):
    """Raised when a tool name is not found in the registry."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name

    def __str__(self) -> str:
        return f"Tool '{self.name}' not found in registry."


class DuplicateToolError(ValueError):
    """Raised when registering a tool whose name already exists."""

    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.name = name

    def __str__(self) -> str:
        return f"Tool '{self.name}' is already registered. Use a different name or version suffix."
