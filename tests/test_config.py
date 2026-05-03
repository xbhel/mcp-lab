from __future__ import annotations

from pathlib import Path

import pytest

from http_adaptor.config import load_mcp_config


def test_load_mcp_config_should_return_typed_config_from_toml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage_path = tmp_path / "from-file-tools.json"
    config_path = tmp_path / "config.toml"
    os_environ_storage = "HTTP_ADAPTOR_TEST_STORAGE_PATH"
    os_environ_host = "HTTP_ADAPTOR_TEST_HOST"

    # Placeholder values are expanded from the environment before TOML parsing.
    monkeypatch.setenv(os_environ_storage, str(storage_path))
    monkeypatch.setenv(os_environ_host, "127.0.0.10")
    config_path.write_text(
        "\n".join(
            [
                "[mcp]",
                f'storage_path = "${{{os_environ_storage}}}"',
                'transport = "sse"',
                f'host = "${{{os_environ_host}}}"',
                "port = 8123",
                "timeout_seconds = 45.0",
                "retry_max_attempts = 5",
            ]
        ),
        encoding="utf-8",
    )

    config = load_mcp_config(config_path)

    assert config.storage_path == storage_path
    assert config.transport == "sse"
    assert config.host == "127.0.0.10"
    assert config.port == 8123
    assert config.timeout_seconds == 45.0
    assert config.retry_max_attempts == 5


def test_load_mcp_config_should_raise_when_placeholder_env_var_is_missing(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    config_path.write_text(
        'storage_path = "${HTTP_ADAPTOR_MISSING_ENV}"',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="HTTP_ADAPTOR_MISSING_ENV"):
        load_mcp_config(config_path)
