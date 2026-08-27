"""Opt-in live comparison of direct and planned RLM architectures.

This is intentionally not named ``test_*.py``: it can require Docker and make
model calls. Pytest covers its deterministic case/metric helpers separately.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from rlm import RLM

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CASES = ROOT / "tests" / "architecture_benchmark_cases.json"
SCHEMA_VERSION = 1
_CITATION = re.compile(
    r"(?P<path>[A-Za-z0-9_.\-/]+\.[A-Za-z0-9_+-]+):(?P<start>\d+)(?:-(?P<end>\d+))?"
)


@dataclass(frozen=True)
class Case:
    id: str
    band: str
    evidence_tokens: str
    query: str


def load_cases(path: Path = DEFAULT_CASES) -> dict[str, Case]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("version") != 1 or not isinstance(raw.get("cases"), list):
        raise ValueError("benchmark cases must have version=1 and a cases list")
    cases: dict[str, Case] = {}
    for item in raw["cases"]:
        if not isinstance(item, dict) or set(item) != {"id", "band", "evidence_tokens", "query"}:
            raise ValueError("each benchmark case has an invalid schema")
        case = Case(**item)
        if case.band not in {"small", "medium", "large"} or not case.query.strip():
            raise ValueError(f"invalid benchmark case: {case.id!r}")
        if case.id in cases:
            raise ValueError(f"duplicate benchmark case: {case.id}")
        cases[case.id] = case
    return cases


def _events(path: Path) -> list[dict[str, Any]]:
    events_path = path / "events.jsonl"
    if not events_path.is_file():
        return []
    return [
        json.loads(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line
    ]


def citation_metrics(answer: str, target: Path) -> dict[str, int]:
    """Count syntactically cited, in-target line ranges without judging semantics."""
    root = target.resolve()
    total = valid = 0
    for match in _CITATION.finditer(answer):
        total += 1
        start, end = int(match["start"]), int(match["end"] or match["start"])
        if start < 1 or end < start:
            continue
        try:
            path = (root / match["path"]).resolve()
            path.relative_to(root)
        except ValueError:
            continue
        if not path.is_file():
            continue
        if start <= len(path.read_text(encoding="utf-8", errors="replace").splitlines()):
            valid += 1
    return {"citations_total": total, "citations_valid": valid}


def summarize_run(completion, target: Path, variant: str) -> dict[str, Any]:
    events = _events(completion.trajectory)
    planner = next((event for event in events if event.get("kind") == "planner"), None)
    scope = next((event for event in events if event.get("kind") == "scope_manifest"), None)
    execution = next((event for event in events if event.get("kind") == "plan_execution"), None)
    metrics: dict[str, Any] = {
        "variant": variant,
        "trajectory": str(completion.trajectory),
        "usage": asdict(completion.usage),
        "root_turns": sum(event.get("kind") == "root_lm" for event in events),
        "repl_cells": sum(event.get("kind") == "repl" for event in events),
        "planner_accepted": bool(planner and not planner.get("fallback")),
        "planner_fallback": bool(planner and planner.get("fallback")),
        "manifest_records": None if scope is None else scope.get("record_count"),
        "manifest_truncated": None if scope is None else scope.get("truncated"),
        "selected_records": None if planner is None else planner.get("selected_count"),
        "planned_leaf_calls": None if execution is None else execution.get("leaf_count"),
        "planned_child_calls": None if execution is None else execution.get("child_count"),
        "answer_n_chars": len(completion.response),
        "answer_sha256": hashlib.sha256(completion.response.encode()).hexdigest(),
        **citation_metrics(completion.response, target),
    }
    return metrics


def run_trial(
    *, target: Path, domain: str, query: str, variant: str, log_dir: Path
) -> dict[str, Any]:
    planner_enabled = variant == "planned"
    rlm = RLM(log_dir=str(log_dir), planner_enabled=planner_enabled)
    completion = rlm.ask_repo(target, query) if domain == "repo" else rlm.research(target, query)
    return summarize_run(completion, target, variant)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True, help="Local repo or corpus directory")
    parser.add_argument("--domain", choices=("repo", "corpus"), default="repo")
    parser.add_argument("--case", action="append", help="Case ID; repeatable. Default: all cases")
    parser.add_argument("--query", help="Override the selected case query (requires one --case)")
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument(
        "--output", type=Path, default=ROOT / "evals/results/architecture-benchmark.json"
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.attempts < 1:
        raise SystemExit("--attempts must be >= 1")
    target = args.target.resolve()
    if not target.exists():
        raise SystemExit(f"Target does not exist: {target}")
    cases = load_cases()
    selected_ids = args.case or list(cases)
    try:
        selected = [cases[case_id] for case_id in selected_ids]
    except KeyError as exc:
        raise SystemExit(f"Unknown case: {exc.args[0]}") from exc
    if args.query and len(selected) != 1:
        raise SystemExit("--query requires exactly one --case")

    trials: list[dict[str, Any]] = []
    for case in selected:
        query = args.query or case.query
        for attempt in range(1, args.attempts + 1):
            for variant in ("direct", "planned"):
                try:
                    metrics = run_trial(
                        target=target,
                        domain=args.domain,
                        query=query,
                        variant=variant,
                        log_dir=ROOT / ".rlm/evals/architecture" / case.id / variant,
                    )
                    trials.append({"case_id": case.id, "attempt": attempt, **metrics})
                    print(
                        json.dumps({"case": case.id, "attempt": attempt, **metrics}, sort_keys=True)
                    )
                except Exception as exc:
                    trials.append(
                        {
                            "case_id": case.id,
                            "attempt": attempt,
                            "variant": variant,
                            "error_type": type(exc).__name__,
                            "error": str(exc),
                        }
                    )
                    print(json.dumps(trials[-1], sort_keys=True))
    result = {
        "schema_version": SCHEMA_VERSION,
        "timestamp": datetime.now(UTC).isoformat(),
        "target": str(target),
        "domain": args.domain,
        "cases": [asdict(case) for case in selected],
        "attempts": args.attempts,
        "trials": trials,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
