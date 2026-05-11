"""Tests for the pure diff classifier."""

from __future__ import annotations

from youtrack_aitrack.domain.diff_filter import DiffFilterConfig, classify_diff


def _file_block(path: str, hunk_lines: int = 3) -> str:
    body = "\n".join(f"+line {i}" for i in range(hunk_lines))
    return (
        f"diff --git a/{path} b/{path}\n"
        f"index 1111111..2222222 100644\n"
        f"--- a/{path}\n"
        f"+++ b/{path}\n"
        f"@@ -1,3 +1,{hunk_lines} @@\n"
        f"{body}\n"
    )


def test_empty_diff_returns_empty() -> None:
    assert classify_diff("") == ""


def test_normal_diff_passes_through() -> None:
    diff = _file_block("src/foo.py")
    out = classify_diff(diff)
    assert "src/foo.py" in out
    assert "+line 0" in out


def test_lock_files_excluded() -> None:
    diff = _file_block("package-lock.json") + _file_block("src/foo.py")
    out = classify_diff(diff)
    assert "package-lock.json" not in out
    assert "src/foo.py" in out


def test_all_default_lock_files_excluded() -> None:
    locks = [
        "package-lock.json",
        "poetry.lock",
        "uv.lock",
        "Cargo.lock",
        "Gemfile.lock",
        "yarn.lock",
        "pnpm-lock.yaml",
        "composer.lock",
    ]
    diff = "".join(_file_block(p) for p in locks) + _file_block("src/keep.py")
    out = classify_diff(diff)
    for lock in locks:
        assert lock not in out
    assert "src/keep.py" in out


def test_vendor_dirs_excluded() -> None:
    diff = (
        _file_block("node_modules/foo/index.js")
        + _file_block("vendor/lib.go")
        + _file_block(".venv/lib/x.py")
        + _file_block("dist/app.js")
        + _file_block("build/out.o")
        + _file_block("src/keep.py")
    )
    out = classify_diff(diff)
    for path in ["node_modules/", "vendor/", ".venv/", "dist/", "build/"]:
        assert path not in out
    assert "src/keep.py" in out


def test_minified_assets_excluded() -> None:
    diff = (
        _file_block("static/app.min.js")
        + _file_block("static/app.min.css")
        + _file_block("src/keep.ts")
    )
    out = classify_diff(diff)
    assert ".min.js" not in out
    assert ".min.css" not in out
    assert "src/keep.ts" in out


def test_binary_files_excluded() -> None:
    binary_block = (
        "diff --git a/img.png b/img.png\n"
        "index 1111..2222 100644\n"
        "Binary files a/img.png and b/img.png differ\n"
    )
    diff = binary_block + _file_block("src/keep.py")
    out = classify_diff(diff)
    assert "img.png" not in out
    assert "src/keep.py" in out


def test_oversized_file_is_truncated() -> None:
    big = _file_block("src/big.py", hunk_lines=500)
    cfg = DiffFilterConfig(max_file_bytes=200, truncate_keep_lines=5)
    out = classify_diff(big, config=cfg)
    assert "[truncated]" in out
    assert out.count("+line ") <= 5


def test_oversized_total_triggers_per_file_truncation() -> None:
    diff = "".join(_file_block(f"src/f{i}.py", hunk_lines=200) for i in range(5))
    cfg = DiffFilterConfig(
        max_file_bytes=10 * 1024 * 1024,
        max_total_bytes=500,
        truncate_keep_lines=3,
    )
    out = classify_diff(diff, config=cfg)
    assert out.count("[truncated]") == 5


def test_short_block_not_truncated() -> None:
    diff = _file_block("src/tiny.py", hunk_lines=2)
    out = classify_diff(diff)
    assert "[truncated]" not in out


def test_custom_exclude_globs_override_defaults() -> None:
    diff = _file_block("package-lock.json") + _file_block("custom.txt")
    cfg = DiffFilterConfig(exclude_globs=("custom.txt",))
    out = classify_diff(diff, config=cfg)
    assert "package-lock.json" in out
    assert "custom.txt" not in out


def test_nested_minified_path_excluded() -> None:
    diff = _file_block("a/b/c/script.min.js") + _file_block("src/keep.py")
    out = classify_diff(diff)
    assert "script.min.js" not in out
    assert "src/keep.py" in out
