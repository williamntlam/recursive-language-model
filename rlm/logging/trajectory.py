"""Inspectable trajectories: meta.json, events.jsonl, answer.txt, usage.json, error.txt."""

from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

from rlm.core.types import Usage
from rlm.logging.trace import TRACE_SCHEMA_VERSION, TraceWriter, read_trace, summarize

_SECRET = re.compile(r"sk-[A-Za-z0-9_\-]{8,}")


def redact(text: str) -> str:
    return _SECRET.sub("sk-REDACTED", text)


def _safe(obj: Any) -> Any:
    if isinstance(obj, str):
        return redact(obj)
    if isinstance(obj, dict):
        return {str(k): _safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_safe(v) for v in obj]
    if isinstance(obj, (int, float, bool)) or obj is None:
        return obj
    return redact(str(obj))


class TrajectoryLogger:
    def __init__(self, log_dir: str | Path, *, query: str, extra_meta: dict[str, Any]) -> None:
        ts = time.strftime("%Y%m%d-%H%M%S")
        run_id = f"{ts}-{uuid.uuid4().hex[:8]}"
        self.dir = Path(log_dir) / run_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.events_path = self.dir / "events.jsonl"
        self.error_path = self.dir / "error.txt"
        # With the default ``.rlm/logs``, this is ``.rlm/repl_errors.jsonl``.
        self.repl_errors_path = self.dir.parent.parent / "repl_errors.jsonl"
        self.trace = TraceWriter(self.dir)
        self.trace_capture = str(extra_meta.get("trace_capture") or "metadata")
        self._artifact_bytes = 0
        self._artifact_limit = 2_000_000
        self._artifact_item_limit = 200_000
        self.root_started = time.perf_counter()
        self.root_span_id = self.trace.start("rlm.run", "run", parent_span_id=None, depth=0)
        meta = {
            "id": run_id,
            "query_sha256": extra_meta.get("query_sha256"),
            "query_n_chars": len(query),
            "trace_schema_version": TRACE_SCHEMA_VERSION,
            "trace_id": self.trace.trace_id,
            "trace_capture": self.trace_capture,
            **{k: v for k, v in extra_meta.items() if k != "query"},
        }
        (self.dir / "meta.json").write_text(
            json.dumps(_safe(meta), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    def event(self, **record: Any) -> None:
        line = json.dumps(_safe(record), ensure_ascii=False, default=str)
        with self.events_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
        try:
            self._maybe_record_event_error(record)
        except OSError:
            pass

    def capture_content(self, kind: str, text: str) -> str | None:
        """Store an opt-in local artifact and return its opaque reference."""
        if self.trace_capture != "content":
            return None
        raw = redact(text)
        encoded = raw.encode("utf-8")
        truncated = len(encoded) > self._artifact_item_limit
        if truncated:
            encoded = encoded[: self._artifact_item_limit]
        if self._artifact_bytes + len(encoded) > self._artifact_limit:
            return None
        digest = __import__("hashlib").sha256(encoded).hexdigest()
        artifacts = self.dir / "artifacts"
        artifacts.mkdir(exist_ok=True)
        path = artifacts / f"{digest}.txt"
        if not path.exists():
            path.write_bytes(encoded)
        self._artifact_bytes += len(encoded)
        manifest_path = artifacts / "manifest.json"
        manifest: dict[str, Any] = {}
        if manifest_path.exists():
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                manifest = {}
        manifest[digest] = {
            "kind": kind,
            "byte_length": len(encoded),
            "sha256": digest,
            "truncated": truncated,
            "redacted": raw != text,
        }
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return f"artifacts/{digest}.txt"

    def record_stderr(
        self,
        text: str,
        *,
        iteration: int | None = None,
        depth: int | None = None,
        kind: str = "repl",
        code: str | None = None,
    ) -> None:
        """Append stderr (or an abort/parse error) to error.txt. No-op if empty."""
        body = redact(text or "").rstrip()
        if not body:
            return
        bits = [f"=== {kind}"]
        if iteration is not None:
            bits.append(f"iteration={iteration}")
        if depth is not None:
            bits.append(f"depth={depth}")
        chunk = " ".join(bits) + " ===\n"
        if code:
            chunk += "code:\n" + redact(str(code)).rstrip() + "\n\n"
        chunk += body + "\n\n"
        with self.error_path.open("a", encoding="utf-8") as f:
            f.write(chunk)

    def record_repl_error(
        self,
        text: str,
        *,
        stage: str,
        iteration: int | None = None,
        depth: int | None = None,
        error_type: str | None = None,
        code: str | None = None,
    ) -> None:
        """Append a bounded, redacted REPL failure to the cross-run index.

        The index deliberately excludes prompts, source, and raw REPL code;
        the owning run directory holds the fuller local diagnostic.
        """
        body = redact(text or "").strip()
        if not body:
            return
        record: dict[str, Any] = {
            "schema_version": 1,
            "ts_unix_ms": int(time.time() * 1000),
            "run_id": self.dir.name,
            "trajectory": str(self.dir),
            "stage": stage,
            "message": body[:4000],
            "message_truncated": len(body) > 4000,
        }
        if iteration is not None:
            record["iteration"] = iteration
        if depth is not None:
            record["depth"] = depth
        if error_type:
            record["error_type"] = error_type
        if code is not None:
            raw_code = str(code)
            record["code_sha256"] = (
                __import__("hashlib").sha256(raw_code.encode("utf-8")).hexdigest()
            )
            record["code_n_chars"] = len(raw_code)
        with self.repl_errors_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(_safe(record), ensure_ascii=False) + "\n")

    def _maybe_record_event_error(self, record: dict[str, Any]) -> None:
        kind = str(record.get("kind") or "")
        iteration = record.get("iteration")
        depth = record.get("depth")
        if kind == "repl":
            text = record.get("stderr") or record.get("error") or ""
            if text:
                self.record_stderr(
                    str(text),
                    iteration=iteration if isinstance(iteration, int) else None,
                    depth=depth if isinstance(depth, int) else None,
                    kind="repl",
                    code=None if record.get("code") is None else str(record.get("code")),
                )
            if record.get("error"):
                self.record_repl_error(
                    str(record["error"]),
                    stage="cell",
                    iteration=iteration if isinstance(iteration, int) else None,
                    depth=depth if isinstance(depth, int) else None,
                    error_type="ReplCellError",
                    code=None if record.get("code") is None else str(record.get("code")),
                )
            return
        if kind == "parse_error":
            preview = str(record.get("text_preview") or "").rstrip()
            msg = "parse_error: no executable code fence"
            if preview:
                msg += "\n" + preview
            self.record_stderr(
                msg,
                iteration=iteration if isinstance(iteration, int) else None,
                depth=depth if isinstance(depth, int) else None,
                kind="parse_error",
            )

    def finish(self, answer: str, usage: Usage, extra: dict[str, Any] | None = None) -> None:
        (self.dir / "answer.txt").write_text(redact(answer), encoding="utf-8")
        payload = {
            "prompt_tokens": usage.prompt_tokens,
            "completion_tokens": usage.completion_tokens,
            "cost_usd": usage.cost_usd,
            "iterations": usage.iterations,
            "subcalls": usage.subcalls,
            **(extra or {}),
        }
        (self.dir / "usage.json").write_text(
            json.dumps(_safe(payload), indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        self.trace.end(
            self.root_span_id,
            "rlm.run",
            "run",
            depth=0,
            status="ok",
            started=self.root_started,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.completion_tokens,
            cost_usd=usage.cost_usd,
        )
        self.write_trace_summary(complete=True)
        self.write_html()

    def abort_trace(self, error: BaseException, *, depth: int = 0) -> None:
        # Do not close the root span: a missing end is the durable interruption signal.
        self.trace.event(
            "run.abort",
            "runtime",
            parent_span_id=self.root_span_id,
            depth=depth,
            error_type=type(error).__name__,
        )
        self.write_trace_summary(complete=False)

    def write_trace_summary(self, *, complete: bool) -> None:
        try:
            payload = summarize(read_trace(self.trace.path), complete=complete)
            (self.dir / "trace-summary.json").write_text(
                json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
            )
        except (OSError, ValueError, json.JSONDecodeError):
            pass

    def write_html(self):
        from rlm.logging.html import write_report

        return write_report(self.dir)
