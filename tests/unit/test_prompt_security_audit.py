"""Snapshot test for the security_audit prompt template."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from youtrack_aitrack.adapters.llm.jinja import JinjaPromptRenderer
from youtrack_aitrack.domain.context import Context
from youtrack_aitrack.domain.event import IssueEvent

_DIFF = """diff --git a/app/login.py b/app/login.py
@@ -10,3 +10,4 @@ def login(user, pw):
-    if check(user, pw):
+    if check(user, pw) or user == "admin":
         return token(user)
"""

EXPECTED = """You are a senior application-security reviewer. A YouTrack issue has just
transitioned to "Ready for testing" and the developer needs a focused, no-noise
security audit of the change before it ships.

## Issue metadata

- Issue: SEC-42 (SEC)
- Event: status_change
- Transition: In Progress -> Ready for testing
- Actor: alice
- Timestamp: 2026-05-11 12:00:00+00:00
- Branch: SEC-42-fix-login

## Diff under review

```diff
diff --git a/app/login.py b/app/login.py
@@ -10,3 +10,4 @@ def login(user, pw):
-    if check(user, pw):
+    if check(user, pw) or user == "admin":
         return token(user)

```

## What to look for

Audit the diff above for concrete, evidence-based security risks. Focus on:

- OWASP Top 10 categories (injection, broken access control, SSRF, XSS, CSRF,
  insecure deserialization, IDOR, security misconfiguration, etc.).
- PCI-DSS-relevant patterns: primary account numbers (PANs), cardholder data
  (CHD), key material, or any logging / serialization of those values.
- Secrets or credentials accidentally committed: API keys, tokens, passwords,
  private keys, connection strings.
- Dangerous primitives: string-built SQL, shell or subprocess invocations with
  untrusted input, `eval`, `exec`, `pickle.loads`, dynamic `import`, unsafe YAML
  loaders, `os.system`, deserialization of attacker-controlled data.
- Authentication and authorization bypass: missing checks, weakened roles,
  hardcoded admin flags, removed permission guards.

Ignore stylistic issues. Only report things that are or could become exploitable.

## Output format

Reply in Markdown using exactly these three sections, in this order. Label each
section with a **bold** line exactly as shown — do NOT use Markdown `#`
headings. The report is written into a YouTrack custom field whose name label is
small; `#` headings render larger than that label and invert the visual
hierarchy.

**Summary**

One short paragraph (2-4 sentences) stating the overall risk posture of the
diff and whether it appears safe to ship.

**Findings**

A list of findings. If there are none, write "No security-relevant findings."
Each finding MUST follow this shape:

- **[severity: critical|high|medium|low] short title** - file:line (or path)
  - Evidence: quote or paraphrase the offending code.
  - Impact: what an attacker could do.
  - Fix: the smallest concrete change that addresses it.

Severities:

- critical: remote code execution, auth bypass, secret leak, PAN/CHD exposure.
- high: exploitable injection, broken access control on sensitive resources.
- medium: input-validation gaps, weak crypto, risky defaults.
- low: defense-in-depth, hardening suggestions.

**Recommendations**

A short bulleted list of follow-up actions (rotate a key, add a test, gate a
flag). Skip this section entirely if there are no findings.
"""


def _ctx() -> Context:
    event = IssueEvent(
        issue_id="SEC-42",
        project="SEC",
        event_kind="status_change",
        from_state="In Progress",
        to_state="Ready for testing",
        actor="alice",
        timestamp=datetime(2026, 5, 11, 12, 0, tzinfo=UTC),
    )
    return Context(issue=event, branch="SEC-42-fix-login", diff=_DIFF)


def test_security_audit_prompt_renders_verbatim() -> None:
    renderer = JinjaPromptRenderer(Path("prompts"))
    rendered = renderer.render("security_audit.md", _ctx())
    assert rendered == EXPECTED
