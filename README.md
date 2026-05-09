# youtrack-aitrack

> **Status: alpha.** APIs, CLI, and YAML schema may shift before the first stable release.

A YAML-driven workflow engine that runs AI-agent actions in response to YouTrack
issue events. Each workflow declares one trigger (e.g. a status change) and a
sequence of actions; an engine matches incoming events against triggers and
dispatches the matching actions, running independent steps concurrently and
respecting `depends_on` for ordered work.

The first reference workflow ships with the project: when an issue moves to
`Ready for testing`, three parallel AI reports run — a security/PCI audit, a
"Pages Changed" UI summary, and a manual QA plan — and the results are written
back into the issue's custom fields. Each action is a plugin: registered via
decorator, invoked by name from YAML, and exposed to the engine through small
`Protocol` interfaces so its dependencies (LLM client, YouTrack REST client,
git tooling) can be swapped or stubbed without touching the workflow.

One running daemon binds to one YouTrack project. Multi-project setups use
multiple instances with separate configs; this keeps configuration small and
token usage bounded per workflow.

## Quickstart

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
# Alpha install directly from git
uv tool install --from git+https://github.com/lechuszczynski/youtrack-aitrack youtrack-aitrack

# Verify the install
youtrack-aitrack --help
youtrack-aitrack version
```

The shorter `yta` alias is registered for the same entry point.

The full command surface (`init`, `workflows list/validate`, `run <issue-id>`,
`poll [--daemon]`) is described in [CLAUDE.md](./CLAUDE.md#cli) and is being
landed alongside the engine and adapter work — track open commands with
`bd ready`.

## Architecture

A short tour of the layout and the rules that keep it coherent across
multiple AI-agent contributions lives in [CLAUDE.md](./CLAUDE.md).

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for the issue workflow, branching
conventions, and quality gates that every change is expected to pass.

## License

MIT — see [LICENSE](./LICENSE).
