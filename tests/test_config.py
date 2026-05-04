from __future__ import annotations

from pathlib import Path

import pytest

from http2mcp.config import load_mcp_config


def test_load_mcp_config_should_return_typed_config_from_toml(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    work_dir = tmp_path / "from-file"
    config_path = tmp_path / "config.toml"
    os_environ_work_dir = "http2mcp_TEST_WORK_DIR"
    os_environ_host = "http2mcp_TEST_HOST"

    # Placeholder values are expanded from the environment before TOML parsing.
    monkeypatch.setenv(os_environ_work_dir, str(work_dir))
    monkeypatch.setenv(os_environ_host, "127.0.0.10")
    config_path.write_text(
        "\n".join(
            [
                "[mcp]",
                f'work_dir = "${{{os_environ_work_dir}}}"',
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

    assert config.work_dir == work_dir
    assert config.tools_storage_path == work_dir / "tools.json"
    assert config.metrics_storage_path == work_dir / "metrics.json"
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
        "[mcp]\nwork_dir = \"${http2mcp_MISSING_ENV}\"",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="http2mcp_MISSING_ENV"):
        load_mcp_config(config_path)
