# youtrack-aitrack

> **Status: alpha.** APIs, CLI, and YAML schema may shift before the first stable release. Verified against YouTrack Cloud 2026.1.

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
