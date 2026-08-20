"""Truncate REPL stdout/stderr for hist. Never append the bound corpus."""

from __future__ import annotations

import hashlib

from rlm.core.types import Observation


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def format_observation(obs: Observation, max_chars: int) -> str:
    parts: list[str] = []
    stdout = obs.stdout or ""
    if len(stdout) > max_chars:
        parts.append(stdout[:max_chars])
        parts.append(
            f"...[truncated, total_len={obs.total_stdout_len}, sha256={obs.sha256}]"
        )
    else:
        parts.append(stdout)
        if obs.total_stdout_len > len(stdout):
            parts.append(
                f"...[truncated, total_len={obs.total_stdout_len}, sha256={obs.sha256}]"
            )
    stderr = obs.stderr or ""
    if stderr:
        parts.append("--- stderr ---")
        if len(stderr) > max_chars:
            err_hash = sha256_text(stderr)
            parts.append(stderr[:max_chars])
            parts.append(
                f"...[truncated, total_len={obs.total_stderr_len}, sha256={err_hash}]"
            )
        else:
            parts.append(stderr)
            if obs.total_stderr_len > len(stderr):
                parts.append(f"...[truncated, total_len={obs.total_stderr_len}]")
    return "\n".join(parts)


def hist_contains_context(hist_text: str, context: str, min_len: int = 200) -> bool:
    """True if the full bound context leaked into hist (for tests and debug)."""
    if len(context) < min_len:
        return context in hist_text and len(context) > 0
    return context in hist_text
