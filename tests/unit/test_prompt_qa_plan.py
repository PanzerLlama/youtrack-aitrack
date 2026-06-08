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


EXPECTED = """You are a senior QA assistant. A YouTrack issue has just transitioned to
"Ready for testing". The reader of your report is a QA tester — not a developer.
They will execute the scenarios manually in a browser, or encode them as
Playwright scripts. They do not read source code, do not see file paths, and
do not have access to the repository. An upstream "pages_changed" report has
already summarised which surfaces were touched — treat it as the source of
truth for scope.

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

## How to reason

Read the pages_changed report above and the issue metadata. Design a set of
browser-executable scenarios that cover what the report names. Do NOT invent
surface area the report does not mention.

Each scenario must be self-contained: pre-conditions, ordered steps, and
expected results. Both a human tester and a QA encoding it into Playwright
must be able to execute it from the report alone.

Describe UI elements physically and by their visible label or role (e.g.
"the Apply button next to the coupon input", "the first dropdown on the
page"). Never reference file paths, selectors, component names, or source
code. Keep descriptions adequately precise — the QA tester can derive their
own automation selectors and will ask if anything is ambiguous; do not
over-specify.

Group scenarios into two priority bands:

- **P1** — happy paths through every page or feature listed in the report,
  plus the single most likely critical regression for each.
- **P2** — edge cases, form / input validation, empty and error states,
  boundary values, permission variants.

Hard limits: at most 5 P1 scenarios and at most 5 P2 scenarios. Pick the most
valuable ones if the surface area exceeds the cap. Do not introduce
cross-browser or responsive checks — that is the tester's standing
responsibility, not output of this report.

## Output format

Reply in Markdown using exactly these three sections, in this order. Label each
section with a **bold** line exactly as shown — do NOT use Markdown `#`
headings. The report is written into a YouTrack custom field whose name label is
small; `#` headings render larger than that label and invert the visual
hierarchy.

**Summary**

2-3 sentences. What is in scope, where the tester should focus first.

**Scenarios**

A flat list of scenario blocks. Each scenario uses this shape:

**[P1] <scenario name>**
**Pre-conditions:** <single sentence: who is logged in, what state>.

**Steps:**
1. <action>
2. <action>
3. <action>

**Expected:**
- <observable outcome>
- <observable outcome>

Tag each scenario label with `[P1]` or `[P2]`. List P1 scenarios first, then
P2. If the report yields nothing testable in a band, omit that band entirely.

**Regression Watchlist**

A short bulleted list of areas not directly changed but plausibly impacted by
the change (shared layouts, navigation, auth, billing, etc.). For each entry
give the area and the one symptom a tester should glance at while running the
scenarios above.

If no such areas come to mind, write "No regression watchlist."
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
