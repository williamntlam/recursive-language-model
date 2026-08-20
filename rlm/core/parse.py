"""Extract fenced ```repl``` blocks. Prose is ignored."""

from __future__ import annotations

import re

_FENCE = re.compile(r"```repl[^\n]*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def extract_repl_code(text: str) -> str | None:
    matches = _FENCE.findall(text or "")
    if not matches:
        return None
    return matches[-1]
