# Contributing to youtrack-aitrack

Thanks for the interest in helping. This project is in beta and moves in
small, atomic steps — please read the rules below before opening a PR.

## Architecture and anti-drift rules

The architecture (hexagonal: `domain` / `engine` / `registry` / `adapters` /
`runtime`) and the per-module / per-function size and purity rules are
documented in [CLAUDE.md](./CLAUDE.md). The "Anti-drift rules for AI agents"
section there applies to human contributors too — they are the rules that
keep multi-author sessions coherent.

In short:

- **One change = one issue = one commit.**
- Don't edit core (`domain/`, `engine/`) and adapters in the same change.
- Don't introduce new abstractions for hypothetical future use.
- Don't add a new dependency without an issue justifying it.
- No `# TODO` / `# FIXME` left in committed code — file an issue.
- Match existing naming. Singular module names by default.

## Issue tracking

External bug reports and feature requests go through GitHub Issues using
the [bug](./.github/ISSUE_TEMPLATE/bug.md) and
[feature](./.github/ISSUE_TEMPLATE/feature.md) templates. Security issues
follow the disclosure flow in [SECURITY.md](./SECURITY.md) — please don't
report security findings as public issues.

The project maintainers use [beads (`bd`)](https://github.com/sfultong/beads)
locally for granular issue tracking; that database is not shipped with the
repo. Outside contributors do not need to install bd.

## Pull requests

1. Open a related GitHub issue first (or comment on an existing one) so the
   scope is visible before the diff lands.
2. Branch from `main`. Keep the diff focused on one issue.
3. Run the quality gates locally before pushing — see below.
4. Fill in the PR template; it walks you through what reviewers will check.

## Quickstart on a fresh checkout

```bash
./scripts/setup-dev.sh
```

This installs `uv` (via the official Astral installer if missing), installs
the project Python and dependencies, installs the pre-commit hooks via
`pre-commit install`, and runs every CI gate locally as a smoke test. The
script is idempotent — re-run it any time.

## Quality gates

```bash
uv sync                                     # install deps incl. dev
uv run pytest                               # tests
uv run ruff check                           # lint
uv run ruff format --check                  # format
uv run mypy src                             # static types (strict)
uv run pre-commit run --all-files           # everything pre-commit enforces
```

All four pass on every commit. CI runs the same set on every PR and push to
`main` (see `.github/workflows/ci.yml`).

## Adding a trigger or action type

See [docs/architecture.md](./docs/architecture.md#adding-a-new-trigger-type)
for the step-by-step recipes for new triggers, actions, and adapters. Each
is one new file in `domain/` plus a registry import, no engine changes.

## Reporting issues

External bug reports and feature requests are welcome via GitHub Issues.
Reproduction steps, your `yta version`, and the output of
`yta workflows validate` are usually enough to diagnose configuration
problems. For security findings, see [SECURITY.md](./SECURITY.md).
