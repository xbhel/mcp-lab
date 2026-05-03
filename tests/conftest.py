# Shared test fixtures for http_adaptor tests
import pytest


@pytest.fixture
def sample_tool_definition():
    """Minimal valid ToolDefinition dict for use in tests."""
    return {
        "name": "test_get_hello_v1",
        "description": "A test HTTP GET tool",
        "url": "https://example.com/hello",
        "method": "GET",
        "tags": ["test"],
    }
