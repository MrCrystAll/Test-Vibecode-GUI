# SPDX-License-Identifier: Apache-2.0
"""TC-34 AC2: the app settings file (QA T-34-3, unit part)."""

import json
import sys
from pathlib import Path

import pytest

from studio_backend.workspace import SETTINGS_DIR_ENV, AppSettingsStore, settings_dir


@pytest.fixture
def store(tmp_path: Path) -> AppSettingsStore:
    return AppSettingsStore(tmp_path / "settings dir é")


def test_the_override_env_var_is_named_like_the_other_backend_settings() -> None:
    assert SETTINGS_DIR_ENV == "STUDIO_BACKEND_SETTINGS_DIR"


def test_settings_dir_override(tmp_path: Path) -> None:
    assert settings_dir({SETTINGS_DIR_ENV: str(tmp_path)}) == tmp_path


def test_settings_dir_defaults_to_the_os_user_config_dir() -> None:
    default = settings_dir({})
    assert default.name == "rlgym-studio"
    assert default == settings_dir({SETTINGS_DIR_ENV: "   "})  # blank means unset


def test_no_file_means_empty_settings_and_nothing_written(store: AppSettingsStore) -> None:
    settings = store.load()

    assert settings.current_workspace is None
    assert settings.recent_workspaces == []
    assert not store.directory.exists()


def test_remembered_workspace_survives_a_restart(store: AppSettingsStore, tmp_path: Path) -> None:
    workspace = tmp_path / "my ws é"

    store.remember_workspace(workspace)
    reloaded = AppSettingsStore(store.directory).load()  # a new backend reads the same dir

    assert reloaded.current_workspace == str(workspace)
    assert reloaded.recent_workspaces == [str(workspace)]
    data = json.loads(store.path.read_text(encoding="utf-8"))
    assert data["kind"] == "app-settings"
    assert data["schemaVersion"] == 1


def test_recent_list_is_most_recent_first_without_duplicates(store: AppSettingsStore) -> None:
    for name in ("a", "b", "c", "a"):
        settings = store.remember_workspace(Path(f"/ws/{name}"))

    assert settings.recent_workspaces == [str(Path(p)) for p in ("/ws/a", "/ws/c", "/ws/b")]


@pytest.mark.skipif(sys.platform != "win32", reason="Windows paths are case-insensitive")
def test_recent_list_ignores_case_on_windows(store: AppSettingsStore) -> None:
    store.remember_workspace(Path("C:/Work/WS"))
    settings = store.remember_workspace(Path("c:/work/ws"))

    assert settings.recent_workspaces == [str(Path("c:/work/ws"))]


def test_recent_list_keeps_ten(store: AppSettingsStore) -> None:
    for i in range(12):
        settings = store.remember_workspace(Path(f"/ws/{i}"))

    assert len(settings.recent_workspaces) == 10
    assert settings.recent_workspaces[0] == str(Path("/ws/11"))
    assert str(Path("/ws/1")) not in settings.recent_workspaces


def test_forget_workspace(store: AppSettingsStore) -> None:
    store.remember_workspace(Path("/ws/a"))
    store.remember_workspace(Path("/ws/b"))

    settings = store.forget_workspace(Path("/ws/b"))

    assert settings.current_workspace is None
    assert settings.recent_workspaces == [str(Path("/ws/a"))]
    assert AppSettingsStore(store.directory).load() == settings


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        (b"{oops", "invalid_json"),
        (
            b'{"kind": "app-settings", "schemaVersion": 1, "recentWorkspaces": "x"}',
            "invalid_content",
        ),
        (b'{"kind": "app-settings", "schemaVersion": 7}', "too_new"),
    ],
)
def test_unreadable_settings_are_moved_aside_not_lost(
    store: AppSettingsStore, content: bytes, reason: str, caplog: pytest.LogCaptureFixture
) -> None:
    store.directory.mkdir()
    store.path.write_bytes(content)

    settings = store.load()

    assert settings.current_workspace is None
    assert not store.path.exists()
    [aside] = list(store.directory.glob(f"settings.json.{reason}.*.json"))
    assert aside.read_bytes() == content
    assert "moved to" in caplog.text
