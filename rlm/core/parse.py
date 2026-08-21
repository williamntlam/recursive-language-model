"""Extract a Python cell from a model turn."""

from __future__ import annotations

import re

# Opening fence, then body until a closer or end of string (unclosed is allowed).
_OPEN = re.compile(
    r"```[ \t]*(?P<lang>[a-zA-Z0-9_+-]*)[^\n]*\n(?P<code>.*?)(?:```|\Z)",
    re.DOTALL | re.IGNORECASE,
)
_SKIP_LANGS = frozenset(
    {
        "json",
        "html",
        "xml",
        "md",
        "markdown",
        "yaml",
        "yml",
        "diff",
        "text",
        "txt",
        "bash",
        "sh",
        "zsh",
        "shell",
    }
)
_BARE_HEADERS = frozenset({"repl", "python", "py"})
_FENCE_LEFTOVER = re.compile(
    r"^[ \t]*(?:```)?[ \t]*(?:repl|python|py)[ \t]*:?[ \t]*(?:```)?[ \t]*$",
    re.IGNORECASE,
)
# `print(...)")repl` — heading glued to the previous statement.
_GLUED_REPL = re.compile(
    r"^(?P<prefix>.*[^A-Za-z0-9_])(?P<header>repl)[ \t]*:?[ \t]*$",
    re.IGNORECASE,
)


def extract_repl_code(text: str) -> str | None:
    """Prefer ```repl, then ```python, then unlabeled ```, then a bare `repl` header."""
    body = (text or "").replace("\r\n", "\n")
    fenced = _fenced_cell(body)
    if fenced is not None:
        return _strip_fence_leftovers(fenced)
    bare = _bare_repl_cell(body)
    if bare is None:
        return None
    return _strip_fence_leftovers(bare)


def _strip_fence_leftovers(code: str) -> str:
    """Drop stray `repl` / `python` headings the model leaves inside a cell."""
    kept = [line for line in code.split("\n") if not _FENCE_LEFTOVER.match(line)]
    return "\n".join(kept).strip("\n")


def _fenced_cell(body: str) -> str | None:
    labeled: dict[str, str] = {}
    unlabeled: str | None = None
    for match in _OPEN.finditer(body):
        lang = (match.group("lang") or "").lower()
        code = match.group("code")
        if lang in _SKIP_LANGS:
            continue
        if lang in _BARE_HEADERS:
            labeled[lang] = code
        elif lang == "":
            unlabeled = code
    for lang in ("repl", "python", "py"):
        if lang in labeled:
            return labeled[lang]
    return unlabeled


def _is_bare_header(line: str) -> bool:
    header = line.strip().strip("`").strip().lower().rstrip(":")
    return header in _BARE_HEADERS


def _unglue_repl_headers(body: str) -> str:
    lines: list[str] = []
    for line in body.split("\n"):
        match = _GLUED_REPL.match(line)
        if match and match.group("prefix").strip():
            lines.append(match.group("prefix"))
            lines.append("repl")
        else:
            lines.append(line)
    return "\n".join(lines)


def _bare_repl_cell(body: str) -> str | None:
    """gpt-5 often writes `repl` as a heading, not a markdown fence."""
    body = _unglue_repl_headers(body)
    lines = body.split("\n")
    start: int | None = None
    for i, line in enumerate(lines):
        if _is_bare_header(line):
            start = i
            break
    if start is None:
        return None
    rest = "\n".join(lines[start + 1 :])
    if not rest.strip():
        return None
    return rest
