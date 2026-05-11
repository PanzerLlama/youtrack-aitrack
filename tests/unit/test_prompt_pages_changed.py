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

EXPECTED = """You are a senior front-end reviewer. A YouTrack issue has just transitioned to
"Ready for testing" and a human reviewer needs a precise map of which
user-facing surfaces (pages, routes, screens) this change touches before they
start manual testing.

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

Work strictly from the file paths and contents in the diff above. You do NOT
have a route index or a build manifest. Infer affected surfaces from path
conventions alone. Be framework-agnostic:

- Next.js app router: `app/<segment>/page.tsx`, `app/<segment>/route.ts`,
  `app/<segment>/layout.tsx`.
- Next.js pages router: `pages/<segment>.tsx`, `pages/api/<segment>.ts`.
- React Router / SPA: `src/pages/<Name>.tsx`, `src/routes/<name>.tsx`,
  `src/views/<Name>.vue`.
- Server-rendered apps: FastAPI / Flask / Django route decorators, Rails
  controllers, plain `templates/*.html`.
- Anything else: use the path segment that most plausibly maps to a URL.

Classify each changed file as one of:

- **Directly affected** - the file IS a route, page, screen, controller, or
  template. The URL it serves is changed.
- **Indirectly affected** - the file is a shared component, hook, util, style,
  config, or test that is imported elsewhere. Pages that use it inherit the
  change.

If a path is ambiguous, say so and pick the most likely category. Do not
invent files that are not in the diff.

## Output format

Reply in Markdown using exactly these three sections, in this order.

## Summary

One short paragraph (2-4 sentences) stating the scope of UI impact: how many
distinct surfaces, whether the blast radius is narrow or wide, and whether
manual testing should focus on a specific flow or sweep broadly.

## Affected Routes

A bulleted list. One bullet per inferred route or page. Use this shape:

- `<inferred URL or screen name>` - contributed by:
  - `<path/from/diff>` - one-line note on what changed there.

If no file in the diff maps to a route, write "No directly affected routes."

## Indirect Impact

A bulleted list of shared modules touched and their likely downstream blast
radius. Use this shape:

- `<path/from/diff>` - <component | hook | util | style | config | test>.
  Downstream: <best guess at which routes or feature areas import this, based
  only on the path>. If unknown, say "unknown - grep needed".

If nothing in the diff is shared, write "No indirect impact."
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
