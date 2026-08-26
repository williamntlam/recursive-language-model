"""Truncate REPL stdout/stderr for hist. Never append the bound corpus."""

from __future__ import annotations

import ast
import hashlib
from typing import Any

from rlm.core.types import Message, Observation

# Parent hist keeps only this many recent (assistant, observation) pairs in full.
# Older pairs become stubs so the root stays in the low thousands of tokens.
HIST_KEEP_RECENT = 4
# When the next parent send would exceed this, remind it to keep work in the REPL.
PARENT_TOKEN_NUDGE = 1500
# Last-expression / compact repr budget (further truncated by max_observation_chars).
DISPLAY_MAX_CHARS = 800
_SEQ_PREVIEW = 8
_STR_PREVIEW = 240
# repo.ask / corpus.ask: larger than this (chars) spawns a child RLM instead of a leaf.
# ~6k tokens; enough for a typical function, not a whole modeling_*.py file.
ASK_LEAF_CHARS = 24_000
# cl100k is not in the REPL image; ~4 chars/token matches the leaf budget above.
CHARS_PER_TOKEN = 4

_OBS_STUB_PREFIX = "(compacted observation"
_CELL_STUB_MARK = "compacted cell"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="replace")).hexdigest()


def compact_repr(value: Any, *, max_chars: int = DISPLAY_MAX_CHARS) -> str:
    """Notebook-style display that refuses to dump large strings or sequences."""
    text = _compact(value, max_chars=max_chars, depth=0)
    if len(text) > max_chars:
        return (
            text[:max_chars] + f"\n...[truncated, total_len={len(text)}; "
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


def repl_error_hint(code: str, error: str | None) -> str | None:
    """Short recovery hint for common model-written cell failures."""
    if not error:
        return None
    if "KeyError" in error and ".format(" in (code or ""):
        return (
            "Hint: str.format() treats `{` as a replacement field. "
            "Use an f-string, or double the braces (`{{` `}}`) in the template."
        )
    return None


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
        parts.append(f"...[truncated, total_len={obs.total_stdout_len}, sha256={obs.sha256}]")
    else:
        parts.append(stdout)
        if obs.total_stdout_len > len(stdout):
            parts.append(f"...[truncated, total_len={obs.total_stdout_len}, sha256={obs.sha256}]")
    stderr = obs.stderr or ""
    if stderr:
        parts.append("--- stderr ---")
        if len(stderr) > max_chars:
            err_hash = sha256_text(stderr)
            parts.append(stderr[:max_chars])
            parts.append(f"...[truncated, total_len={obs.total_stderr_len}, sha256={err_hash}]")
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
        "Do not print file bodies. Grep/ast in this REPL; "
        "llm_query / repo.ask only on tight slices; "
        "rlm_query / repo.explore only if a file is still too large.]"
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
                f"{_OBS_STUB_PREFIX}, {n} chars, sha256={digest}; values remain in REPL variables)",
            )


def _already_compacted(content: str) -> bool:
    head = (content or "")[:120]
    return _CELL_STUB_MARK in head or head.startswith(_OBS_STUB_PREFIX)


def hist_contains_context(hist_text: str, context: str, min_len: int = 200) -> bool:
    """True if the full bound context leaked into hist (for tests and debug)."""
    if len(context) < min_len:
        return context in hist_text and len(context) > 0
    return context in hist_text


def estimate_tokens(n_chars: int) -> int:
    """Cheap token estimate for REPL routing. Not tiktoken (not in the image)."""
    if n_chars <= 0:
        return 0
    return (int(n_chars) + CHARS_PER_TOKEN - 1) // CHARS_PER_TOKEN


def _n_lines_of(text: str) -> int:
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def chunk_line_ranges(
    text: str, *, leaf_chars: int = ASK_LEAF_CHARS, line_offset: int = 0
) -> list[dict[str, int]]:
    """1-indexed line ranges, each at most `leaf_chars` when a line allows it."""
    if not text:
        return []
    lines = text.splitlines(keepends=True)
    out: list[dict[str, int]] = []
    i = 0
    n = len(lines)
    while i < n:
        start = i
        size = 0
        while i < n:
            ln = len(lines[i])
            if size > 0 and size + ln > leaf_chars:
                break
            size += ln
            i += 1
            if size >= leaf_chars:
                break
        if i == start:
            size = len(lines[i])
            i += 1
        out.append(
            {
                "start": start + 1 + line_offset,
                "end": i + line_offset,
                "n_chars": size,
                "n_tokens": estimate_tokens(size),
            }
        )
    return out


def measure_size(
    n_chars: int, *, n_lines: int | None = None, leaf_chars: int = ASK_LEAF_CHARS
) -> dict[str, Any]:
    n_chars = max(0, int(n_chars))
    too_big = n_chars > leaf_chars
    if n_chars == 0:
        n_chunks = 0
    elif too_big:
        n_chunks = (n_chars + leaf_chars - 1) // leaf_chars
    else:
        n_chunks = 1
    row: dict[str, Any] = {
        "n_chars": n_chars,
        "n_tokens": estimate_tokens(n_chars),
        "route": "child" if too_big else "fit",
        "n_chunks": n_chunks,
        "leaf_chars": leaf_chars,
    }
    if n_lines is not None:
        row["n_lines"] = n_lines
    return row


