"""Persistent REPL namespace: reserved names, FINAL_VAR, normal Python stdlib."""

from __future__ import annotations

import ast
import hashlib
import io
import signal
import sys
import traceback
from collections.abc import Callable, Iterator
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from typing import Any

from rlm.core.history import (
    DISPLAY_MAX_CHARS,
    compact_repr,
    measure_ast,
    measure_text,
    plan_reads,
    sha256_text,
)
from rlm.core.types import Observation

# Fallback if the init payload omits cell_timeout_s (this file is copied into
# the image without config.py). Host default is Config.cell_timeout_s.
DEFAULT_CELL_CPU_TIMEOUT_S = 300.0


@contextmanager
def pause_alarm() -> Iterator[None]:
    """Stop SIGALRM for the duration of a host RPC so children can outlive the cell CPU cap."""
    if not hasattr(signal, "getitimer"):
        yield
        return
    remaining = signal.getitimer(signal.ITIMER_REAL)[0]
    signal.setitimer(signal.ITIMER_REAL, 0)
    try:
        yield
    finally:
        if remaining > 0:
            signal.setitimer(signal.ITIMER_REAL, remaining)

RESERVED_NAMES = (
    "context",
    "context_0",
    "query",
    "llm_query",
    "llm_query_batched",
    "rlm_query",
    "rlm_query_batched",
    "measure",
    "measure_ast",
    "plan_reads",
    "SHOW_VARS",
    "FINAL",
    "FINAL_VAR",
    "answer",
    "repo",
    "corpus",
    "catalog",
    "manifest",
)

# Docker is the sandbox (no net, no API key, read-only workspace). The REPL
# matches ordinary CPython so we do not fight pretrained import habits.
# `socket` stays blocked so cells cannot speak the host IPC sockets.
BLOCKED_IMPORTS = frozenset({"socket"})

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


def _require_prompt_str(who: str, prompt: Any) -> str:
    if isinstance(prompt, str):
        return prompt
    kind = type(prompt).__name__
    return (
        f"Error: {who} requires a str, got {kind}. "
        "Build the question with an f-string; do not pass a function or lambda. "
        'For a file, pass {"question": q, "path": p} to rlm_query / rlm_query_batched.'
    )


def _coerce_rlm_prompt(who: str, prompt: Any) -> str:
    """Accept a str, or {question, path} / {prompt, file} dict, for child RLMs."""
    if isinstance(prompt, str):
        return prompt
    if isinstance(prompt, dict):
        path = prompt.get("path") or prompt.get("file")
        question = prompt.get("question") or prompt.get("prompt") or prompt.get("q")
        have_q = isinstance(question, str) and bool(question.strip())
        have_path = isinstance(path, str) and bool(path.strip())
        if have_q and have_path:
            return (
                f"{question}\n\nTarget: {path}. "
                "The same repo/corpus is bound in your REPL. Read that file or document there; "
                "do not print the body. llm_query tight slices. FINAL a short cited answer."
            )
        if have_q:
            return question
    return _require_prompt_str(who, prompt)


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
        if root in BLOCKED_IMPORTS:
            raise ImportError(
                f"import of {name!r} is reserved for the RLM host RPC. "
                "Use llm_query / rlm_query."
            )
        return _builtins.__import__(name, globals, locals, fromlist, level)

    safe_builtins = {
        k: getattr(_builtins, k)
        for k in dir(_builtins)
        if not k.startswith("_")
    }
    # Keep the cell runner in charge of the process; everything else is normal Python.
    for banned in ("breakpoint", "exit", "quit", "help"):
        safe_builtins.pop(banned, None)
    safe_builtins["__import__"] = _restricted_import
    # Class statements need this; dir(builtins) skips dunders so it was dropped above.
    safe_builtins["__build_class__"] = _builtins.__build_class__

    def bounded_print(*args: Any, **kwargs: Any) -> None:
        file = kwargs.pop("file", None)
        buf = io.StringIO()
        _builtins.print(*args, file=buf, **kwargs)
        text = buf.getvalue()
        cap = int(ns.get("_max_stdout_chars") or 4000)
        total = len(text)
        if total > cap:
            text = (
                text[:cap]
                + f"\n...[print truncated, total_len={total}; "
                "assign to a variable and llm_query; do not print large strings]\n"
            )
        dest = file if file is not None else sys.stdout
        dest.write(text)

    safe_builtins["print"] = bounded_print
    ns["__builtins__"] = safe_builtins
    ns["__name__"] = "rlm_repl"

    def llm_query(prompt: str, model: str | None = None) -> str:
        text = _require_prompt_str("llm_query", prompt)
        if text.startswith("Error:"):
            return text
        return handler.llm_query(text, model=model)

    def llm_query_batched(prompts: list[str], model: str | None = None) -> list[str]:
        texts = [_require_prompt_str("llm_query_batched", p) for p in prompts]
        if any(t.startswith("Error:") for t in texts):
            return texts
        return handler.llm_query_batched(texts, model=model)

    def rlm_query(prompt: str, model: str | None = None) -> str:
        text = _coerce_rlm_prompt("rlm_query", prompt)
        if text.startswith("Error:"):
            return text
        return handler.rlm_query(text, model=model)

    def rlm_query_batched(prompts: list[str], model: str | None = None) -> list[str]:
        texts = [_coerce_rlm_prompt("rlm_query_batched", p) for p in prompts]
        if any(t.startswith("Error:") for t in texts):
            return texts
        return handler.rlm_query_batched(texts, model=model)

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
        if not isinstance(name, str):
            kind = type(name).__name__
            raise TypeError(
                f'FINAL_VAR requires a variable name as a str, got {kind}. '
                'Assign the answer, then FINAL_VAR("that_name").'
            )
        if name not in ns:
            raise NameError(_missing_final_var(name, ns))
        return FINAL(ns[name])

    ns["llm_query"] = llm_query
    ns["llm_query_batched"] = llm_query_batched
    ns["rlm_query"] = rlm_query
    ns["rlm_query_batched"] = rlm_query_batched
    ns["measure"] = measure_text
    ns["measure_ast"] = measure_ast
    ns["plan_reads"] = plan_reads
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

    _bind_subcall_fns(ns.get("repo"), llm_query, rlm_query)
    _bind_subcall_fns(ns.get("corpus"), llm_query, rlm_query)

    return ns


