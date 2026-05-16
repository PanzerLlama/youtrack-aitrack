# youtrack-aitrack

> **Status: beta.** Core daemon path is feature-complete and verified end-to-end against YouTrack Cloud 2026.1. APIs, CLI, and YAML schema may still shift before the first stable release; breaking changes will be called out in the changelog.

A YAML-driven workflow engine that runs AI-agent actions in response to
YouTrack issue events. Each workflow declares one trigger (e.g. a status
change) and a sequence of actions; an engine matches incoming events against
triggers and dispatches matching actions, running independent steps
concurrently and respecting `depends_on` for ordered work.

The reference workflow ships with the project: when an issue moves to
`Ready for testing`, three parallel AI reports run — a security/PCI audit, a
"Pages Changed" UI summary, and a manual QA plan — and the results are
written back into the issue's custom fields. Each action is a plugin:
registered via decorator, invoked by name from YAML, and exposed to the
engine through small `Protocol` interfaces so its dependencies (LLM client,
YouTrack REST client, git tooling) can be swapped or stubbed without
touching the workflow.

One running daemon binds to one YouTrack project. Multi-project setups use
multiple instances with separate configs.

## How it works — one dispatch, end to end

Cause: a developer moves an issue to `Ready for testing`. This bit of YAML in
your config dir is what teaches the daemon to react:

```yaml
# workflows/ready-for-testing-audit.yaml (excerpt)
name: ready-for-testing-audit
trigger:
  type: status_change
  to_state: "Ready for testing"
actions:
  - id: security_audit
    type: ai_report
    output: { kind: custom_field, name: "Security Audit" }
    prompt: security_audit.md
    model: claude-sonnet-4-6
  - id: pages_changed
    type: ai_report
    output: { kind: custom_field, name: "Pages Changed" }
    prompt: pages_changed.md
    model: claude-sonnet-4-6
  - id: qa_plan
    type: ai_report
    depends_on: [pages_changed]
    output: { kind: custom_field, name: "QA Plan" }
    prompt: qa_plan.md
    model: claude-sonnet-4-6
on_success:
  - id: mark_done
    type: set_field
    fields: { "Audit Status": "done" }
```

Effect: the daemon catches the state change on its next poll and runs the
graph. Independent reports run in parallel; `qa_plan` waits for
`pages_changed` so it can use its findings. Results land in the issue's
custom fields. The on-success hook marks the audit done.

```mermaid
sequenceDiagram
    autonumber
    actor Dev as Developer
    participant YT as YouTrack
    participant D as yta poll --daemon
    participant G as local git
    participant E as engine
    participant AI as Claude

    Dev->>YT: move DEMO-42 → "Ready for testing"
    D->>YT: poll /api/activitiesPage
    YT-->>D: state-change event
    D->>YT: get_issue_tags (tag filter passes)
    D->>G: resolve branch & diff
    G-->>D: DEMO-42-fix + diff + commit_sha
    D->>E: dispatch matching workflow

    par parallel
        E->>AI: security_audit prompt + diff
        E->>AI: pages_changed prompt + diff
    end
    AI-->>E: Security Audit report
    AI-->>E: Pages Changed report
    E->>AI: qa_plan prompt (uses pages_changed output)
    AI-->>E: QA Plan report

    E->>YT: write Security Audit, Pages Changed, QA Plan custom fields
    E->>YT: set Audit Status = "done" (on_success hook)
    Note over D: cursor advances; idempotency key recorded
```

Every step is also a place where you can intervene: `--dry-run` swaps the
YouTrack writer for a no-op so nothing lands in YT; `--stub-llm` swaps the
Anthropic call for a placeholder so nothing costs tokens; `include_tags`
in config filters which issues the daemon reacts to. See
[docs/operations.md](./docs/operations.md) for the full set of safety knobs
and the recommended first-run staircase.

## Quickstart

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
# Install
uv tool install --from git+https://github.com/PanzerLlama/youtrack-aitrack youtrack-aitrack

# Scaffold config
yta init
cp ~/.youtrack-aitrack/.env.example ~/.youtrack-aitrack/.env
# ...edit .env with YouTrack URL, token, project, and Anthropic API key...

# Copy the reference workflow + prompts (one-time)
git clone https://github.com/PanzerLlama/youtrack-aitrack /tmp/yta-source
cp /tmp/yta-source/workflows/ready-for-testing-audit.yaml ~/.youtrack-aitrack/workflows/
cp /tmp/yta-source/prompts/*.md ~/.youtrack-aitrack/prompts/

# Sanity check
yta workflows validate

# First dispatch — no API spend, no YouTrack writes
cd /path/to/your/repo                            # daemon needs the git repo
yta run <issue-id> --dry-run --stub-llm
```

The shorter `yta` alias is registered alongside `youtrack-aitrack` and is
used throughout the docs.

For the full setup walk-through including custom-field creation and the
recommended testing staircase, see [docs/installation.md](./docs/installation.md)
and [docs/operations.md](./docs/operations.md).

## Documentation

| Doc | Audience | What it covers |
|---|---|---|
| [docs/installation.md](./docs/installation.md) | First-time users | Install, configure, scaffold, first run. |
| [docs/configuration.md](./docs/configuration.md) | Operators | Every `config.yaml` option and its default. |
| [docs/operations.md](./docs/operations.md) | Operators | `yta run` vs `yta poll` vs daemon, `--dry-run`/`--stub-llm`/`--force`/`--workflow`, tag filter, troubleshooting. |
| [docs/workflows.md](./docs/workflows.md) | Workflow authors | YAML schema, trigger and action types, prompt template variables. |
| [docs/architecture.md](./docs/architecture.md) | Contributors | Hexagonal layout, plugin system, how to add new triggers/actions/adapters. |

## Command surface

```bash
yta init                                         # scaffold ~/.youtrack-aitrack/
yta workflows list                                # show every workflow YAML
yta workflows validate                            # check every YAML parses
yta run <issue-id>                                # manual dispatch
yta run <issue-id> --dry-run --stub-llm --force  # safe rerun, no spend
yta poll                                          # one-shot pull from the activity feed
yta poll --daemon                                 # continuous loop
```

Detail in [docs/operations.md](./docs/operations.md).

## Architecture summary

Hexagonal (ports & adapters):

```
cli/  →  runtime/  →  engine/  →  domain/  ←  adapters/
```

Inner rings never import from outer rings. `domain/` is pure pydantic +
Protocols (no httpx, no anthropic, no subprocess). Adapters wrap external
systems and implement the Protocols. `runtime/` is the composition root.
`cli/` is the entry point.

See [docs/architecture.md](./docs/architecture.md) for the full tour.

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for the issue workflow, branching
conventions, and quality gates (`ruff`, `mypy --strict`, `pytest`,
`pre-commit`) that every change is expected to pass.

[CLAUDE.md](./CLAUDE.md) and [AGENTS.md](./AGENTS.md) capture the project
conventions that AI coding agents should follow. Humans are welcome to read
them too — they document the anti-drift rules that keep the codebase
coherent across many small contributions.

## License

MIT — see [LICENSE](./LICENSE).
