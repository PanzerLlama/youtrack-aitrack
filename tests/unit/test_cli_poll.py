"""End-to-end CliRunner tests for ``youtrack-aitrack poll``."""

from __future__ import annotations

import json
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


def _activities_response(
    *,
    issue_id: str,
    to_state: str,
    cursor: str,
) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "afterCursor": cursor,
            "activities": [
                {
                    "id": "A1",
                    "timestamp": 1_700_000_000_000,
                    "category": {"id": "CustomFieldCategory"},
                    "author": {"login": "alice"},
                    "target": {"idReadable": issue_id, "project": {"shortName": PROJECT}},
                    "field": {
                        "name": STATE_FIELD_NAME,
                        "customField": {"name": STATE_FIELD_NAME},
                    },
                    "added": [{"name": to_state}],
                    "removed": [{"name": "In progress"}],
                }
            ],
        },
    )


@respx.mock(base_url=BASE_URL, assert_all_called=False)
def test_poll_one_shot_dispatches_and_saves_cursor(
    respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    cfg = _make_config(tmp_path)
    _write_workflow(cfg, "smoke.yaml", SMOKE_WORKFLOW)
    respx_mock.get("/api/activitiesPage").mock(
        return_value=_activities_response(
            issue_id="DEMO-1", to_state="Ready for testing", cursor="cur-1"
        )
    )
    respx_mock.get(f"/api/admin/projects/{PROJECT}/customFields").mock(
        return_value=httpx.Response(
            200,
            json=[{"id": "PF-1", "$type": "SimpleProjectCustomField", "field": {"name": "Status"}}],
        )
    )
    write_route = respx_mock.post("/api/issues/DEMO-1").mock(
        return_value=httpx.Response(200, json={"id": "DEMO-1"})
    )

    result = runner.invoke(app, ["--config-dir", str(cfg), "poll"])

    assert result.exit_code == 0, result.output
    assert write_route.called
    assert "events=1" in result.output
    assert "workflows_fired=1" in result.output
    cursor_file = cfg / "runs" / ".cursor.json"
    assert cursor_file.is_file()
    assert json.loads(cursor_file.read_text()) == {"cursor": "cur-1"}


@respx.mock(base_url=BASE_URL, assert_all_called=False)
def test_poll_no_events_still_saves_cursor(respx_mock: respx.MockRouter, tmp_path: Path) -> None:
    cfg = _make_config(tmp_path)
    _write_workflow(cfg, "smoke.yaml", SMOKE_WORKFLOW)
    respx_mock.get("/api/activitiesPage").mock(
        return_value=httpx.Response(200, json={"afterCursor": "cur-empty", "activities": []})
    )

    result = runner.invoke(app, ["--config-dir", str(cfg), "poll"])

    assert result.exit_code == 0
    assert "events=0" in result.output
    cursor_file = cfg / "runs" / ".cursor.json"
    assert json.loads(cursor_file.read_text()) == {"cursor": "cur-empty"}


@respx.mock(base_url=BASE_URL, assert_all_called=False)
def test_poll_daemon_with_max_iterations_runs_and_exits(
    respx_mock: respx.MockRouter, tmp_path: Path
) -> None:
    cfg = _make_config(tmp_path)
    _write_workflow(cfg, "smoke.yaml", SMOKE_WORKFLOW)
    activity_route = respx_mock.get("/api/activitiesPage").mock(
        return_value=httpx.Response(200, json={"afterCursor": "cur-d", "activities": []})
    )

    result = runner.invoke(
        app,
        [
            "--config-dir",
            str(cfg),
            "poll",
            "--daemon",
            "--interval-seconds",
            "0.001",
            "--max-iterations",
            "2",
        ],
    )

    assert result.exit_code == 0, result.output
    assert activity_route.call_count == 2
    assert result.output.count("poll: cursor") == 2


def test_poll_missing_config_errors(tmp_path: Path) -> None:
    cfg = tmp_path / "empty"
    cfg.mkdir()
    result = runner.invoke(app, ["--config-dir", str(cfg), "poll"])
    assert result.exit_code != 0
