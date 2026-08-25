"""Versioned, local execution traces for RLM trajectories.

The trace deliberately records causal metadata rather than prompts, source
text, callback payloads, or REPL memory.  It is JSONL so evaluators can stream
it after an interrupted run.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from collections import Counter
from pathlib import Path
from typing import Any

TRACE_SCHEMA_VERSION = 1
TERMINAL_STATUSES = frozenset({"ok", "error", "cancelled", "blocked"})


def digest(value: str | bytes) -> str:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(raw).hexdigest()


def safe_error(error: BaseException | str) -> dict[str, str]:
    """Classify an error without retaining possibly sensitive exception text."""
    if isinstance(error, BaseException):
        return {"type": type(error).__name__, "digest": digest(str(error))}
    return {"type": "Error", "digest": digest(str(error))}


class TraceWriter:
    """Append-only trace writer with a total per-run event order."""

    def __init__(self, directory: str | Path, trace_id: str | None = None) -> None:
        self.path = Path(directory) / "trace.jsonl"
        self.trace_id = trace_id or uuid.uuid4().hex
        self._lock = threading.Lock()
        self._seq = 0

    def _write(self, record: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._seq += 1
            full = {
                "schema_version": TRACE_SCHEMA_VERSION,
                "trace_id": self.trace_id,
                "seq": self._seq,
                "ts_unix_ms": int(time.time() * 1000),
                **record,
            }
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(full, sort_keys=True, ensure_ascii=False, default=str) + "\n")
                f.flush()
            return full

    def start(
        self, name: str, kind: str, *, parent_span_id: str | None, depth: int, **fields: Any
    ) -> str:
        span_id = uuid.uuid4().hex
        self._write(
            {
                "event": "span_start",
                "span_id": span_id,
                "parent_span_id": parent_span_id,
                "name": name,
                "kind": kind,
                "depth": depth,
                **fields,
            }
        )
        return span_id

    def end(
        self,
        span_id: str,
        name: str,
        kind: str,
        *,
        depth: int,
        status: str,
        started: float,
        **fields: Any,
    ) -> None:
        if status not in TERMINAL_STATUSES:
            status = "error"
        self._write(
            {
                "event": "span_end",
                "span_id": span_id,
                "parent_span_id": None,
                "name": name,
                "kind": kind,
                "depth": depth,
                "status": status,
                "duration_ms": max(0, round((time.perf_counter() - started) * 1000)),
                **fields,
            }
        )

    def event(
        self, name: str, kind: str, *, parent_span_id: str | None, depth: int, **fields: Any
    ) -> None:
        self._write(
            {
                "event": "span_event",
                "span_id": uuid.uuid4().hex,
                "parent_span_id": parent_span_id,
                "name": name,
                "kind": kind,
                "depth": depth,
                **fields,
            }
        )


def read_trace(path: str | Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            item = json.loads(line)
            if isinstance(item, dict):
                records.append(item)
    return records


def validate_trace(records: list[dict[str, Any]]) -> list[str]:
    """Return structural errors; an unfinished start is valid interruption data."""
    errors: list[str] = []
    starts: dict[str, dict[str, Any]] = {}
    seqs: set[int] = set()
    for record in records:
        required = {
            "schema_version",
            "trace_id",
            "span_id",
            "event",
            "seq",
            "ts_unix_ms",
            "depth",
            "name",
            "kind",
        }
        missing = sorted(required - set(record))
        if missing:
            errors.append("missing fields: " + ", ".join(missing))
            continue
        seq = record["seq"]
        if not isinstance(seq, int) or seq in seqs:
            errors.append(f"duplicate or invalid sequence: {seq!r}")
        seqs.add(seq)
        if record["event"] == "span_start":
            starts[record["span_id"]] = record
            parent = record.get("parent_span_id")
            if parent is not None and parent not in starts:
                errors.append(f"orphaned span: {record['span_id']}")
        elif record["event"] == "span_end":
            if record["span_id"] not in starts:
                errors.append(f"end without start: {record['span_id']}")
            if record.get("status") not in TERMINAL_STATUSES:
                errors.append(f"invalid end status: {record.get('status')!r}")
    return errors


def summarize(records: list[dict[str, Any]], *, complete: bool | None = None) -> dict[str, Any]:
    errors = validate_trace(records)
    starts = [r for r in records if r.get("event") == "span_start"]
    ends = [r for r in records if r.get("event") == "span_end"]
    counts = Counter(f"{r.get('kind')}:{r.get('name')}" for r in starts)
    statuses = Counter(str(r.get("status")) for r in ends)
    token_in = sum(int(r.get("input_tokens") or 0) for r in ends)
    token_out = sum(int(r.get("output_tokens") or 0) for r in ends)
    costs = [r.get("cost_usd") for r in ends if isinstance(r.get("cost_usd"), (int, float))]
    tools = Counter(str(r.get("name")) for r in starts if r.get("kind") == "tool")
    return {
        "schema_version": TRACE_SCHEMA_VERSION,
        "trace_id": records[0].get("trace_id") if records else None,
        "valid": not errors,
        "validation_errors": errors,
        "completion_status": "complete" if complete else "partial",
        "counts_by_operation": dict(sorted(counts.items())),
        "counts_by_status": dict(sorted(statuses.items())),
        "root_turns": sum(r.get("name") == "root.complete" for r in starts),
        "cells": sum(r.get("kind") == "repl" for r in starts),
        "leaf_calls": sum(r.get("name") == "leaf.complete" for r in starts),
        "child_calls": sum(r.get("name") == "rlm.run" and r.get("depth", 0) > 0 for r in starts),
        "batches": sum(r.get("kind") == "batch" for r in starts),
        "tool_calls": sum(tools.values()),
        "source_operations": dict(sorted(tools.items())),
        "max_recursion_depth": max((int(r.get("depth") or 0) for r in records), default=0),
        "prompt_tokens": token_in,
        "completion_tokens": token_out,
        "cost_usd": sum(costs) if costs else None,
    }


def index_runs(path: str | Path) -> list[dict[str, Any]]:
    """Return a compact deterministic index without opening content artifacts."""
    root = Path(path)
    candidates = (
        [root]
        if (root / "trace-summary.json").is_file()
        else sorted(
            p for p in root.iterdir() if p.is_dir() and (p / "trace-summary.json").is_file()
        )
    )
    rows: list[dict[str, Any]] = []
    for run in candidates:
        summary = json.loads((run / "trace-summary.json").read_text(encoding="utf-8"))
        meta_path = run / "meta.json"
        meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.is_file() else {}
        rows.append(
            {
                "run_id": meta.get("id", run.name),
                "trace_id": summary.get("trace_id"),
                "completion_status": summary.get("completion_status"),
                "valid": summary.get("valid"),
                "root_model": meta.get("root_model"),
                "leaf_model": meta.get("leaf_model"),
                "cost_usd": summary.get("cost_usd"),
                "prompt_tokens": summary.get("prompt_tokens"),
                "completion_tokens": summary.get("completion_tokens"),
                "max_recursion_depth": summary.get("max_recursion_depth"),
                "source_operations": summary.get("source_operations", {}),
            }
        )
    return rows
