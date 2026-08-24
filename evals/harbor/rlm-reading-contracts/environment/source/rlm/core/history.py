"""Truncate REPL observations for history; never append the bound corpus."""

from __future__ import annotations

import hashlib

# Parent history keeps only this many recent assistant/observation pairs in full.
# Older pairs become stubs so the root stays in the low thousands of tokens.
HIST_KEEP_RECENT = 4
_OBS_STUB_PREFIX = "(compacted observation"
_CELL_STUB_MARK = "compacted cell"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def compact_parent_hist(hist: list[dict[str, str]], *, keep_recent: int = HIST_KEEP_RECENT) -> None:
    """Stub old code/observation pairs without copying bound source context."""
    if keep_recent < 1 or len(hist) < 4:
        return
    keep_from = len(hist) - keep_recent * 2
    for index in range(2, keep_from):
        message = hist[index]
        content = message.get("content", "")
        digest = sha256_text(content)[:16]
        if message.get("role") == "assistant":
            hist[index] = {
                "role": "assistant",
                "content": (
                    f"```repl\\n# {_CELL_STUB_MARK} ({len(content)} chars, "
                    f"sha256={digest})\\n```"
                ),
            }
        elif message.get("role") == "user":
            hist[index] = {
                "role": "user",
                "content": (
                    f"{_OBS_STUB_PREFIX}, {len(content)} chars, sha256={digest}; "
                    "values remain in REPL variables)"
                ),
            }