def measure_text(
    text: str, *, leaf_chars: int = ASK_LEAF_CHARS, line_offset: int = 0
) -> dict[str, Any]:
    """Size a slice. `route` is `fit` (ast / one leaf) or `child` (too big for one leaf)."""
    text = text or ""
    row = measure_size(len(text), n_lines=_n_lines_of(text), leaf_chars=leaf_chars)
    if row["route"] == "child":
        chunks = chunk_line_ranges(text, leaf_chars=leaf_chars, line_offset=line_offset)
        row["chunks"] = chunks
        row["n_chunks"] = len(chunks) or row["n_chunks"]
    return row


def measure_ast(source: str, *, leaf_chars: int = ASK_LEAF_CHARS) -> list[dict[str, Any]]:
    """Class / function spans with sizes. No bodies. Filter in Python, then plan_reads."""
    tree = ast.parse(source or "")
    lines = (source or "").splitlines(keepends=True)
    rows: list[dict[str, Any]] = []

    def record(node: ast.AST, kind: str, qualname: str) -> None:
        start = getattr(node, "lineno", None)
        end = getattr(node, "end_lineno", None) or start
        if start is None or end is None:
            return
        body = "".join(lines[start - 1 : end])
        row = measure_text(body, leaf_chars=leaf_chars, line_offset=start - 1)
        row["name"] = getattr(node, "name", "")
        row["qualname"] = qualname
        row["kind"] = kind
        row["start"] = start
        row["end"] = end
        rows.append(row)

    class Visitor(ast.NodeVisitor):
        def __init__(self) -> None:
            self.stack: list[str] = []

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            qual = ".".join(self.stack + [node.name])
            record(node, "ClassDef", qual)
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            record(node, "FunctionDef", ".".join(self.stack + [node.name]))
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            record(node, "AsyncFunctionDef", ".".join(self.stack + [node.name]))
            self.stack.append(node.name)
            self.generic_visit(node)
            self.stack.pop()

    Visitor().visit(tree)
    return rows


def plan_reads(items: Any, *, leaf_chars: int = ASK_LEAF_CHARS) -> dict[str, Any]:
    """How many leaves vs children a list of spans needs. Does not call an LM."""
    rows: list[dict[str, Any]] = []
    seq = items if isinstance(items, list) else [items]
    for item in seq:
        rows.append(_coerce_plan_item(item, leaf_chars=leaf_chars))
    n_fit = sum(1 for r in rows if r.get("route") == "fit")
    n_child = sum(1 for r in rows if r.get("route") == "child")
    n_chunks = sum(int(r.get("n_chunks") or 0) for r in rows)
    return {
        "n_fit": n_fit,
        "n_child": n_child,
        "n_chunks": n_chunks,
        "leaf_chars": leaf_chars,
        "spans": rows,
    }


def _coerce_plan_item(item: Any, *, leaf_chars: int) -> dict[str, Any]:
    if isinstance(item, dict):
        if "route" in item and "n_chars" in item:
            return item
        if "text" in item and item["text"] is not None:
            row = measure_text(str(item["text"]), leaf_chars=leaf_chars)
            return {k: v for k, v in item.items() if k != "text"} | row
        if "n_chars" in item:
            row = measure_size(int(item["n_chars"]), leaf_chars=leaf_chars)
            return {**item, **row}
        if "path" in item or "file" in item:
            raise ValueError(
                "plan_reads cannot size repository paths. Use repo.plan(spans) or "
                "repo.measure(path) first; plan_reads accepts text, character counts, "
                "or rows returned by measure/measure_ast."
            )
        return measure_size(0, leaf_chars=leaf_chars)
    if isinstance(item, str):
        return measure_text(item, leaf_chars=leaf_chars)
    if isinstance(item, (int, float)):
        return measure_size(int(item), leaf_chars=leaf_chars)
    return measure_size(0, leaf_chars=leaf_chars)


def route_read_subcall(
    question: str,
    loc: str,
    text: str,
    llm_fn,
    rlm_fn,
    *,
    leaf_chars: int = ASK_LEAF_CHARS,
    targets: list[dict] | None = None,
) -> str:
    """Leaf for tight slices; child RLM when the read would bloat a prompt."""
    n = len(text or "")
    if rlm_fn is not None and (llm_fn is None or n > leaf_chars):
        return str(
            rlm_fn(
                f"{question}\n\nTarget: {loc} ({n} chars). "
                "The same repo/corpus is bound in your REPL. Grep/ast it there; "
                "do not print the body. llm_query tight slices. "
                "rlm_query again only if it is still too large. FINAL a short cited answer.",
                targets=targets,
            )
        )
    if llm_fn is None:
        raise RuntimeError("No llm_query/rlm_query bound. Call llm_query(question + text) instead.")
    return str(
        llm_fn(
            f"{question}\n\nSource: {loc}\n"
            "Answer using only this text. Quote briefly and cite when possible.\n"
            "---\n"
            f"{text}\n"
            "---\n"
        )
    )
