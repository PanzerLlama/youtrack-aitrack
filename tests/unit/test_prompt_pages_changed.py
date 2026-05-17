"""Snapshot test for the pages_changed prompt template."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from youtrack_aitrack.adapters.llm.jinja import JinjaPromptRenderer
from youtrack_aitrack.domain.context import Context
from youtrack_aitrack.domain.event import IssueEvent

_DIFF = """diff --git a/src/pages/Checkout.tsx b/src/pages/Checkout.tsx
@@ -3,7 +3,7 @@ import { formatPrice } from "../lib/currency";
 export function Checkout() {
-  return <div>{formatPrice(total, "USD")}</div>;
+  return <div>{formatPrice(total)}</div>;
 }
diff --git a/src/lib/currency.ts b/src/lib/currency.ts
@@ -1,3 +1,5 @@
-export function formatPrice(value: number, code: string): string {
+const DEFAULT_CODE = "USD";
+export function formatPrice(value: number, code: string = DEFAULT_CODE): string {
   return new Intl.NumberFormat("en", { style: "currency", currency: code }).format(value);
 }
"""

EXPECTED = """You are a senior UI reviewer's assistant. A YouTrack issue has just transitioned
to "Ready for testing". The reader of your report is a UI reviewer — not a
developer — who needs to know what to open in a browser, what wording changed,
and what visual details to inspect. They do not read code.

## Issue metadata

- Issue: SHOP-17 (SHOP)
- Event: status_change
- Transition: In Progress -> Ready for testing
- Actor: bob
- Timestamp: 2026-05-11 12:00:00+00:00
- Branch: SHOP-17-default-currency

## Diff under review

```diff
diff --git a/src/pages/Checkout.tsx b/src/pages/Checkout.tsx
@@ -3,7 +3,7 @@ import { formatPrice } from "../lib/currency";
 export function Checkout() {
-  return <div>{formatPrice(total, "USD")}</div>;
+  return <div>{formatPrice(total)}</div>;
 }
diff --git a/src/lib/currency.ts b/src/lib/currency.ts
@@ -1,3 +1,5 @@
-export function formatPrice(value: number, code: string): string {
+const DEFAULT_CODE = "USD";
+export function formatPrice(value: number, code: string = DEFAULT_CODE): string {
   return new Intl.NumberFormat("en", { style: "currency", currency: code }).format(value);
 }

```

## How to reason

The diff above is your only source of truth. You do NOT have a route index or a
build manifest. Infer affected surfaces from path conventions alone. Be
framework-agnostic:

- Next.js app router: `app/<segment>/page.tsx`, `app/<segment>/route.ts`,
  `app/<segment>/layout.tsx`.
- Next.js pages router: `pages/<segment>.tsx`, `pages/api/<segment>.ts`.
- React Router / SPA: `src/pages/<Name>.tsx`, `src/routes/<name>.tsx`,
  `src/views/<Name>.vue`.
- Server-rendered apps: FastAPI / Flask / Django route decorators, Rails
  controllers, plain `templates/*.html`.
- Anything else: use the path segment that most plausibly maps to a URL.

Translate everything into user-facing language for the report. The reviewer
does not read code, does not know what a "hook" or "component" is, and should
never see a file path or framework name in the output. Refer to screens by
plain English names ("Customer list", "Checkout page") and to locations by
where the user sees them ("toolbar button on the customer list", "first field
label on the edit form").

Decide whether the diff contains any user-visible change at all. The following
do NOT count as user-visible and should be ignored: schema migrations, internal
refactors with identical rendered output, build / CI / dependency changes,
unit-test-only changes, lint config, dead-code removal.

## Output format

Reply in Markdown.

If, after applying the rule above, the diff contains no user-visible changes,
output exactly one line and stop:

```
No user-visible changes — nothing to review.
```

Otherwise reply using exactly these four sections, in this order:

## Summary

2-3 sentences in product language. State what an end user could notice without
naming files, frameworks, or components. Example: "A new Export button is added
to the customer list. One form field label changed on the customer edit screen."

## Screens to check

A bulleted list. One bullet per screen the reviewer should actually open. Use
one of the two shapes below.

No Base URL is configured. Emit each screen with an inline annotation noting
that the path could not be resolved to a clickable link. Use this shape:

- <plain-English screen name> _(path unresolved — no base URL configured)_ — <one-sentence focus>

If no file in the diff maps to a screen, write "No screens to open."

## Text / copy changes

A table of every user-visible string added, changed, or removed. Columns:

| Where | Before | After |
|---|---|---|

"Where" must be a human-readable location ("Customer list — toolbar button",
"Edit form — first field label"). Never a file path or component name. Use
`(none)` in the Before or After cell when a string is purely added or removed.

If translation / i18n keys are changed without changing the rendered string,
list them in a sub-bulleted "i18n keys changed (no visible text change)" block
after the table — those need a translation-file review but not visual review.

If there are no copy changes, write "No copy changes."

## What to look for visually

A bulleted list of concrete visual checks. Phrase as observations to make, not
test instructions. Example shape:

- New "Export" button on the customer list toolbar — alignment with adjacent
  buttons, spacing on the right edge.
- Changed icon in the page header — visual rhythm with the rest of the section.
- Modal "Confirm delete" — width relative to other modals in the app.

If nothing visually changed (pure copy or data change), write "No visual
changes beyond text."
"""


def _ctx() -> Context:
    event = IssueEvent(
        issue_id="SHOP-17",
        project="SHOP",
        event_kind="status_change",
        from_state="In Progress",
        to_state="Ready for testing",
        actor="bob",
        timestamp=datetime(2026, 5, 11, 12, 0, tzinfo=UTC),
    )
    return Context(issue=event, branch="SHOP-17-default-currency", diff=_DIFF)


def test_pages_changed_prompt_renders_verbatim() -> None:
    renderer = JinjaPromptRenderer(Path("prompts"))
    rendered = renderer.render("pages_changed.md", _ctx())
    assert rendered == EXPECTED


def test_pages_changed_includes_base_url_when_set() -> None:
    event = IssueEvent(
        issue_id="SHOP-17",
        project="SHOP",
        event_kind="status_change",
        from_state="In Progress",
        to_state="Ready for testing",
        actor="bob",
        timestamp=datetime(2026, 5, 11, 12, 0, tzinfo=UTC),
    )
    ctx = Context(
        issue=event,
        branch="SHOP-17-default-currency",
        diff=_DIFF,
        base_url="https://staging.example.com",
    )
    rendered = JinjaPromptRenderer(Path("prompts")).render("pages_changed.md", ctx)

    assert "- Base URL: https://staging.example.com" in rendered
    assert "A Base URL is provided in the metadata above." in rendered
    assert "https://staging.example.com/path" in rendered
    assert "path unresolved" not in rendered


def test_pages_changed_omits_base_url_block_when_unset() -> None:
    rendered = JinjaPromptRenderer(Path("prompts")).render("pages_changed.md", _ctx())
    assert "- Base URL:" not in rendered
    assert "No Base URL is configured." in rendered
    assert "path unresolved — no base URL configured" in rendered
