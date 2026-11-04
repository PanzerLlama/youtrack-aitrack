"""Shared fixtures for the unit suite."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _plain_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Render CLI output without ANSI escapes, locally and on CI alike.

    GitHub Actions advertises a colour terminal, so Rich styles option names
    inside Typer's error panels and splits the text with escape codes; a plain
    substring assertion then passes locally and fails on CI. NO_COLOR only drops
    colours (bold/dim remain), TERM=dumb disables styling entirely.
    """
    monkeypatch.setenv("NO_COLOR", "1")
    monkeypatch.setenv("TERM", "dumb")
    monkeypatch.delenv("FORCE_COLOR", raising=False)
