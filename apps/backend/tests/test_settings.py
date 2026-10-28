# SPDX-License-Identifier: Apache-2.0
import pytest

from studio_backend.settings import Settings, SettingsError, load_settings

TOKEN = "env-token-0123456789-abcdefghijklmnop"  # noqa: S105 - test value


def test_defaults_bind_localhost_on_any_free_port() -> None:
    settings = load_settings([], env={})

    assert settings == Settings(host="127.0.0.1", port=0, log_level="info", token=settings.token)
    assert settings.allowed_origins == ()
    assert not settings.unsafe_bind_any
    assert not settings.shutdown_on_stdin_eof


def test_env_vars_override_defaults() -> None:
    env = {
        "STUDIO_BACKEND_PORT": "8123",
        "STUDIO_BACKEND_LOG_LEVEL": "DEBUG",
        "STUDIO_BACKEND_TOKEN": TOKEN,
        "STUDIO_BACKEND_ALLOWED_ORIGINS": "http://localhost:4200, app://studio",
    }

    assert load_settings([], env=env) == Settings(
        host="127.0.0.1",
        port=8123,
        log_level="debug",
        token=TOKEN,
        allowed_origins=("http://localhost:4200", "app://studio"),
    )


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


def test_generated_tokens_are_long_random_and_url_safe() -> None:
    first, second = load_settings([], env={}).token, load_settings([], env={}).token

    assert first != second
    assert len(first) >= 43  # 32 random bytes, base64url
    assert set(first) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_")


@pytest.mark.parametrize("token", ["short", "x" * 31, "has space " + "x" * 32, "é" * 40])
def test_weak_or_unsafe_env_token_is_rejected(token: str) -> None:
    with pytest.raises(SettingsError, match="STUDIO_BACKEND_TOKEN"):
        load_settings([], env={"STUDIO_BACKEND_TOKEN": token})


def test_token_is_not_in_the_settings_repr() -> None:
    settings = load_settings([], env={"STUDIO_BACKEND_TOKEN": TOKEN})

    assert TOKEN not in repr(settings)


@pytest.mark.parametrize("host", ["0.0.0.0", "::1", "localhost", "192.168.1.10"])  # noqa: S104
def test_non_loopback_host_is_refused_without_the_dev_flag(host: str) -> None:
    with pytest.raises(SettingsError, match="unsafe-bind-any"):
        load_settings(["--host", host], env={})


def test_dev_flag_allows_another_host() -> None:
    assert load_settings(["--host", "0.0.0.0", "--unsafe-bind-any"], env={}).host == "0.0.0.0"  # noqa: S104
    env = {"STUDIO_BACKEND_HOST": "0.0.0.0", "STUDIO_BACKEND_UNSAFE_BIND_ANY": "1"}  # noqa: S104
    assert load_settings([], env=env).unsafe_bind_any


def test_cli_origins_replace_env_origins() -> None:
    env = {"STUDIO_BACKEND_ALLOWED_ORIGINS": "http://a.test"}

    settings = load_settings(
        ["--allowed-origin", "app://x", "--allowed-origin", "app://y"], env=env
    )

    assert settings.allowed_origins == ("app://x", "app://y")


@pytest.mark.parametrize(
    ("argv", "env"),
    [
        (["--shutdown-on-stdin-eof"], {}),
        ([], {"STUDIO_BACKEND_SHUTDOWN_ON_STDIN_EOF": "1"}),
    ],
)
def test_shutdown_on_stdin_eof_is_opt_in(argv: list[str], env: dict[str, str]) -> None:
    assert load_settings(argv, env=env).shutdown_on_stdin_eof
