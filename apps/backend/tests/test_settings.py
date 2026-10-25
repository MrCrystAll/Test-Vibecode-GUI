# SPDX-License-Identifier: Apache-2.0
import pytest

from studio_backend.settings import Settings, SettingsError, load_settings


def test_defaults_bind_localhost_on_any_free_port() -> None:
    assert load_settings([], env={}) == Settings(host="127.0.0.1", port=0, log_level="info")


def test_env_vars_override_defaults() -> None:
    env = {
        "STUDIO_BACKEND_HOST": "::1",
        "STUDIO_BACKEND_PORT": "8123",
        "STUDIO_BACKEND_LOG_LEVEL": "DEBUG",
    }

    assert load_settings([], env=env) == Settings(host="::1", port=8123, log_level="debug")


def test_cli_args_override_env_vars() -> None:
    env = {"STUDIO_BACKEND_PORT": "8123", "STUDIO_BACKEND_LOG_LEVEL": "debug"}

    settings = load_settings(["--port", "9000", "--log-level", "warning"], env=env)

    assert settings.port == 9000
    assert settings.log_level == "warning"


@pytest.mark.parametrize("port", ["-1", "65536", "abc"])
def test_invalid_port_is_rejected(port: str) -> None:
    with pytest.raises(SettingsError, match="--port"):
        load_settings(["--port", port], env={})


def test_invalid_env_log_level_is_rejected() -> None:
    with pytest.raises(SettingsError, match="STUDIO_BACKEND_LOG_LEVEL"):
        load_settings([], env={"STUDIO_BACKEND_LOG_LEVEL": "loud"})
