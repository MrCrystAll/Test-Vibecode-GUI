# SPDX-License-Identifier: Apache-2.0
"""Project id derivation and validation (PO rules, TC-42 Q3)."""

import re

import pytest

from studio_config_schema import PROJECT_ID_PATTERN, derive_project_id, project_id_problem


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Équipe 7", "equipe-7"),
        ("  My  Great__Project!! ", "my-great-project"),
        ("日本語", "project"),
        ("!!!", "project"),
        ("Con", "con-project"),
        ("LPT1", "lpt1-project"),
        ("com10", "com10"),
        ("ﬁnal", "final"),  # NFKD folds the ligature
    ],
)
def test_derived_id(name: str, expected: str) -> None:
    assert derive_project_id(name) == expected


def test_derived_id_is_cut_to_64_without_a_trailing_dash() -> None:
    derived = derive_project_id("a" * 63 + " b")

    assert derived == "a" * 63


def test_taken_ids_get_a_counter_case_insensitively() -> None:
    assert derive_project_id("Équipe 7", taken={"EQUIPE-7"}) == "equipe-7-2"
    assert derive_project_id("Équipe 7", taken={"equipe-7", "equipe-7-2"}) == "equipe-7-3"
    assert derive_project_id("Con", taken={"con-project"}) == "con-project-2"


def test_counter_keeps_the_id_within_64_characters() -> None:
    long_id = "x" * 64

    derived = derive_project_id(long_id, taken={long_id})

    assert derived == "x" * 62 + "-2"
    assert re.match(PROJECT_ID_PATTERN, derived)


@pytest.mark.parametrize("project_id", ["a", "equipe-7", "x" * 64, "con-project", "com10"])
def test_valid_explicit_ids(project_id: str) -> None:
    assert project_id_problem(project_id) is None


@pytest.mark.parametrize(
    ("project_id", "rule"),
    [
        ("", "1 to 64"),
        ("x" * 65, "1 to 64"),
        ("My Proj", "lowercase"),
        ("équipe", "lowercase"),
        ("con", "reserved"),
        ("aux", "reserved"),
    ],
)
def test_invalid_explicit_ids_name_the_rule(project_id: str, rule: str) -> None:
    problem = project_id_problem(project_id)

    assert problem is not None
    assert rule in problem
