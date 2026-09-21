"""Deterministic branch naming from an issue id and its summary.

Pure string functions so the same issue always yields the same branch name.
The default template ``{task_id}-{slug}`` matches the default
``defaults.branch_pattern`` (``{task_id}-*``), so branches created here are
later found by the diff-based workflows without extra configuration.
"""

from __future__ import annotations

import re
import unicodedata

DEFAULT_BRANCH_TEMPLATE = "{task_id}-{slug}"
DEFAULT_SLUG_MAX_LEN = 40

_NON_SLUG_CHARS = re.compile(r"[^a-z0-9]+")

# Letters that NFKD leaves undecomposed (no combining-mark form), so the ASCII
# fold would silently drop them. Mapped explicitly to their conventional ASCII.
_UNDECOMPOSABLE = str.maketrans(
    {"ł": "l", "Ł": "L", "ø": "o", "Ø": "O", "đ": "d", "Đ": "D", "ß": "ss", "æ": "ae", "Æ": "AE"}
)


def slugify(text: str, *, max_len: int = DEFAULT_SLUG_MAX_LEN) -> str:
    """Fold *text* to lowercase ASCII words joined by single hyphens, cut on a word boundary."""
    folded = (
        unicodedata.normalize("NFKD", text.translate(_UNDECOMPOSABLE))
        .encode("ascii", "ignore")
        .decode("ascii")
    )
    slug = _NON_SLUG_CHARS.sub("-", folded.lower()).strip("-")
    if len(slug) <= max_len:
        return slug
    cut = slug[:max_len]
    if "-" in cut and not slug[max_len:].startswith("-"):
        cut = cut.rsplit("-", 1)[0]
    return cut.strip("-")


def build_branch_name(
    template: str,
    *,
    task_id: str,
    summary: str | None,
    max_slug_len: int = DEFAULT_SLUG_MAX_LEN,
) -> str:
    """Fill ``{task_id}`` / ``{slug}`` in *template*.

    Raises ValueError when the template needs a slug but the summary is missing
    or slugifies to nothing, so callers never create a branch like ``PROJ-1-``.
    """
    if "{slug}" not in template:
        return template.replace("{task_id}", task_id)
    slug = slugify(summary or "", max_len=max_slug_len)
    if not slug:
        raise ValueError(
            f"cannot build branch name from template {template!r}: "
            f"issue summary {summary!r} yields an empty slug"
        )
    return template.replace("{task_id}", task_id).replace("{slug}", slug)
