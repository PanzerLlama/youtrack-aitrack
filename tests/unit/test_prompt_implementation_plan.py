"""Snapshot test for the implementation_plan prompt template (plan-mode CLI prompt)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from youtrack_aitrack.adapters.llm.jinja import JinjaPromptRenderer
from youtrack_aitrack.domain.context import Context
from youtrack_aitrack.domain.event import IssueEvent
from youtrack_aitrack.domain.issue import IssueDetails
from youtrack_aitrack.domain.run import ActionResult

EXPECTED = """You are a senior software engineer preparing to implement a YouTrack task.
Nothing has been coded yet. Your job is to understand the task, study the
codebase, and produce an implementation plan the developer will review and
discuss with you before any code changes are made.

## Task

- Issue: PROJ-12 (PROJ)
- Summary: Add CSV export
- State: Development in progress
- Branch: PROJ-12-add-csv-export

### Description

```text
Users need to download invoices as CSV.
Include date filter.
```

## How to work

You are running inside the project's working tree, on the branch named
above, in read-only planning mode. Use your file-reading and shell tools to
understand how the task fits the existing code:

- Locate the modules, routes, models, and tests the task touches. Follow
  imports and callers; do NOT browse the whole repository.
- Check existing conventions (naming, layering, test style, migrations,
  feature flags) so the plan fits the codebase rather than fighting it.
- Note anything in the description that is ambiguous, contradictory, or
  missing. Do not guess silently — surface it as a question.

Do NOT modify any file. Do NOT run formatters, tests, or build steps that
write to the tree.

## Output format

Output ONLY the plan below. No preamble ("I will explore..."), no closing
remarks, no narration of the tools you used. The text is posted verbatim as
a comment on the issue and saved to the branch for review.

Use exactly these sections, in this order. Label each section with a
**bold** line exactly as shown — do NOT use Markdown `#` headings.

**Understanding**

2-4 sentences restating the task in your own words: what changes for the
user, and what stays the same. If the description conflicts with what the
code does today, say so here.

**Open questions**

A bulleted list of decisions the developer must make before implementation
starts, each phrased as a question with the options you see. Write "None."
if the task is unambiguous.

**Proposed changes**

An ordered list of steps. Each step names the file(s) it touches (paths
relative to the repository root) and describes the change in one or two
sentences. Mark steps that can be done independently. Prefer the smallest
change that satisfies the task; mention refactors only when they are
required to land the change safely.

**Tests**

Which existing tests are affected and which new tests to add, by file and
scenario. Name the concrete behaviour each test pins down.

**Risks and rollout**

A short bulleted list: data migrations, backwards compatibility, feature
flags, performance, security-sensitive surfaces, and anything that should
be verified manually after deploy. Write "No notable risks." if none apply.
"""


def _event() -> IssueEvent:
    return IssueEvent(
        issue_id="PROJ-12",
        project="PROJ",
        event_kind="status_change",
        to_state="Development in progress",
        timestamp=datetime(2026, 9, 21, 9, 0, tzinfo=UTC),
    )


def _ctx() -> Context:
    return Context(
        issue=_event(),
        issue_details=IssueDetails(
            summary="Add CSV export",
            description="Users need to download invoices as CSV.\nInclude date filter.",
            state="Development in progress",
        ),
        repo_path=Path("/tmp/fakerepo"),
        action_outputs={
            "create_branch": ActionResult(
                action_id="create_branch",
                success=True,
                output={"branch": "PROJ-12-add-csv-export", "created": True},
            )
        },
    )


def test_implementation_plan_prompt_renders_verbatim() -> None:
    renderer = JinjaPromptRenderer(Path("prompts"))
    assert renderer.render("implementation_plan.md", _ctx()) == EXPECTED


def test_implementation_plan_prompt_guards_missing_details_and_branch() -> None:
    renderer = JinjaPromptRenderer(Path("prompts"))
    rendered = renderer.render("implementation_plan.md", Context(issue=_event()))
    assert "- Summary: unavailable" in rendered
    assert "- State: unknown" in rendered
    assert "- Branch: None" in rendered
    assert "No description provided." in rendered
