"""Snapshot test for the qa_plan prompt template."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from youtrack_aitrack.adapters.llm.jinja import JinjaPromptRenderer
from youtrack_aitrack.domain.context import Context
from youtrack_aitrack.domain.event import IssueEvent
from youtrack_aitrack.domain.run import ActionResult

_PAGES_TEXT = """Touched pages:
- /checkout (new coupon field)
- /cart (totals recalc)
Feature flag: coupons_v2"""


EXPECTED = """You are a senior QA engineer. A YouTrack issue has just transitioned to
"Ready for testing" and the team needs a focused, prioritised manual
browser-testing plan tailored to the change. An upstream "pages_changed"
report has already summarised which pages and features were touched —
use it as the source of truth for scope.

## Issue metadata

- Issue: UI-7 (UI)
- Event: status_change
- Transition: In Progress -> Ready for testing
- Actor: alice
- Timestamp: 2026-05-11 12:00:00+00:00
- Branch: UI-7-coupons

## Upstream pages_changed report

```text
Touched pages:
- /checkout (new coupon field)
- /cart (totals recalc)
Feature flag: coupons_v2
```

## What to produce

Read the pages_changed report above and the issue metadata, then design a
manual QA test plan a human tester can execute in a browser. Cover the
pages and features the report names. Do NOT invent surface area the
report does not mention.

Group steps into three priority bands:

- **P1** — happy path through every page/feature listed, plus the single
  most likely critical regression for each.
- **P2** — edge cases, form / input validation, empty and error states,
  boundary values, permission variants.
- **P3** — cross-browser checks (latest Chrome, Firefox, Safari) and
  responsive checks (desktop, tablet, mobile widths).

Each step MUST be a numbered item with this shape:

1. **<page or feature>** — <action to perform>. Expected: <observable
   outcome>.

Keep steps atomic: one action, one observable expectation. Skip a band
entirely if the report yields nothing for it; do not pad.

## Output format

Reply in Markdown using exactly these three sections, in this order:

## Summary

One short paragraph (2-4 sentences) describing the scope of testing and
what a tester should focus on.

## Test Plan

Three subsections — `### P1`, `### P2`, `### P3` — each containing the
numbered steps for that band. Omit a subsection if it would be empty.

## Regression Watchlist

A short bulleted list of areas not directly changed but downstream of
changed components (shared layouts, navigation, auth, billing). For each
entry give the area and the one symptom a tester should glance at.
"""


def _ctx() -> Context:
    event = IssueEvent(
        issue_id="UI-7",
        project="UI",
        event_kind="status_change",
        from_state="In Progress",
        to_state="Ready for testing",
        actor="alice",
        timestamp=datetime(2026, 5, 11, 12, 0, tzinfo=UTC),
    )
    pages_result = ActionResult(
        action_id="pages_changed",
        success=True,
        output={"text": _PAGES_TEXT, "model": "claude-sonnet-4-6"},
    )
    return Context(
        issue=event,
        branch="UI-7-coupons",
        diff="diff --git a/cart.py b/cart.py",
        action_outputs={"pages_changed": pages_result},
    )


def test_qa_plan_prompt_renders_verbatim() -> None:
    renderer = JinjaPromptRenderer(Path("prompts"))
    rendered = renderer.render("qa_plan.md", _ctx())
    assert rendered == EXPECTED
