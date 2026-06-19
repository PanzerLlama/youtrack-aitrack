# Changelog

This project follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)
conventions. Versions follow [Semantic Versioning](https://semver.org).

While in 0.x, minor-version bumps may carry breaking changes. Read this
file before upgrading.

## [Unreleased]

### Added

- **Live progress for `yta run`**. On an interactive terminal the command now
  shows a live region with each action's state (pending / running / ok / fail /
  skipped) and a per-second elapsed timer, so a multi-minute CLI-agent run no
  longer looks hung. Non-TTY callers (pipes, tests, daemons) are unaffected.
- **Per-action wall-time** is measured for every action and recorded on
  `ActionResult.duration_ms`; the final `yta run` summary gains a TIME column.
- The engine emits `ProgressEvent`s through an optional `on_progress` callback
  threaded from the runtime/CLI; `engine/` stays free of any renderer import.
  (Per-action tokens/cost is tracked separately as a follow-up.)

### Removed

- **`anthropic_api` SDK backend**. The direct-API `AgentRunner`
  (`AnthropicAgentRunner` + `AnthropicLLMClient`, `adapters/llm/anthropic.py`)
  is dropped; `claude_code_cli` is now the sole execution path. The SDK path
  only inlined the git diff into the prompt, so the model had no way to
  explore the repository — the CLI agent does, via its own file/git tools.
  This completes the CLI pivot rather than reversing it (Phase 2 keeps adding
  CLI backends under the same Protocol).
- **`anthropic.default_model` config field**. Now dead — the CLI takes its
  model from the per-action `model:` field, falling back to the `claude`
  CLI's own default when omitted.
- The `anthropic` runtime dependency, now unused.

### Changed

- **BREAKING**: `defaults.default_agent` now defaults to `claude_code_cli`
  (was `anthropic_api`). Configs that relied on the old default, or that set
  `agent: anthropic_api` on any action, must switch to `claude_code_cli`.
- `anthropic.api_key` is retained but is now only consumed by
  `claude_code_cli` in `cli_agent_mode: bare`; it is unused in `oauth` mode.

## [0.2.0b0] — 2026-05-18

This release pivots the AI-agent backend from "single Anthropic SDK
client" to a vendor-agnostic `AgentRunner` Protocol. The same engine
now drives both the SDK path and a new subprocess-based path that
spawns the local Claude Code CLI per action. Workflow YAML gains a
per-action `agent:` field; instance config gains a registry-driven
`default_agent`. No changes are required to the reference workflow
YAML to keep using the SDK backend.

### Added

- **Vendor-agnostic agent backend**. `AgentRunner` Protocol in
  `domain/agent_runner.py` is now the single contract every backend
  fulfils. `runtime/runner.py:_build_agents` constructs the registry at
  `wire()` time. Two backends ship:
  - `claude_code_cli`: `ClaudeCodeCliRunner` spawns `claude -p` /
    `claude --bare -p` per action with `cwd` set to the resolved repo
    path; concurrency-gated by an injected `asyncio.Semaphore`;
    `--model <name>` forwarded when set; bare mode auth via
    `ANTHROPIC_API_KEY` pushed into the subprocess env.
  - `anthropic_api`: `AnthropicAgentRunner` wraps the existing
    `AnthropicLLMClient` and adapts to the new Protocol (cwd /
    commit_sha accepted and discarded; SDK has no working tree).
- **Per-action backend selector**. Workflow YAML `ai_report` actions
  may set `agent: <backend-name>`. Unknown names fail at `wire()` time
  with the available list. Omitted → falls back to
  `defaults.default_agent`.
- **New `defaults` fields**:
  - `default_agent` (default `anthropic_api`)
  - `agent_timeout_seconds` (default `300`)
  - `cli_agent_concurrency` (default `1`)
  - `cli_agent_mode` (`bare` | `oauth`, default `oauth`)
- **`Context.commit_sha` and `Context.repo_path`** plumbed through the
  engine so action implementations (and prompt templates) can reference
  the commit being audited and the repo root the agent should operate
  on.
- **CLI-mode reference prompt**: `prompts/security_audit_cli.md` — a
  CLI-friendly variant of `security_audit.md` that omits the embedded
  diff and instructs the agent to inspect the commit via its file-reading
  and git tools.
- **`yta --version` / `-V` flag**. Both the flag and the existing
  `yta version` subcommand now source the package version from
  `importlib.metadata` so they stay in lockstep with `pyproject.toml`.

### Changed

- **`AiReportAction` switched from `LLMClient` to `AgentRunner`**.
  The same action class now covers both backends; the engine and
  `ActionFactory` are unaware of which one is in use.
- **`ActionFactory` constructor** now takes
  `agents: dict[str, AgentRunner]` + `default_agent: str` instead of a
  single `LLMClient`. Per-action backend selection happens here.
- **`StubLLMClient` → `StubAgentRunner`**. `--stub-llm` continues to
  work as a CLI flag; the marker string in stub output is now
  `[STUB AGENT]`.
- **`AgentRunnerError` stderr now surfaces in `ActionResult.error`**.
  Failures from the CLI backend used to report only "Claude Code CLI
  exited with code N" with no diagnostic; the runner's captured
  stderr (and stdout-on-failure, capped at 8KB) is now appended below
  a `stderr:` delimiter. The `yta run` table-row formatter shows the
  first line of the error in the `NOTE` column with a "see run report
  for full error" hint for multi-line errors.

### Documentation

- README reframed around the two-backend architecture; the CLI backend
  is positioned as the recommended production path.
- `docs/installation.md` covers prerequisites for both backends and
  walks through switching the default backend to `claude_code_cli` in
  bare mode.
- `docs/configuration.md` gains an "Agent backends" section and tables
  for every new `defaults.*` field.
- `docs/workflows.md` documents the `agent:` field, the new ctx
  variables (`commit_sha`, `repo_path`), and the difference between
  SDK-style and CLI-style prompts.
- `docs/architecture.md` documents the `AgentRunner` Protocol, the
  registry pattern in `_build_agents`, and the
  `AnthropicAgentRunner` / `ClaudeCodeCliRunner` adapters.

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

[Unreleased]: https://github.com/PanzerLlama/youtrack-aitrack/compare/v0.2.0b0...HEAD
[0.2.0b0]: https://github.com/PanzerLlama/youtrack-aitrack/compare/v0.1.0b0...v0.2.0b0
[0.1.0b0]: https://github.com/PanzerLlama/youtrack-aitrack/releases/tag/v0.1.0b0
