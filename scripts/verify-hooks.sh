#!/usr/bin/env bash
# Verify that the bd-managed pre-commit hook still chains the pre-commit framework.
# Exits 0 when intact, 1 otherwise. Wire into CI and dev setup scripts.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
HOOK="${REPO_ROOT}/.beads/hooks/pre-commit"

if [ ! -f "$HOOK" ]; then
    echo "ERROR: $HOOK not found. Run 'bd init' to install bd hooks." >&2
    exit 1
fi

if ! grep -q 'uv run pre-commit run' "$HOOK"; then
    echo "ERROR: pre-commit framework chain missing from $HOOK" >&2
    echo "Expected: 'uv run pre-commit run' invocation after the BEADS markers." >&2
    exit 1
fi

echo "OK: pre-commit chain intact in ${HOOK#"${REPO_ROOT}/"}"
