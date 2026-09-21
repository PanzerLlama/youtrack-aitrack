"""BeadsCliClient — availability detection and bd create invocation via a fake bd script."""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

from youtrack_aitrack.adapters.beads.client import BeadsCliClient, BeadsError
from youtrack_aitrack.domain.actions.bd_issue import IssueTrackerClient, TrackedIssue


def _fake_bd(path: Path, body: str) -> Path:
    path.write_text(f"#!/usr/bin/env bash\n{body}\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _accepts(c: IssueTrackerClient) -> IssueTrackerClient:
    return c


def _issue() -> TrackedIssue:
    return TrackedIssue(
        title="PROJ-12: Add CSV export",
        body="**Understanding**\nline two\n",
        issue_type="feature",
        priority=1,
        external_ref="PROJ-12",
    )


def test_satisfies_protocol() -> None:
    client = BeadsCliClient()
    assert _accepts(client) is client


def test_unavailable_without_beads_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    _fake_bd(bin_dir / "bd", "echo x")
    monkeypatch.setenv("PATH", str(bin_dir))
    repo = tmp_path / "repo"
    repo.mkdir()

    assert BeadsCliClient().is_available(repo) is False
    (repo / ".beads").mkdir()
    assert BeadsCliClient().is_available(repo) is True


def test_unavailable_without_binary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "empty"))
    (tmp_path / ".beads").mkdir()
    assert BeadsCliClient(binary="definitely-not-bd").is_available(tmp_path) is False


def test_create_issue_passes_fields_and_body_on_stdin(tmp_path: Path) -> None:
    log = tmp_path / "args.log"
    body = tmp_path / "body.log"
    fake = _fake_bd(
        tmp_path / "bd",
        f'printf "%s\\n" "$@" > "{log}"\ncat > "{body}"\necho "proj-a1b2"',
    )

    issue_id = BeadsCliClient(binary=str(fake)).create_issue(tmp_path, _issue())

    assert issue_id == "proj-a1b2"
    args = log.read_text().splitlines()
    assert args[:2] == ["create", "--silent"]
    assert args[args.index("--title") + 1] == "PROJ-12: Add CSV export"
    assert args[args.index("--type") + 1] == "feature"
    assert args[args.index("--priority") + 1] == "1"
    assert args[args.index("--body-file") + 1] == "-"
    assert args[args.index("--external-ref") + 1] == "PROJ-12"
    assert body.read_text() == "**Understanding**\nline two\n"


def test_create_issue_omits_external_ref_when_none(tmp_path: Path) -> None:
    log = tmp_path / "args.log"
    fake = _fake_bd(tmp_path / "bd", f'printf "%s\\n" "$@" > "{log}"\necho "id-1"')
    issue = TrackedIssue(title="t", body="b", external_ref=None)

    BeadsCliClient(binary=str(fake)).create_issue(tmp_path, issue)

    assert "--external-ref" not in log.read_text().splitlines()


def test_create_issue_raises_on_failure(tmp_path: Path) -> None:
    fake = _fake_bd(tmp_path / "bd", 'echo "no database" >&2\nexit 3')
    with pytest.raises(BeadsError, match="no database"):
        BeadsCliClient(binary=str(fake)).create_issue(tmp_path, _issue())


def test_create_issue_raises_on_empty_output(tmp_path: Path) -> None:
    fake = _fake_bd(tmp_path / "bd", "cat > /dev/null")
    with pytest.raises(BeadsError, match="no issue id"):
        BeadsCliClient(binary=str(fake)).create_issue(tmp_path, _issue())


def test_create_issue_raises_when_binary_missing(tmp_path: Path) -> None:
    with pytest.raises(BeadsError, match="not found"):
        BeadsCliClient(binary=str(tmp_path / "nope")).create_issue(tmp_path, _issue())
