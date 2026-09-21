"""Tests for deterministic branch naming."""

from __future__ import annotations

import pytest

from youtrack_aitrack.domain.branch_name import build_branch_name, slugify


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Add CSV export", "add-csv-export"),
        ("  Fix: login  --  redirect loop!  ", "fix-login-redirect-loop"),
        ("Dodaj eksport faktur do CSV (żółć)", "dodaj-eksport-faktur-do-csv-zolc"),
        ("UPPER_case_with_underscores", "upper-case-with-underscores"),
        ("", ""),
        ("!!!", ""),
    ],
)
def test_slugify_folds_to_ascii_lowercase_hyphens(text: str, expected: str) -> None:
    assert slugify(text) == expected


def test_slugify_cuts_on_word_boundary() -> None:
    assert slugify("alpha beta gamma delta", max_len=12) == "alpha-beta"
    assert slugify("alpha beta gamma delta", max_len=10) == "alpha-beta"
    assert slugify("alpha-beta", max_len=40) == "alpha-beta"


def test_slugify_single_long_word_is_hard_cut() -> None:
    assert slugify("supercalifragilistic", max_len=5) == "super"


def test_build_branch_name_default_template() -> None:
    name = build_branch_name("{task_id}-{slug}", task_id="PROJ-12", summary="Add CSV export")
    assert name == "PROJ-12-add-csv-export"


def test_build_branch_name_is_deterministic() -> None:
    a = build_branch_name("{task_id}-{slug}", task_id="PROJ-12", summary="Add CSV export")
    b = build_branch_name("{task_id}-{slug}", task_id="PROJ-12", summary="Add CSV export")
    assert a == b


def test_build_branch_name_without_slug_placeholder_ignores_summary() -> None:
    assert build_branch_name("feature/{task_id}", task_id="PROJ-12", summary=None) == (
        "feature/PROJ-12"
    )


@pytest.mark.parametrize("summary", [None, "", "???"])
def test_build_branch_name_rejects_empty_slug(summary: str | None) -> None:
    with pytest.raises(ValueError, match="empty slug"):
        build_branch_name("{task_id}-{slug}", task_id="PROJ-12", summary=summary)
