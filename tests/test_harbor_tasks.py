"""Static contracts for the local Harbor read-only evaluation dataset."""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TASKS_ROOT = ROOT / "evals" / "harbor"


def task_dirs() -> list[Path]:
    return sorted(path for path in TASKS_ROOT.iterdir() if (path / "task.toml").is_file())


def test_harbor_reading_tasks_have_required_artifacts_and_shared_verifier():
    tasks = task_dirs()
    assert tasks
    for task in tasks:
        assert (task / "instruction.md").is_file()
        assert (task / "environment" / "Dockerfile").is_file()
        assert (task / "tests" / "test.sh").is_file()
        config = tomllib.loads((task / "task.toml").read_text(encoding="utf-8"))
        assert config["version"] == "1.0"
        assert config["verifier"]["environment_mode"] == "shared"


def test_harbor_reading_task_keeps_source_read_only_and_only_requests_an_answer():
    task = TASKS_ROOT / "rlm-reading-contracts"
    dockerfile = (task / "environment" / "Dockerfile").read_text(encoding="utf-8")
    instruction = (task / "instruction.md").read_text(encoding="utf-8")

    assert "chmod -R a-w /workspace/source" in dockerfile
    assert "USER agent" in dockerfile
    assert "Do not modify it." in instruction
    assert "/workspace/answer.md" in instruction


def test_harbor_verifier_writes_a_numeric_reward_without_installing_dependencies():
    test_script = (TASKS_ROOT / "rlm-reading-contracts" / "tests" / "test.sh").read_text(
        encoding="utf-8"
    )

    assert "/logs/verifier/reward.txt" in test_script
    assert "printf '1" in test_script
    assert "printf '0" in test_script
    assert "pip install" not in test_script
