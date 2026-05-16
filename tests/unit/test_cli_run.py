"""End-to-end CliRunner tests for ``youtrack-aitrack run``."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx
from typer.testing import CliRunner

from youtrack_aitrack.cli.init import scaffold
from youtrack_aitrack.cli.main import app
from youtrack_aitrack.domain.event import STATE_FIELD_NAME

runner = CliRunner()

BASE_URL = "https://yt.example.com"
PROJECT = "DEMO"


@pytest.fixture(autouse=True)
def _stub_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("YOUTRACK_URL", BASE_URL)
    monkeypatch.setenv("YOUTRACK_TOKEN", "tok")
    monkeypatch.setenv("YOUTRACK_PROJECT", PROJECT)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")


SMOKE_WORKFLOW = """\
name: smoke
trigger:
  type: status_change
  to_state: "Ready for testing"
actions:
  - id: mark
    type: set_field
    fields:
      Status: "audited"
"""


def _make_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "cfg"
    scaffold(cfg)
    return cfg


def _write_workflow(cfg: Path, name: str, content: str) -> None:
    (cfg / "workflows" / name).write_text(content)


def _mock_state(respx_mock: respx.MockRouter, issue: str, state: str) -> respx.Route:
    return respx_mock.get(f"/api/issues/{issue}").mock(
        return_value=httpx.Response(
            200,
            json={"customFields": [{"name": STATE_FIELD_NAME, "value": {"name": state}}]},
        )
    )


def _mock_field_metadata(respx_mock: respx.MockRouter) -> None:
    respx_mock.get(f"/api/admin/projects/{PROJECT}/customFields").mock(
        return_value=httpx.Response(
            200,
            json=[{"id": "PF-1", "$type": "SimpleProjectCustomField", "field": {"name": "Status"}}],
        )
    )


@respx.mock(base_url=BASE_URL, assert_all_called=False)
def test_run_writes_field_when_state_matches(respx_mock: respx.MockRouter, tmp_path: Path) -> None:
    cfg = _make_config(tmp_path)
    _write_workflow(cfg, "smoke.yaml", SMOKE_WORKFLOW)
    _mock_state(respx_mock, "DEMO-1", "Ready for testing")
    _mock_field_metadata(respx_mock)
    write_route = respx_mock.post("/api/issues/DEMO-1").mock(
        return_value=httpx.Response(200, json={"id": "DEMO-1"})
    )

    result = runner.invoke(app, ["--config-dir", str(cfg), "run", "DEMO-1"])

    assert result.exit_code == 0, result.output
    assert write_route.called
    body = write_route.calls.last.request.read().decode()
    assert '"value":"audited"' in body
    assert "smoke" in result.output
    assert "mark" in result.output
    assert "ok" in result.output
    assert "DONE" in result.output


@respx.mock(base_url=BASE_URL, assert_all_called=False)
def test_run_dry_run_skips_field_writes(respx_mock: respx.MockRouter, tmp_path: Path) -> None:
    cfg = _make_config(tmp_path)
    _write_workflow(cfg, "smoke.yaml", SMOKE_WORKFLOW)
    _mock_state(respx_mock, "DEMO-1", "Ready for testing")
    # Field metadata + write routes intentionally not registered: dry-run must not call them.
    write_route = respx_mock.post("/api/issues/DEMO-1").mock(
        return_value=httpx.Response(500, text="should-not-be-called")
    )

    result = runner.invoke(app, ["--config-dir", str(cfg), "run", "DEMO-1", "--dry-run"])

    assert result.exit_code == 0, result.output
    assert not write_route.called
    assert "DONE" in result.output


@respx.mock(base_url=BASE_URL, assert_all_called=False)
def test_run_no_match_when_state_differs(respx_mock: respx.MockRouter, tmp_path: Path) -> None:
    cfg = _make_config(tmp_path)
    _write_workflow(cfg, "smoke.yaml", SMOKE_WORKFLOW)
    _mock_state(respx_mock, "DEMO-1", "In progress")
    write_route = respx_mock.post("/api/issues/DEMO-1").mock(
        return_value=httpx.Response(200, json={})
    )

    result = runner.invoke(app, ["--config-dir", str(cfg), "run", "DEMO-1"])

    assert result.exit_code == 0
    assert not write_route.called
    assert "No matching workflows" in result.output


@respx.mock(base_url=BASE_URL, assert_all_called=False)
def test_run_workflow_filter_scopes_to_one_name(
    respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    cfg = _make_config(tmp_path)
    _write_workflow(cfg, "smoke.yaml", SMOKE_WORKFLOW)
    _write_workflow(cfg, "other.yaml", SMOKE_WORKFLOW.replace("smoke", "other"))
    _mock_state(respx_mock, "DEMO-1", "Ready for testing")
    _mock_field_metadata(respx_mock)
    respx_mock.post("/api/issues/DEMO-1").mock(
        return_value=httpx.Response(200, json={"id": "DEMO-1"})
    )

    result = runner.invoke(app, ["--config-dir", str(cfg), "run", "DEMO-1", "--workflow", "other"])

    assert result.exit_code == 0
    assert "other" in result.output
    assert "smoke" not in result.output


@respx.mock(base_url=BASE_URL, assert_all_called=False)
def test_run_force_bypasses_idempotency(respx_mock: respx.MockRouter, tmp_path: Path) -> None:
    cfg = _make_config(tmp_path)
    _write_workflow(cfg, "smoke.yaml", SMOKE_WORKFLOW)
    _mock_state(respx_mock, "DEMO-1", "Ready for testing")
    _mock_field_metadata(respx_mock)
    write_route = respx_mock.post("/api/issues/DEMO-1").mock(
        return_value=httpx.Response(200, json={"id": "DEMO-1"})
    )

    runner.invoke(app, ["--config-dir", str(cfg), "run", "DEMO-1"])
    runner.invoke(app, ["--config-dir", str(cfg), "run", "DEMO-1"])
    runner.invoke(app, ["--config-dir", str(cfg), "run", "DEMO-1", "--force"])

    assert write_route.call_count == 2


def test_run_missing_config_yaml_errors(tmp_path: Path) -> None:
    cfg = tmp_path / "empty"
    cfg.mkdir()
    result = runner.invoke(app, ["--config-dir", str(cfg), "run", "DEMO-1"])
    assert result.exit_code != 0


AI_WORKFLOW = """\
name: ai-smoke
trigger:
  type: status_change
  to_state: "Ready for testing"
