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


def extract_repl_code(text: str) -> str | None:
    """Prefer ```repl, then ```python, then unlabeled ```, then a bare `repl` header."""
    body = (text or "").replace("\r\n", "\n")
    fenced = _fenced_cell(body)
    if fenced is not None:
        return fenced
    return _bare_repl_cell(body)


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


def _bare_repl_cell(body: str) -> str | None:
    """gpt-5 often writes `repl` as a heading, not a markdown fence."""
    stripped = body.strip()
    if not stripped or "\n" not in stripped:
        return None
    first, _, rest = stripped.partition("\n")
    header = first.strip().strip("`").strip().lower().rstrip(":")
    if header in _BARE_HEADERS and rest.strip():
        return rest
    return None
