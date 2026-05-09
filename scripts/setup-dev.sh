#!/usr/bin/env bash
# Bootstrap a fresh checkout into a working dev environment.
# Idempotent: safe to re-run.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

step() { printf "\n==> %s\n" "$*"; }

step "Repo root: $REPO_ROOT"

# 1. Install uv via the official Astral installer if missing.
if ! command -v uv >/dev/null 2>&1; then
    step "Installing uv (Astral installer)"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # Astral installer drops the binary in ~/.local/bin; make sure this shell sees it.
    export PATH="$HOME/.local/bin:$PATH"
fi

if ! command -v uv >/dev/null 2>&1; then
    cat >&2 <<'MSG'
ERROR: uv was installed but is not on PATH for this shell.
Add ~/.local/bin to PATH (e.g. in ~/.bashrc) and re-run scripts/setup-dev.sh.
MSG
    exit 1
fi
step "uv: $(uv --version)"

# 2. Install Python (matching .python-version) and project dependencies.
step "uv python install"
uv python install
step "uv sync"
uv sync

# 3. Wire git hooks to the bd-managed directory so the pre-commit chain fires.
HOOKS_DIR="$REPO_ROOT/.beads/hooks"
CURRENT="$(git config --get core.hooksPath || true)"
if [ "$CURRENT" != "$HOOKS_DIR" ]; then
    step "Setting git core.hooksPath to $HOOKS_DIR"
    git config core.hooksPath "$HOOKS_DIR"
fi

# 4. Verify the bd-managed hook still chains pre-commit.
step "Verifying hook chain"
"$REPO_ROOT/scripts/verify-hooks.sh"

# 5. Smoke test: run every CI gate locally.
step "Smoke test: ruff check"
uv run ruff check
step "Smoke test: ruff format --check"
uv run ruff format --check
step "Smoke test: mypy"
uv run mypy src
step "Smoke test: pytest"
uv run pytest

printf "\n✓ Dev environment ready. Run 'bd ready' to pick up work.\n"
