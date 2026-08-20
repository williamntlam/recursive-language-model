"""Inspectable trajectories: meta.json, events.jsonl, answer.txt, usage.json."""

from __future__ import annotations

import json
import re
import time
import uuid
from pathlib import Path
from typing import Any

from rlm.core.types import Usage

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
        meta = {
            "id": run_id,
            "query_sha256": extra_meta.get("query_sha256"),
            "query_n_chars": len(query),
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
