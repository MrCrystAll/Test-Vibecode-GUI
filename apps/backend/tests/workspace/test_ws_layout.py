# SPDX-License-Identifier: Apache-2.0
"""TC-34 AC1: project-id rules (QA T-34-2) and derived ids (PO Q3 on TC-42, QA T-36-10)."""

import sys
from pathlib import Path

import pytest

from studio_backend.workspace import InvalidProjectIdError, check_project_id, derive_project_id
from studio_backend.workspace.layout import os_path


@pytest.mark.parametrize(
    "project_id", ["a", "a" * 64, "my-project", "equipe-7", "con-project", "com10"]
)
def test_valid_ids(project_id: str) -> None:
    check_project_id(project_id)


@pytest.mark.parametrize(
    ("project_id", "rule"),
    [
        ("", "must not be empty"),
        ("a" * 65, "at most 64"),
        ("My-Proj", "lowercase"),
        ("proj_1", "lowercase"),
        ("é", "lowercase"),
        ("my proj", "lowercase"),
        ("con", "reserved by Windows"),
        ("nul", "reserved by Windows"),
        ("com1", "reserved by Windows"),
        ("lpt9", "reserved by Windows"),
    ],
)
def test_invalid_ids_name_the_broken_rule(project_id: str, rule: str) -> None:
    with pytest.raises(InvalidProjectIdError) as caught:
        check_project_id(project_id)
    assert rule in caught.value.rule
    assert caught.value.code == "invalid_project_id"


def test_uppercase_reserved_name_is_reported_as_not_lowercase_first() -> None:
    with pytest.raises(InvalidProjectIdError) as caught:
        check_project_id("NUL")
    assert "lowercase" in caught.value.rule


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Équipe 7", "equipe-7"),
        ("  My   Project!! ", "my-project"),
        ("日本語", "project"),
        ("!!!", "project"),
        ("Con", "con-project"),
        ("LPT1", "lpt1-project"),
        ("ﬁle №5", "file-no5"),  # NFKD: ligature and numero sign
        ("a" * 70, "a" * 64),
        ("a" * 63 + " b", "a" * 63),  # cut at 64 leaves "aaa…a-": trimmed again
    ],
)
def test_derived_id(name: str, expected: str) -> None:
    assert derive_project_id(name) == expected
    check_project_id(expected)


def test_derived_id_skips_taken_ids_case_insensitively() -> None:
    assert derive_project_id("My project", ["MY-PROJECT"]) == "my-project-2"
    assert derive_project_id("My project", ["my-project", "my-project-2"]) == "my-project-3"
    assert derive_project_id("日本語", ["project"]) == "project-2"


def test_derived_id_with_suffix_stays_within_64_characters() -> None:
    long_id = "a" * 64

    derived = derive_project_id("a" * 80, [long_id])

    assert derived == "a" * 62 + "-2"
    check_project_id(derived)


@pytest.mark.skipif(sys.platform != "win32", reason="extended-length paths are a Windows thing")
def test_os_path_uses_the_extended_form_on_windows(tmp_path: Path) -> None:
    assert str(os_path(tmp_path)).startswith("\\\\?\\")
    assert os_path(os_path(tmp_path)) == os_path(tmp_path)
    assert str(os_path(Path("\\\\server\\share\\ws"))) == "\\\\?\\UNC\\server\\share\\ws"


@pytest.mark.skipif(sys.platform == "win32", reason="POSIX paths are used as they are")
def test_os_path_is_just_absolute_elsewhere(tmp_path: Path) -> None:
    assert os_path(tmp_path) == tmp_path
