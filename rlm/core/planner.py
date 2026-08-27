"""Untrusted JSON planner contract and deterministic resolution."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from rlm.domains.scope import ScopeManifest

PLAN_SCHEMA_VERSION = 1
PLAN_SCHEMA = {
    "version": 1,
    "selected": [
        {"record_id": "manifest id", "question": "inspection question", "route": "leaf|child"}
    ],
    "report_shape": "cited_markdown",
}


class PlanValidationError(ValueError):
    pass


@dataclass(frozen=True)
class PlannedSelection:
    record_id: str
    question: str
    route: str


@dataclass(frozen=True)
class ResearchPlan:
    version: int
    selected: tuple[PlannedSelection, ...]
    report_shape: str
    digest: str


def planner_messages(query: str, manifest: ScopeManifest, budget_summary: dict[str, Any]) -> list:
    from rlm.core.types import Message

    system = (
        "You are a constrained research planner. Return JSON only. "
        "Select only manifest record IDs; "
        "do not provide paths, code, spans, models, budgets, or nested plans. "
        f"Schema: {json.dumps(PLAN_SCHEMA, sort_keys=True)}"
    )
    content = json.dumps(
        {"question": query, "manifest": manifest.planner_dict(), "budget": budget_summary},
        sort_keys=True,
    )
    return [Message("system", system), Message("user", content)]


def planner_instruction_count(messages: list) -> int:
    """Count planner directives using the same guard as regular root turns."""
    from rlm.core.prompt_guard import count_instructions
    from rlm.core.types import PromptPayload

    return count_instructions(PromptPayload(system_prompt=messages[0].content, user_query="plan"))


def parse_plan(
    raw: str,
    manifest: ScopeManifest,
    *,
    max_selected: int = 16,
    max_leaf_calls: int = 16,
    max_child_calls: int = 8,
) -> ResearchPlan:
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise PlanValidationError("planner response is not valid JSON") from exc
    if not isinstance(value, dict) or set(value) != {"version", "selected", "report_shape"}:
        raise PlanValidationError(
            "planner response must contain only version, selected, and report_shape"
        )
    if value["version"] != PLAN_SCHEMA_VERSION or not isinstance(value["report_shape"], str):
        raise PlanValidationError("unsupported planner schema version or report shape")
    selected = value["selected"]
    if not isinstance(selected, list) or not selected or len(selected) > max_selected:
        raise PlanValidationError("planner selection count exceeds configured limit")
    allowed = {record.id: record for record in manifest.records}
    seen: set[str] = set()
    result: list[PlannedSelection] = []
    leaf = child = 0
    for item in selected:
        if not isinstance(item, dict) or set(item) != {"record_id", "question", "route"}:
            raise PlanValidationError("each planner selection has an invalid schema")
        record_id, question, route = item.get("record_id"), item.get("question"), item.get("route")
        if not isinstance(record_id, str) or record_id not in allowed or record_id in seen:
            raise PlanValidationError("planner selected an unknown or duplicate record")
        if not isinstance(question, str) or not question.strip() or len(question) > 1_000:
            raise PlanValidationError("planner selection question is invalid")
        if route not in {"leaf", "child"}:
            raise PlanValidationError("planner selection route is invalid")
        record = allowed[record_id]
        if route == "child" and record.route == "fit":
            raise PlanValidationError("fit records cannot request a child")
        if route == "leaf" and record.route == "child":
            raise PlanValidationError("oversized records must be routed to a child")
        leaf += route == "leaf"
        child += route == "child"
        seen.add(record_id)
        result.append(PlannedSelection(record_id, question, route))
    if leaf > max_leaf_calls or child > max_child_calls:
        raise PlanValidationError("planner route count exceeds configured limit")
    canonical = json.dumps(value, sort_keys=True, separators=(",", ":"))
    return ResearchPlan(
        PLAN_SCHEMA_VERSION,
        tuple(result),
        value["report_shape"],
        hashlib.sha256(canonical.encode()).hexdigest(),
    )


def resolve_targets(plan: ResearchPlan, manifest: ScopeManifest) -> list[dict[str, Any]]:
    by_id = {record.id: record for record in manifest.records}
    return [dict(by_id[item.record_id].target) for item in plan.selected]
