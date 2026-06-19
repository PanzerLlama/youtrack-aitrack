# Project Instructions for AI Agents

This file provides instructions and context for AI coding agents working on this project.

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:ca08a54f -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   bd dolt push
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
<!-- END BEADS INTEGRATION -->


## Mission

`youtrack-aitrack` is a vendor-agnostic AI agent orchestrator for YouTrack issue events. A YAML workflow declares one trigger and a sequence of actions; an engine matches events against triggers and dispatches actions in parallel where possible. Each `ai_report` action routes through an `AgentRunner` backend — the Protocol covers shelling out to local CLI agents (Claude Code today; future Codex / Gemini / Aider), which inspect the working tree directly via their own file/git tools rather than relying on an embedded diff.

**First reference workflow** — when an issue moves to `Ready for testing`, three parallel AI reports run (Security/PCI audit, Pages Changed for UI review, QA Plan for manual browser testing) and write back to the issue's custom fields.

**Single-project per instance.** One running daemon binds to one YouTrack project. Multi-project = multiple instances with separate configs. Reduces config and token sprawl.

## Architecture — hexagonal (ports & adapters)

```
src/youtrack_aitrack/
├── domain/         # Pure. Pydantic models: Workflow, Trigger, Action, Context, RunState, AgentRunner Protocol
├── engine/         # Trigger matching, action scheduling, run lifecycle, idempotency
├── registry/       # Decorator-based plugin registries (trigger types, action types)
├── adapters/
│   ├── youtrack/   # YT REST client (httpx async)
│   ├── git/        # Branch resolve, diff extraction (subprocess git)
│   ├── llm/        # Jinja prompt renderer
│   ├── cli/        # ClaudeCodeCliRunner (spawns `claude -p`); future Codex/Gemini live here
│   └── storage/    # Run logs, cache, state persistence (JSON files)
├── config/         # YAML loader, schema validation, env loading
├── runtime/        # Composition root: wire(), ActionFactory, agent registry, Runner, Poller
└── cli/            # Typer commands
```

**Hard rules:**

- Core (`domain/`, `engine/`, `registry/`) is **pure** — no network, no disk, no env reads. Imports only stdlib + pydantic.
- Adapters wrap I/O. One module per external system. Engine talks to them via `Protocol` interfaces, never concrete classes.
- DI by function args. **No global state. No singletons.**
- `Protocol` over ABC.
- Single direction of dependency: `cli` → `engine` → `domain` ← `adapters` (adapters implement Protocols owned by domain).

DDD-light: keep ubiquitous language consistent (`Workflow`, `Trigger`, `Action`, `Run`, `Event`). No aggregate / repository / bounded-context ceremony.

## Plugin model

Triggers and actions are plugins registered via decorator at module import:

```python
@register_trigger("status_change")
class StatusChangeTrigger:
    def matches(self, event: IssueEvent) -> bool: ...

@register_action("ai_report")
class AiReportAction:
    async def execute(self, ctx: Context) -> ActionResult: ...
```

Adding a new trigger / action type = one file in `domain/triggers/` or `domain/actions/`, imported explicitly from a registry init module. **No filesystem auto-scan.**

## Workflow YAML schema

```yaml
name: ready-for-testing-audit
trigger:
  type: status_change
  to_state: "Ready for testing"
  from_state: "*"
actions:
  - id: security_audit
    type: ai_report
    inputs: [git_diff, task_meta]
    agent: claude_code_cli                # optional; falls back to defaults.default_agent
    output: { kind: custom_field, name: "Security Audit" }
    prompt: security_audit_cli.md         # CLI-style prompt for the CLI backend
    model: claude-sonnet-4-6
  - id: pages_changed
    type: ai_report
    inputs: [git_diff, route_index]
    # no `agent:` → uses defaults.default_agent (claude_code_cli by default)
    output: { kind: custom_field, name: "Pages Changed" }
    prompt: pages_changed.md
    model: claude-sonnet-4-6
  - id: qa_plan
    type: ai_report
    inputs: [task_meta, dependency_outputs]
    depends_on: [pages_changed]
    output: { kind: custom_field, name: "QA Plan" }
    prompt: qa_plan.md
    model: claude-sonnet-4-6
on_failure:
  - set_field: { Audit Status: failed }
on_success:
  - set_field: { Audit Status: done }
```

