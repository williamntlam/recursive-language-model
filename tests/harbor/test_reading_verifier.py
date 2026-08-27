"""Fast deterministic contracts for the read-only Harbor task verifier."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.harbor

ROOT = Path(__file__).resolve().parents[2]
VERIFIER = ROOT / "evals/harbor/rlm-reading-contracts/tests/verify_answer.py"


def run_verifier(answer: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "HARBOR_ANSWER_PATH": str(answer)}
    return subprocess.run(
        [sys.executable, str(VERIFIER)], text=True, capture_output=True, env=env, check=False
    )


def test_reading_verifier_accepts_a_cited_contract_explanation(tmp_path):
    answer = tmp_path / "answer.md"
    answer.write_text(
        """The bound source context must remain outside parent history: copying it into a
conversation would defeat the bounded-context design. Older observations are compacted into
stubs while recent work remains available (rlm/core/history.py:8-9, rlm/core/history.py:18-35).

Every send is guarded by a 150 instruction ceiling (rlm/config.py:4,
rlm/core/prompt_guard.py:10-11). The maximum permitted prompt is 99,999 tokens
(rlm/config.py:3); 100,000 is illegal and cannot be sent because the guard rejects
prompt counts at or above that exclusive limit (rlm/core/prompt_guard.py:12-15).
""",
        encoding="utf-8",
    )

    result = run_verifier(answer)

    assert result.returncode == 0, result.stderr


def test_reading_verifier_rejects_an_uncited_answer(tmp_path):
    answer = tmp_path / "answer.md"
    answer.write_text(
        "Bound context should not enter history. History is compact and recent observations are "
        "kept. There are 150 instructions and 99,999 prompt tokens; 100,000 is not allowed. "
        "This statement is intentionally long enough to be a plausible but uncited answer. " * 2,
        encoding="utf-8",
    )

    result = run_verifier(answer)

    assert result.returncode == 1
    assert "citation" in result.stderr
