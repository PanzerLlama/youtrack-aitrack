# Contributing to youtrack-aitrack

Thanks for the interest in helping. This project is alpha and moves in small,
atomic steps — please read the rules below before opening a PR.

## Architecture and anti-drift rules

The architecture (hexagonal: `domain` / `engine` / `registry` / `adapters`)
and the per-module / per-function size and purity rules are documented in
[CLAUDE.md](./CLAUDE.md). The "Anti-drift rules for AI agents" section there
applies to human contributors too — they are the rules that keep multi-author
sessions coherent.

In short:

- **One change = one issue = one commit.**
- Don't edit core (`domain/`, `engine/`) and adapters in the same change.
- Don't introduce new abstractions for hypothetical future use.
- Don't add a new dependency without an issue justifying it.
- No `# TODO` / `# FIXME` left in committed code — file an issue.
- Match existing naming. Singular module names by default.

## Issue tracking — beads

Issue tracking lives in this repo via [beads (`bd`)](https://github.com/sfultong/beads),
not GitHub Issues. Run `bd prime` after `bd init` for the full command
reference. Day-to-day:

```bash
bd ready                  # List unblocked work
bd show <id>              # View the issue
bd update <id> --claim    # Claim it
bd update <id> --status=in_progress
bd close <id>             # When the work is committed
```

Create the issue **before** writing the code so the description stays honest
about scope and motivation.

## Pull requests

1. Branch from `main` (or `master` while the project is single-branch).
2. Reference the beads issue id in the commit message and PR description.
3. Keep the diff focused on one issue. Split unrelated work into separate
   issues and PRs.
4. Run the quality gates locally before pushing — see below.

## Quality gates

```bash
uv sync                                     # install deps incl. dev
uv run pytest                               # tests
uv run ruff check                           # lint
uv run ruff format --check                  # format
uv run mypy src                             # static types (strict)
uv run pre-commit run --all-files           # everything pre-commit enforces
```

All four pass on every commit. CI (when wired) runs the same set.

## Adding a trigger or action type

A new trigger lives in `src/youtrack_aitrack/domain/triggers/` as a single
file, registered with `@register_trigger("<name>")` and re-exported from the
sibling `__init__.py`. Actions follow the same pattern under
`domain/actions/`. Real I/O lives in adapters under
`src/youtrack_aitrack/adapters/`; the action class injects adapter
dependencies via its constructor and calls them via `Protocol` interfaces
declared next to the action. See the existing `ai_report`, `yt_comment`, and
`set_field` action stubs for the pattern.

## Reporting issues

External bug reports and feature requests are welcome on the project's GitHub
issue tracker once the repository is published. Reproduction steps and the
output of `youtrack-aitrack workflows validate` are usually enough to
diagnose configuration problems.