actions:
  - id: audit
    type: ai_report
    output: { kind: custom_field, name: "Security Audit" }
    prompt: smoke.md
    model: claude-sonnet-4-6
"""


SMOKE_PROMPT = "Audit issue {{ ctx.issue.issue_id }}."


def _write_prompt(cfg: Path, name: str, content: str) -> None:
    (cfg / "prompts" / name).write_text(content)


@respx.mock(base_url=BASE_URL, assert_all_called=False)
def test_run_stub_llm_skips_anthropic_and_writes_placeholder(
    respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    cfg = _make_config(tmp_path)
    _write_workflow(cfg, "ai.yaml", AI_WORKFLOW)
    _write_prompt(cfg, "smoke.md", SMOKE_PROMPT)
    _mock_state(respx_mock, "DEMO-1", "Ready for testing")
    respx_mock.get(f"/api/admin/projects/{PROJECT}/customFields").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": "PF-1",
                    "$type": "TextProjectCustomField",
                    "field": {"name": "Security Audit"},
                }
            ],
        )
    )
    write_route = respx_mock.post("/api/issues/DEMO-1").mock(
        return_value=httpx.Response(200, json={"id": "DEMO-1"})
    )
    anthropic_route = respx.route(host="api.anthropic.com").mock(
        return_value=httpx.Response(500, text="should-not-be-called")
    )

    result = runner.invoke(app, ["--config-dir", str(cfg), "run", "DEMO-1", "--stub-llm"])

    assert result.exit_code == 0, result.output
    assert not anthropic_route.called
    # Output sink writes the ai_report text to the declared custom field.
    assert write_route.called
    body = write_route.calls.last.request.read().decode()
    assert "[STUB LLM]" in body
    assert "claude-sonnet-4-6" in body
    # YouTrack field-write payload uses the resolved field id (PF-1), not the name.
    assert '"id":"PF-1"' in body
