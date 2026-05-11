"""Tests for JinjaPromptRenderer adapter."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from jinja2 import UndefinedError

from youtrack_aitrack.adapters.llm.jinja import JinjaPromptRenderer
from youtrack_aitrack.domain.actions.ai_report import PromptRenderer
from youtrack_aitrack.domain.context import Context
from youtrack_aitrack.domain.event import IssueEvent


def _accepts_renderer(r: PromptRenderer) -> PromptRenderer:
    return r


def _make_ctx(issue_id: str = "ABC-1") -> Context:
    event = IssueEvent(
        issue_id=issue_id,
        project="ABC",
        event_kind="status_change",
        from_state="Open",
        to_state="Ready for testing",
        timestamp=datetime(2026, 5, 11, 12, 0, tzinfo=UTC),
    )
    return Context(issue=event, branch="feat/ABC-1", diff="--- a\n+++ b\n")


def _write_template(prompts_dir: Path, name: str, body: str) -> Path:
    prompts_dir.mkdir(parents=True, exist_ok=True)
    target = prompts_dir / name
    target.write_text(body)
    return target


def test_renderer_satisfies_protocol(tmp_path: Path) -> None:
    renderer = JinjaPromptRenderer(tmp_path)
    accepted = _accepts_renderer(renderer)
    assert accepted is renderer


def test_simple_substitution(tmp_path: Path) -> None:
    _write_template(tmp_path, "p.md", "Issue: {{ ctx.issue.issue_id }}\n")
    renderer = JinjaPromptRenderer(tmp_path)
    out = renderer.render("p.md", _make_ctx("XYZ-7"))
    assert out == "Issue: XYZ-7\n"


def test_nested_field_access(tmp_path: Path) -> None:
    _write_template(
        tmp_path,
        "p.md",
        "From {{ ctx.issue.from_state }} to {{ ctx.issue.to_state }} on branch {{ ctx.branch }}\n",
    )
    renderer = JinjaPromptRenderer(tmp_path)
    out = renderer.render("p.md", _make_ctx())
    assert out == "From Open to Ready for testing on branch feat/ABC-1\n"


def test_missing_template_raises_file_not_found(tmp_path: Path) -> None:
    renderer = JinjaPromptRenderer(tmp_path)
    with pytest.raises(FileNotFoundError) as exc:
        renderer.render("absent.md", _make_ctx())
    assert "absent.md" in str(exc.value)


def test_strict_undefined_raises_on_missing_variable(tmp_path: Path) -> None:
    _write_template(tmp_path, "p.md", "{{ ctx.does_not_exist }}")
    renderer = JinjaPromptRenderer(tmp_path)
    with pytest.raises(UndefinedError):
        renderer.render("p.md", _make_ctx())


def test_repeated_render_reuses_template_object(tmp_path: Path) -> None:
    _write_template(tmp_path, "p.md", "{{ ctx.issue.issue_id }}")
    renderer = JinjaPromptRenderer(tmp_path)
    t1 = renderer._env.get_template("p.md")
    t2 = renderer._env.get_template("p.md")
    assert t1 is t2


def test_template_in_subdir_resolves(tmp_path: Path) -> None:
    _write_template(tmp_path / "audits", "security.md", "audit {{ ctx.issue.issue_id }}\n")
    renderer = JinjaPromptRenderer(tmp_path)
    out = renderer.render("audits/security.md", _make_ctx("Z-9"))
    assert out == "audit Z-9\n"