Schema is generated from pydantic models — single source of truth. Validated at startup; failure aborts launch with a precise error.

Backend selection: each `ai_report` may set `agent: <backend-name>`. The shipping registry covers `claude_code_cli` (local subprocess) in two auth modes — `oauth` (subscription login) and `bare` (`ANTHROPIC_API_KEY`); Phase 2 adds further CLI backends (Codex / Gemini) under the same Protocol. Unknown names fail at `wire()` time with the available list. Workflow-wide default lives in `defaults.default_agent`.

## Code quality — strict, enforced

| Tool | Purpose |
|---|---|
| `ruff check` | Lint |
| `ruff format` | Auto-format |
| `mypy --strict` | Static types |
| `pytest` | Tests |
| `pre-commit` | Run all of the above on commit |

**Module / function rules:**

- Module size cap: ~200 LOC. Bigger = signal to split.
- Function size cap: ~30 LOC. Bigger = split.
- Pydantic models at every module boundary (input + output).
- Pure functions in core. Side effects only in adapters.
- No `from x import *`. Explicit imports only.
- Tests: unit (no I/O) for core; adapter tests with `respx` / fixtures; one snapshot test per LLM prompt template (rendered output, no LLM call).

## Anti-drift rules for AI agents

These exist to keep the codebase coherent across multiple AI-agent sessions.

1. **Read this CLAUDE.md before editing.** Architecture and rules are here. Don't invent.
2. **Don't edit core (`domain/`, `engine/`) and adapters in the same change.** Separate beads issues, separate commits.
3. **Don't add a new dependency without a beads issue justifying it.**
4. **Don't add abstractions for hypothetical future use.** Three similar lines beat a premature interface.
5. **Don't add fallbacks / error handling for cases the type system rules out.** Trust mypy inside core.
6. **No `# TODO` / `# FIXME` left in committed code.** File a beads issue instead.
7. **Comments only when WHY is non-obvious.** Names describe WHAT.
8. **No new top-level directories without architecture discussion.**
9. **One change = one beads issue = one commit.** Atomic, reviewable.
10. **Match existing naming.** Singular module names by default (`trigger.py` not `triggers.py` unless plural intent).
11. **Validate all external data with pydantic at the boundary.** Inside core, types are trusted.
12. **No new top-level concepts in the domain language without discussion.** `Workflow`, `Trigger`, `Action`, `Run`, `Event` are the vocabulary.

## Build & test

```bash
uv sync                                  # install all deps incl. dev
uv run youtrack-aitrack --help           # run CLI
uv run pytest                            # tests
uv run ruff check && uv run ruff format --check
uv run mypy src
```

## CLI

```bash
youtrack-aitrack init                            # scaffold ~/.youtrack-aitrack/
youtrack-aitrack workflows list                  # list configured workflows
youtrack-aitrack workflows validate              # check YAML schema
youtrack-aitrack run <issue-id>                  # manually fire matching workflow now
youtrack-aitrack run <issue-id> --workflow=<name> --dry-run
youtrack-aitrack poll                            # one polling pass
youtrack-aitrack poll --daemon                   # continuous polling loop
```

Short alias `yta` available for all subcommands.

## Distribution

- During alpha: `uv tool install --from git+<repo>`
- After PyPI release (Phase 1+): `uv tool install youtrack-aitrack`
- Python 3.12+ required.

## License

MIT.

## Status (today: 2026-05-18)

Beta. Core daemon path verified end-to-end against YouTrack Cloud. Phase 1 of the CLI-agent pivot is shipped (`AgentRunner` Protocol, `ClaudeCodeCliRunner`, per-action `agent:` field, bare/oauth modes, `--version` flag, stderr passthrough). Phase 2 (Codex/Gemini runners, CLI variants of pages_changed + qa_plan prompts, init flow refresh) is open as a separate epic. See `bd ready`.
