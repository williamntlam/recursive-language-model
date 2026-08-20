#!/usr/bin/env python3
"""In-container cell runner. Talks to the host over unix sockets. No API key here."""

from __future__ import annotations

import os
import socket
import sys
import time
from pathlib import Path

# PYTHONPATH=/opt/rlm
from rlm.domains.corpus import Corpus, ingest_path
from rlm.domains.repo import Repo
from rlm.ipc import read_msg, write_msg
from rlm.repl_ns import SubcallHandler, create_namespace, run_cell, snapshot_reserved

REPL_SOCK = "/ipc/repl.sock"
LM_SOCK = "/ipc/lm.sock"
WORKSPACE = Path("/workspace")


class RpcHandler(SubcallHandler):
    def _call(self, payload: dict) -> object:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(LM_SOCK)
        try:
            write_msg(sock, payload)
            resp = read_msg(sock)
        finally:
            sock.close()
        if resp.get("type") == "error":
            return f"Error: {resp.get('message')}"
        return resp.get("value")

    def llm_query(self, prompt: str, model: str | None = None) -> str:
        return str(self._call({"type": "llm_query", "prompt": prompt, "model": model}))

    def llm_query_batched(self, prompts: list[str], model: str | None = None) -> list[str]:
        value = self._call({"type": "llm_query_batched", "prompts": prompts, "model": model})
        if isinstance(value, list):
            return [str(x) for x in value]
        return [str(value)]

    def rlm_query(self, prompt: str, model: str | None = None) -> str:
        return str(self._call({"type": "rlm_query", "prompt": prompt, "model": model}))

    def rlm_query_batched(self, prompts: list[str], model: str | None = None) -> list[str]:
        value = self._call({"type": "rlm_query_batched", "prompts": prompts, "model": model})
        if isinstance(value, list):
            return [str(x) for x in value]
        return [str(value)]


def bind_workspace(mode: str, query: str) -> dict:
    bindings: dict = {"query": query}
    context_file = WORKSPACE / "context.txt"
    if mode == "string" or context_file.is_file():
        if context_file.is_file():
            bindings["context"] = context_file.read_text(encoding="utf-8", errors="replace")
        else:
            bindings["context"] = ""
    if mode == "repo":
        bindings["repo"] = Repo(WORKSPACE)
        bindings["context"] = bindings.get("context", "")
    if mode == "research":
        corpus = Corpus(ingest_path(WORKSPACE))
        bindings["corpus"] = corpus
        bindings["catalog"] = [
            {"id": d.id, "title": d.title, "path": d.path, "n_chars": d.n_chars}
            for d in corpus.docs
        ]
        bindings["context"] = bindings.get("context", "")
    return bindings


def serve() -> None:
    path = Path(REPL_SOCK)
    if path.exists():
        path.unlink()
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(REPL_SOCK)
    os.chmod(REPL_SOCK, 0o777)
    srv.listen(1)
    conn, _ = srv.accept()
    ns = None
    reserved = None
    max_stdout = 4000
    cell_timeout = 60.0
    try:
        while True:
            msg = read_msg(conn)
            typ = msg.get("type")
            if typ == "init":
                max_stdout = int(msg.get("max_stdout_chars") or 4000)
                cell_timeout = float(msg.get("cell_timeout_s") or 60.0)
                mode = msg.get("mode") or "string"
                query = msg.get("query") or ""
                bindings = bind_workspace(mode, query)
                ns = create_namespace(bindings, RpcHandler(), max_stdout_chars=max_stdout)
                reserved = snapshot_reserved(ns)
                write_msg(conn, {"type": "ok"})
            elif typ == "exec":
                if ns is None or reserved is None:
                    write_msg(conn, {"type": "error", "message": "not initialized"})
                    continue
                obs = run_cell(
                    ns,
                    msg.get("code") or "",
                    reserved,
                    timeout_s=cell_timeout,
                    max_send_chars=max(max_stdout * 2, 8000),
                    use_alarm=True,
                )
                write_msg(
                    conn,
                    {
                        "type": "exec_result",
                        "stdout": obs.stdout,
                        "stderr": obs.stderr,
                        "total_stdout_len": obs.total_stdout_len,
                        "total_stderr_len": obs.total_stderr_len,
                        "sha256": obs.sha256,
                        "final": obs.final,
                        "error": obs.error,
                    },
                )
            elif typ == "shutdown":
                break
            else:
                write_msg(conn, {"type": "error", "message": f"unknown {typ}"})
    finally:
        try:
            conn.close()
        except OSError:
            pass
        srv.close()


if __name__ == "__main__":
    # Small delay so the host can finish chmod on /ipc
    time.sleep(0.05)
    try:
        serve()
    except Exception as e:
        sys.stderr.write(f"repl_server fatal: {e}\n")
        raise
