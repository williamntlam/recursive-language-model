"""Truncate REPL stdout/stderr for hist. Never append the bound corpus."""

from __future__ import annotations

import hashlib
from typing import Any

from rlm.core.types import Message, Observation

# Parent hist keeps only this many recent (assistant, observation) pairs in full.
# Older pairs become stubs so the root stays in the low thousands of tokens.
HIST_KEEP_RECENT = 4
# When the next parent send would exceed this, append a reminder to recurse.
PARENT_TOKEN_NUDGE = 1500
# Last-expression / compact repr budget (further truncated by max_observation_chars).
DISPLAY_MAX_CHARS = 800
_SEQ_PREVIEW = 8
_STR_PREVIEW = 240
# repo.ask / corpus.ask: larger slices spawn a child RLM instead of a leaf.
ASK_LEAF_CHARS = 800

_OBS_STUB_PREFIX = "(compacted observation"
_CELL_STUB_MARK = "compacted cell"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def compact_repr(value: Any, *, max_chars: int = DISPLAY_MAX_CHARS) -> str:
    """Notebook-style display that refuses to dump large strings or sequences."""
    text = _compact(value, max_chars=max_chars, depth=0)
    if len(text) > max_chars:
        return (
            text[:max_chars]
            + f"\n...[truncated, total_len={len(text)}; "
            "keep in a variable and llm_query this slice]"
        )
    return text


def _compact(value: Any, *, max_chars: int, depth: int) -> str:
    if value is None:
        return "None"
    if isinstance(value, str):
        if len(value) <= _STR_PREVIEW and len(value) <= max_chars:
            return value if "\n" in value else repr(value)
        preview = value[:_STR_PREVIEW].replace("\n", "\\n")
        digest = sha256_text(value)[:16]
        return (
            f"<str n_chars={len(value)} sha256={digest}>\n"
            f"{preview}\n"
            "...[not shown; assign to a name and llm_query this slice; do not print it]"
        )
    if isinstance(value, (bytes, bytearray)):
        return f"<{type(value).__name__} n={len(value)}>"
    if isinstance(value, dict):
        n = len(value)
        if n == 0:
            return "{}"
        items = list(value.items())[:_SEQ_PREVIEW]
        inner = ", ".join(
            f"{_compact(k, max_chars=80, depth=depth + 1)!s}: "
            f"{_compact(v, max_chars=120, depth=depth + 1)}"
            for k, v in items
        )
        extra = "" if n <= _SEQ_PREVIEW else f", ... ({n - _SEQ_PREVIEW} more)"
        return "{" + inner + extra + "}"
    if isinstance(value, (list, tuple, set)):
        seq = list(value)
        n = len(seq)
        open_b, close_b = ("[", "]") if not isinstance(value, tuple) else ("(", ")")
        if isinstance(value, set):
            open_b, close_b = "{", "}"
        if n == 0:
            return open_b + close_b
        shown = seq[:_SEQ_PREVIEW]
        inner = ", ".join(_compact(x, max_chars=160, depth=depth + 1) for x in shown)
        extra = "" if n <= _SEQ_PREVIEW else f", ... ({n - _SEQ_PREVIEW} more)"
        hint = ""
        if n > _SEQ_PREVIEW and depth == 0:
            hint = "  # keep in a variable; print(len(...)) or llm_query a slice"
        body = open_b + inner + extra + close_b
        return body + hint if hint else body
    text = repr(value)
    if len(text) > max_chars:
        return text[:max_chars] + f"...[repr truncated, total_len={len(text)}]"
    return text


def format_observation(obs: Observation, max_chars: int) -> str:
    parts: list[str] = []
    stdout = obs.stdout or ""
    if not stdout and not (obs.stderr or "") and not obs.error:
        parts.append(
            "(no stdout; trailing expressions are displayed automatically. "
            "print() only small summaries. Large values stay in variables; "
            "send slices with llm_query / repo.ask / corpus.ask.)"
        )
    elif len(stdout) > max_chars:
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


def observation_nudge(n_tokens: int) -> str | None:
    if n_tokens < PARENT_TOKEN_NUDGE:
        return None
    return (
        f"[parent prompt is {n_tokens} tokens; target is the low thousands. "
        "Do not print file bodies. Spawn rlm_query / repo.explore per file; "
        "use llm_query / repo.ask only on tight slices. Print only short child answers.]"
    )


def assistant_cell_message(code: str) -> Message:
    """Parent hist stores the executed cell, not the model's surrounding prose."""
    return Message("assistant", f"```repl\n{code}\n```")


def compact_parent_hist(
    hist: list[Message],
    *,
    keep_recent: int = HIST_KEEP_RECENT,
) -> None:
    """Stub old code/observation pairs. Does not touch system or the original query."""
    if keep_recent < 1 or len(hist) < 4:
        return
    # hist[0]=system, hist[1]=user query; remaining should be assistant/user pairs.
    session = list(range(2, len(hist)))
    keep_from = len(hist) - keep_recent * 2
    for i in session:
        if i >= keep_from:
            break
        msg = hist[i]
        if _already_compacted(msg.content):
            continue
        n = len(msg.content or "")
        digest = sha256_text(msg.content or "")[:16]
        if msg.role == "assistant":
            hist[i] = Message(
                "assistant",
                f"```repl\n# {_CELL_STUB_MARK} ({n} chars, sha256={digest})\n```",
            )
        elif msg.role == "user":
            hist[i] = Message(
                "user",
                f"{_OBS_STUB_PREFIX}, {n} chars, sha256={digest}; "
                "values remain in REPL variables)",
            )


def _already_compacted(content: str) -> bool:
    head = (content or "")[:120]
    return _CELL_STUB_MARK in head or head.startswith(_OBS_STUB_PREFIX)


def hist_contains_context(hist_text: str, context: str, min_len: int = 200) -> bool:
    """True if the full bound context leaked into hist (for tests and debug)."""
    if len(context) < min_len:
        return context in hist_text and len(context) > 0
    return context in hist_text


def route_read_subcall(
    question: str,
    loc: str,
    text: str,
    llm_fn,
    rlm_fn,
    *,
    leaf_chars: int = ASK_LEAF_CHARS,
) -> str:
    """Leaf for tight slices; child RLM when the read would bloat a prompt."""
    n = len(text or "")
    if rlm_fn is not None and (llm_fn is None or n > leaf_chars):
        return str(
            rlm_fn(
                f"{question}\n\nTarget: {loc} ({n} chars). "
                "The same repo/corpus is bound in your REPL. Read it there; "
                "do not print the body. llm_query tight slices. "
                "rlm_query again if it is still large. FINAL a short cited answer."
            )
        )
    if llm_fn is None:
        raise RuntimeError(
            "No llm_query/rlm_query bound. Call llm_query(question + text) instead."
        )
    return str(
        llm_fn(
            f"{question}\n\nSource: {loc}\n"
            "Answer using only this text. Quote briefly and cite when possible.\n"
            "---\n"
            f"{text}\n"
            "---\n"
        )
    )
