# Changelog

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
conventions. Versions follow [Semantic Versioning](https://semver.org).

While in 0.x, minor-version bumps may carry breaking changes. Read this
file before upgrading.

## [Unreleased]

## [0.1.0b0] — 2026-05-16

First beta release. The core daemon path is feature-complete and has been
verified end-to-end against YouTrack Cloud 2026.1.

### Added

- Workflow engine with trigger matching, parallel action execution,
  `depends_on` ordering, `on_success` / `on_failure` hooks, and
  graceful-degradation via `unavailable_inputs`.
- Two trigger types: `status_change`, `manual`.
- Three action types: `ai_report`, `set_field`, `yt_comment`.
- `OutputSpec` for declarative result persistence (custom field or
  comment); engine writes via a `StandardOutputSink` that respects the
  same dry-run no-op adapters used by `--dry-run`.
- Adapters: `YouTrackClient` (REST), `GitDiffAdapter` (CLI subprocess),
  `AnthropicLLMClient`, `JinjaPromptRenderer`, `JsonRunStore` (atomic
  on-disk JSON with idempotency).
- CLI commands: `init`, `workflows list`/`validate`, `run <issue-id>`,
  `poll [--daemon]`.
- Safety modifiers: `--dry-run` (suppress YouTrack writes), `--stub-llm`
  (suppress Anthropic calls), `--force` (bypass idempotency),
  `--workflow=NAME` (scope to one), `--repo-dir=PATH`.
- Tag-based daemon scoping via `defaults.include_tags`.
- Reference workflow `ready-for-testing-audit.yaml` shipping three
  parallel `ai_report` actions (security audit, pages changed, QA plan)
  with an `on_success` hook writing an audit-status field.
- Full documentation tree under `docs/`:
  installation, configuration, operations, workflows, architecture.
- `SECURITY.md` with private vulnerability disclosure flow.

### Security

- LLM prompts now use a system/user message split; user message carries
  attacker-influenceable diff content, system message frames it as data.
- `run_id` validated against a safe character set before any path
  interpolation in `JsonRunStore.load_run`.
- `IssueEvent.raw` stripped from the Jinja template context to prevent
  future prompt templates from accidentally leaking YouTrack-supplied
  attacker content to the LLM.
- Git subprocess invocations pass `--end-of-options` so user-controlled
  positional args can never be interpreted as flags. `rev-parse` also
  uses `--verify`.
- `issue_id` CLI argument validated against `^[A-Za-z][A-Za-z0-9_]*-\d+$`.
- YouTrack error response bodies truncated to 200 chars and stripped of
  non-printable characters before being embedded in `YouTrackError`
  messages (which propagate to `ActionResult.error` and on-disk JSON).

### Known limitations

- One daemon per host per YouTrack instance. The idempotency store has
  no inter-process locking; concurrent dispatches may produce duplicate
  runs.
- AI report output is advisory. Diffs are attacker-influenceable;
  prompt-injection content in commits can manipulate generated reports
  despite the system/user message split.
- Custom field type support: `Simple` (string) and `Text` only.
- v1 of `--stub-llm` and `--dry-run` are opt-in. A fresh `yta run` with
  no flags hits Anthropic and writes to YouTrack.

[Unreleased]: https://github.com/PanzerLlama/youtrack-aitrack/compare/v0.1.0b0...HEAD
[0.1.0b0]: https://github.com/PanzerLlama/youtrack-aitrack/releases/tag/v0.1.0b0