def _bind_subcall_fns(obj: Any, llm_fn: Callable[..., str], rlm_fn: Callable[..., str]) -> None:
    if obj is None:
        return
    if hasattr(obj, "ask"):
        obj._query_fn = llm_fn
    if hasattr(obj, "explore"):
        obj._rlm_fn = rlm_fn


def _is_final_call(node: ast.Expr) -> bool:
    value = node.value
    return (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Name)
        and value.func.id in {"FINAL", "FINAL_VAR"}
    )


def _user_var_names(ns: dict[str, Any]) -> list[str]:
    skip = {"__builtins__", "__name__"}
    names: list[str] = []
    for key in sorted(ns):
        if key.startswith("_") or key in skip or key in RESERVED_NAMES:
            continue
        names.append(key)
    return names


def _missing_final_var(name: str, ns: dict[str, Any]) -> str:
    bound = _user_var_names(ns)
    if bound:
        shown = bound[:40]
        extra = f" … ({len(bound) - 40} more)" if len(bound) > 40 else ""
        listing = ", ".join(shown) + extra
    else:
        listing = "(none yet)"
    return (
        f"{name!r} is not defined. Bound user names: {listing}. "
        'Assign the answer, then FINAL_VAR("that_name"). '
        "Do not invent names. Peek with grep/ast; llm_query a tight slice if needed."
        "SHOW_VARS() lists what exists."
    )


def _quote_final_var_names(tree: ast.AST) -> None:
    """Treat FINAL_VAR(foo) as FINAL_VAR("foo") so a bare name is a lookup, not a value."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not (isinstance(node.func, ast.Name) and node.func.id == "FINAL_VAR"):
            continue
        if len(node.args) != 1 or node.keywords:
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Name):
            node.args[0] = ast.Constant(arg.id)


def _split_last_expression_tree(
    tree: ast.Module,
) -> tuple[ast.Module | None, ast.Expression | None]:
    """If the last statement is a non-FINAL expression, return (prefix module, expr)."""
    if not tree.body or not isinstance(tree.body[-1], ast.Expr):
        return None, None
    last = tree.body[-1]
    assert isinstance(last, ast.Expr)
    if _is_final_call(last):
        return None, None
    prefix = ast.Module(body=list(tree.body[:-1]), type_ignores=list(tree.type_ignores))
    ast.fix_missing_locations(prefix)
    expr = ast.Expression(last.value)
    ast.fix_missing_locations(expr)
    return prefix, expr


def _format_cell_error(exc: BaseException) -> str:
    """Exception text plus the <repl> line; omit REPL internals."""
    name = type(exc).__name__
    msg = str(exc).strip() or repr(exc)
    lines = [f"{name}: {msg}"]
    for frame in traceback.extract_tb(exc.__traceback__):
        if frame.filename != "<repl>":
            continue
        snippet = (frame.line or "").strip()
        if snippet:
            lines.append(f"  <repl> line {frame.lineno}: {snippet}")
        else:
            lines.append(f"  <repl> line {frame.lineno}")
    return "\n".join(lines)


def _exec_cell(code: str, ns: dict[str, Any], buf_out: io.StringIO, max_send_chars: int) -> None:
    try:
        tree = ast.parse(code, filename="<repl>")
    except SyntaxError:
        compiled = compile(code, "<repl>", "exec")
        exec(compiled, ns, ns)  # noqa: S102 — product REPL; FakeEnv is tests-only
        return
    _quote_final_var_names(tree)
    ast.fix_missing_locations(tree)
    prefix, expr = _split_last_expression_tree(tree)
    if prefix is None or expr is None:
        exec(compile(tree, "<repl>", "exec"), ns, ns)  # noqa: S102
        return
    if prefix.body:
        exec(compile(prefix, "<repl>", "exec"), ns, ns)  # noqa: S102
    value = eval(compile(expr, "<repl>", "eval"), ns, ns)  # noqa: S307
    if value is None:
        return
    cap = min(DISPLAY_MAX_CHARS, max_send_chars)
    text = compact_repr(value, max_chars=cap)
    existing = buf_out.getvalue()
    if existing and not existing.endswith("\n"):
        buf_out.write("\n")
    buf_out.write(text)
    if not text.endswith("\n"):
        buf_out.write("\n")


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
                _exec_cell(code, ns, buf_out, max_send_chars)
            finally:
                if use_alarm and timeout_s and timeout_s > 0:
                    signal.setitimer(signal.ITIMER_REAL, 0)
                    if old_handler is not None:
                        signal.signal(signal.SIGALRM, old_handler)
    except Exception as exc:
        error = _format_cell_error(exc)
        buf_err.write(error)
        if not error.endswith("\n"):
            buf_err.write("\n")
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
