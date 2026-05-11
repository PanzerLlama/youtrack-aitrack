"""Pure diff classifier — filter and bound git-diff text before it reaches the LLM."""

from __future__ import annotations

from fnmatch import fnmatch

from pydantic import BaseModel, ConfigDict

_DEFAULT_EXCLUDE_GLOBS: tuple[str, ...] = (
    "package-lock.json",
    "poetry.lock",
    "uv.lock",
    "Cargo.lock",
    "Gemfile.lock",
    "yarn.lock",
    "pnpm-lock.yaml",
    "composer.lock",
    "node_modules/**",
    "vendor/**",
    ".venv/**",
    "dist/**",
    "build/**",
    "**/*.min.js",
    "**/*.min.css",
)


class DiffFilterConfig(BaseModel):
    exclude_globs: tuple[str, ...] = _DEFAULT_EXCLUDE_GLOBS
    max_file_bytes: int = 256 * 1024
    max_total_bytes: int = 200 * 1024
    truncate_keep_lines: int = 50
    truncation_marker: str = "[truncated]"

    model_config = ConfigDict(frozen=True)


def classify_diff(raw_diff: str, *, config: DiffFilterConfig | None = None) -> str:
    if not raw_diff:
        return ""
    cfg = config or DiffFilterConfig()
    kept: list[str] = []
    for path, block in _split_files(raw_diff):
        if _matches_any(path, cfg.exclude_globs):
            continue
        if _is_binary_block(block):
            continue
        if _byte_len(block) > cfg.max_file_bytes:
            block = _truncate_block(block, cfg)
        kept.append(block)
    total = "".join(kept)
    if _byte_len(total) > cfg.max_total_bytes:
        kept = [_truncate_block(b, cfg) for b in kept]
        total = "".join(kept)
    return total


def _split_files(diff: str) -> list[tuple[str, str]]:
    lines = diff.splitlines(keepends=True)
    files: list[tuple[str, str]] = []
    i = 0
    while i < len(lines):
        if not lines[i].startswith("diff --git "):
            i += 1
            continue
        path = _parse_path(lines[i])
        j = i + 1
        while j < len(lines) and not lines[j].startswith("diff --git "):
            j += 1
        files.append((path, "".join(lines[i:j])))
        i = j
    return files


def _parse_path(header: str) -> str:
    parts = header.strip().split(" ")
    for part in parts:
        if part.startswith("b/"):
            return part[2:]
        if part.startswith("a/"):
            return part[2:]
    return "<unknown>"


def _matches_any(path: str, globs: tuple[str, ...]) -> bool:
    name = path.rsplit("/", 1)[-1]
    for pattern in globs:
        if pattern.endswith("/**"):
            prefix = pattern[:-3]
            if path == prefix or path.startswith(prefix + "/"):
                return True
        elif pattern.startswith("**/"):
            if fnmatch(name, pattern[3:]):
                return True
        elif fnmatch(path, pattern) or fnmatch(name, pattern):
            return True
    return False


def _is_binary_block(block: str) -> bool:
    return "\nBinary files " in block or block.startswith("Binary files ")


def _byte_len(text: str) -> int:
    return len(text.encode("utf-8"))


def _truncate_block(block: str, cfg: DiffFilterConfig) -> str:
    lines = block.splitlines(keepends=True)
    if len(lines) <= cfg.truncate_keep_lines:
        return block
    head = "".join(lines[: cfg.truncate_keep_lines])
    if not head.endswith("\n"):
        head += "\n"
    return f"{head}{cfg.truncation_marker}\n"
