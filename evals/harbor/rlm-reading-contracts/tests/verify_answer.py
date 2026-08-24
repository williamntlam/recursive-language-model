"""Verifier-only checks for the RLM source-grounding task."""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ANSWER = Path(os.environ.get("HARBOR_ANSWER_PATH", "/workspace/answer.md"))


def fail(message: str) -> None:
    print(f"FAIL: {message}", file=sys.stderr)
    raise SystemExit(1)


if not ANSWER.is_file():
    fail("/workspace/answer.md is missing")

answer = ANSWER.read_text(encoding="utf-8").lower()
if len(answer.strip()) < 180:
    fail("answer is too short to explain the requested contracts")

required_citations = {
    "rlm/core/history.py": r"rlm/core/history\.py:\d+(?:-\d+)?",
    "rlm/core/prompt_guard.py": r"rlm/core/prompt_guard\.py:\d+(?:-\d+)?",
    "rlm/config.py": r"rlm/config\.py:\d+(?:-\d+)?",
}
for path, pattern in required_citations.items():
    if not re.search(pattern, answer):
        fail(f"missing a citation to {path}")

if not all(term in answer for term in ("bound", "context", "history")):
    fail("answer does not explain why bound context stays out of history")
if not any(term in answer for term in ("compact", "stub", "recent")):
    fail("answer does not explain history compaction")
if "150" not in answer or "instruction" not in answer:
    fail("answer does not state the instruction ceiling")
if "99,999" not in answer and "99999" not in answer:
    fail("answer does not state the maximum permitted prompt-token count")
if not ("100,000" in answer or "100000" in answer) or not any(
    term in answer for term in ("not", "cannot", "illegal", "reject")
):
    fail("answer does not state that 100,000 prompt tokens cannot be sent")

print("PASS: source-grounded reading answer verified")
