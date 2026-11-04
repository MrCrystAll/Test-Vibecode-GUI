# SPDX-License-Identifier: Apache-2.0
"""TC-34: the workspace marker and the app settings file (QA T-34-3, T-34-4)."""

import json
from pathlib import Path
from typing import Any

import pytest

from studio_config_schema import (
    MAX_RECENT_WORKSPACES,
    AppSettings,
    ErrorReason,
    SchemaFileError,
    WorkspaceMarker,
    dumps,
    loads,
)

QA_WORKSPACES = Path(__file__).resolve().parents[3] / "tests" / "fixtures" / "workspaces"


def test_marker_is_just_the_envelope() -> None:
    marker = loads('{"kind": "workspace", "schemaVersion": 1}', WorkspaceMarker)

    assert dumps(marker) == '{\n  "kind": "workspace",\n  "schemaVersion": 1\n}\n'


@pytest.mark.skipif(not QA_WORKSPACES.is_dir(), reason="package extracted from the monorepo")
def test_qa_fixture_markers_load() -> None:
    markers = sorted(QA_WORKSPACES.glob("*/.studio/workspace.json"))
    assert markers, "QA's workspace fixtures should contain markers"
    for marker in markers:
        loads(marker.read_bytes(), WorkspaceMarker, path=marker)


@pytest.mark.parametrize(
    ("data", "pointer"),
    [
        ({"kind": "project", "schemaVersion": 1}, "/kind"),
        ({"kind": "workspace"}, "/schemaVersion"),
    ],
)
def test_marker_rejects_wrong_content(data: dict[str, Any], pointer: str) -> None:
    with pytest.raises(SchemaFileError) as caught:
        loads(json.dumps(data), WorkspaceMarker)
    assert caught.value.reason is ErrorReason.INVALID_CONTENT
    assert caught.value.pointer == pointer


def test_marker_from_a_newer_studio_is_too_new() -> None:
    with pytest.raises(SchemaFileError) as caught:
        loads('{"kind": "workspace", "schemaVersion": 2}', WorkspaceMarker)
    assert caught.value.reason is ErrorReason.TOO_NEW


def test_app_settings_defaults() -> None:
    settings = loads('{"kind": "app-settings", "schemaVersion": 1}', AppSettings)

    assert settings.current_workspace is None
    assert settings.recent_workspaces == []


def test_app_settings_round_trip_keeps_non_ascii_paths() -> None:
    text = dumps(
        AppSettings.model_validate(
            {
                "kind": "app-settings",
                "schemaVersion": 1,
                "currentWorkspace": r"C:\Users\Zoé\RL studio",
                "recentWorkspaces": [r"C:\Users\Zoé\RL studio", "/home/zoé/ws"],
            }
        )
    )

    assert "Zoé" in text  # UTF-8, no \u escapes
    recent = loads(text, AppSettings).recent_workspaces
    assert recent == [r"C:\Users\Zoé\RL studio", "/home/zoé/ws"]


@pytest.mark.parametrize(
    ("changes", "pointer"),
    [
        ({"currentWorkspace": ""}, "/currentWorkspace"),
        ({"currentWorkspace": 3}, "/currentWorkspace"),
        ({"recentWorkspaces": "/ws"}, "/recentWorkspaces"),
        (
            {"recentWorkspaces": [f"/ws{i}" for i in range(MAX_RECENT_WORKSPACES + 1)]},
            "/recentWorkspaces",
        ),
    ],
)
def test_app_settings_rejects_wrong_content(changes: dict[str, Any], pointer: str) -> None:
    data = {"kind": "app-settings", "schemaVersion": 1, **changes}
    with pytest.raises(SchemaFileError) as caught:
        loads(json.dumps(data), AppSettings)
    assert caught.value.pointer == pointer
