"""Persistent REPL namespace: reserved names, FINAL_VAR, restricted imports."""

from __future__ import annotations

import hashlib
import io
import signal
import traceback
from collections.abc import Callable
from contextlib import redirect_stderr, redirect_stdout
from typing import Any

from rlm.core.history import sha256_text
from rlm.core.types import Observation

RESERVED_NAMES = (
    "context",
    "context_0",
    "query",
    "llm_query",
    "llm_query_batched",
    "rlm_query",
    "rlm_query_batched",
    "SHOW_VARS",
    "FINAL",
    "FINAL_VAR",
    "answer",
    "repo",
    "corpus",
    "catalog",
    "manifest",
)

ALLOWED_IMPORTS = frozenset(
    {
        "re",
        "json",
        "pathlib",
        "collections",
        "textwrap",
        "math",
        "datetime",
        "itertools",
        "functools",
        "typing",
        "html",
        "hashlib",
        "copy",
        "string",
        "pprint",
        "dataclasses",
        "enum",
        "abc",
        "numbers",
        "decimal",
        "fractions",
        "statistics",
        "unicodedata",
        "base64",
        "difflib",
        "fnmatch",
        "operator",
        "heapq",
        "bisect",
        "random",
        "time",
    }
)

_SENTINEL = object()


class SubcallHandler:
    def llm_query(self, prompt: str, model: str | None = None) -> str:
        raise NotImplementedError

    def llm_query_batched(
        self, prompts: list[str], model: str | None = None
    ) -> list[str]:
        raise NotImplementedError

    def rlm_query(self, prompt: str, model: str | None = None) -> str:
        raise NotImplementedError

    def rlm_query_batched(
        self, prompts: list[str], model: str | None = None
    ) -> list[str]:
        raise NotImplementedError


def snapshot_reserved(ns: dict[str, Any]) -> dict[str, Any]:
    return {name: ns[name] for name in RESERVED_NAMES if name in ns}


def restore_reserved(ns: dict[str, Any], snap: dict[str, Any]) -> None:
    for name, value in snap.items():
        ns[name] = value


def _size_hint(value: Any) -> str:
    if isinstance(value, str):
        return f"str n_chars={len(value)}"
    if isinstance(value, (bytes, bytearray)):
        return f"bytes n={len(value)}"
    if isinstance(value, (list, tuple, set, dict)):
        return f"{type(value).__name__} len={len(value)}"
    return type(value).__name__


def create_namespace(
    bindings: dict[str, Any],
    handler: SubcallHandler,
    *,
    max_stdout_chars: int = 4000,
) -> dict[str, Any]:
    import builtins as _builtins

    ns: dict[str, Any] = {}

    def _restricted_import(name, globals=None, locals=None, fromlist=(), level=0):  # noqa: A002
        root = name.split(".")[0]
        if root not in ALLOWED_IMPORTS:
            raise ImportError(
                f"import of {name!r} is not allowed in the RLM REPL. "
                "Use re, json, pathlib, collections, textwrap, and bound helpers."
            )
        return _builtins.__import__(name, globals, locals, fromlist, level)

    safe_builtins = {
        k: getattr(_builtins, k)
        for k in dir(_builtins)
        if not k.startswith("_")
    }
    # Keep the usual safe builtins; drop things that shell out or introspect too hard.
    for banned in ("exec", "eval", "compile", "open", "breakpoint", "exit", "quit", "help"):
        safe_builtins.pop(banned, None)
    safe_builtins["__import__"] = _restricted_import
    ns["__builtins__"] = safe_builtins
    ns["__name__"] = "rlm_repl"

    def llm_query(prompt: str, model: str | None = None) -> str:
        return handler.llm_query(str(prompt), model=model)

    def llm_query_batched(prompts: list[str], model: str | None = None) -> list[str]:
        return handler.llm_query_batched([str(p) for p in prompts], model=model)

    def rlm_query(prompt: str, model: str | None = None) -> str:
        return handler.rlm_query(str(prompt), model=model)

    def rlm_query_batched(prompts: list[str], model: str | None = None) -> list[str]:
        return handler.rlm_query_batched([str(p) for p in prompts], model=model)

    def SHOW_VARS() -> str:
        lines: list[str] = []
        for key, value in sorted(ns.items()):
            if key.startswith("_") or key in {"__builtins__", "__name__"}:
                continue
            if callable(value) and key in RESERVED_NAMES:
                lines.append(f"{key}: builtin")
                continue
            lines.append(f"{key}: {_size_hint(value)}")
        return "\n".join(lines)

    def FINAL(text: Any) -> str:
        ns["_rlm_final"] = str(text)
        answer = ns.get("answer")
        if isinstance(answer, dict):
            answer["ready"] = True
            answer["value"] = str(text)
        return ns["_rlm_final"]

    def FINAL_VAR(name: str) -> str:
        if name not in ns:
            raise NameError(f"{name!r} is not defined")
        return FINAL(ns[name])

    ns["llm_query"] = llm_query
    ns["llm_query_batched"] = llm_query_batched
    ns["rlm_query"] = rlm_query
    ns["rlm_query_batched"] = rlm_query_batched
    ns["SHOW_VARS"] = SHOW_VARS
    ns["FINAL"] = FINAL
    ns["FINAL_VAR"] = FINAL_VAR
    ns["answer"] = {"ready": False, "value": None}
    ns["_rlm_final"] = None
    ns["_max_stdout_chars"] = max_stdout_chars

    for key, value in bindings.items():
        ns[key] = value
        if key == "context" and "context_0" not in bindings:
            ns["context_0"] = value

    return ns


def run_cell(
    ns: dict[str, Any],
    code: str,
    reserved_snap: dict[str, Any],
    *,
    timeout_s: float | None = None,
    max_send_chars: int = 8000,
    use_alarm: bool = False,
) -> Observation:
    buf_out = io.StringIO()
    buf_err = io.StringIO()
    error: str | None = None
    old_handler: Callable | None = None

    def _alarm(signum, frame):  # noqa: ARG001
        raise TimeoutError(f"cell exceeded {timeout_s}s")

    try:
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            if use_alarm and timeout_s and timeout_s > 0:
                old_handler = signal.signal(signal.SIGALRM, _alarm)
                signal.setitimer(signal.ITIMER_REAL, timeout_s)
            try:
                compiled = compile(code, "<repl>", "exec")
                exec(compiled, ns, ns)  # noqa: S102 — product REPL; FakeEnv is tests-only
            finally:
                if use_alarm and timeout_s and timeout_s > 0:
                    signal.setitimer(signal.ITIMER_REAL, 0)
                    if old_handler is not None:
                        signal.signal(signal.SIGALRM, old_handler)
    except Exception:
        error = traceback.format_exc()
        buf_err.write(error)
    finally:
        restore_reserved(ns, reserved_snap)

    stdout_full = buf_out.getvalue()
    stderr_full = buf_err.getvalue()
    final = ns.get("_rlm_final")
    answer = ns.get("answer")
    if final is None and isinstance(answer, dict) and answer.get("ready"):
        final = "" if answer.get("value") is None else str(answer.get("value"))
    if isinstance(final, str) and final == "":
        pass
    elif final is not None:
        final = str(final)

    stdout_send = stdout_full[:max_send_chars]
    stderr_send = stderr_full[:max_send_chars]
    return Observation(
        stdout=stdout_send,
        stderr=stderr_send,
        total_stdout_len=len(stdout_full),
        total_stderr_len=len(stderr_full),
        sha256=sha256_text(stdout_full) if stdout_full else hashlib.sha256(b"").hexdigest(),
        final=final,
        error=error,
    )
