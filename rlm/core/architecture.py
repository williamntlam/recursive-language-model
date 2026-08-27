"""Selectable, bounded execution architectures for repository and corpus research."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from rlm.core.planner import ResearchPlan, planner_messages
from rlm.core.prompt_guard import count_tokens
from rlm.domains.scope import ScopeManifest, ScopeRecord, scope_slice

if TYPE_CHECKING:
    from rlm.logging.trajectory import TrajectoryLogger


@dataclass(frozen=True)
class PreparedArchitecture:
    """The source-free plan and deterministic fallback boundary for one run."""

    scope: ScopeManifest | None = None
    plan: ResearchPlan | None = None
    fallback_targets: tuple[dict[str, Any], ...] = ()
    planned_waves: tuple[tuple[ResearchPlan, ScopeManifest], ...] = ()


class ResearchArchitecture(Protocol):
    """Prepare bounded work without exposing source text to a planner."""

    name: str

    def prepare(
        self,
        query: str,
        domain: Any,
        logger: TrajectoryLogger,
        *,
        build_scope: Callable[[Any, str], ScopeManifest],
        plan_scope: Callable[[str, ScopeManifest, TrajectoryLogger], ResearchPlan | None],
        planner_shard_target_tokens: int = 12_000,
    ) -> PreparedArchitecture: ...


class DirectArchitecture:
    """Existing REPL-led architecture; no planning call or preselected scope."""

    name = "direct"

    def prepare(
        self,
        query: str,
        domain: Any,
        logger: TrajectoryLogger,
        *,
        build_scope: Callable[[Any, str], ScopeManifest],  # noqa: ARG002
        plan_scope: Callable[[str, ScopeManifest, TrajectoryLogger], ResearchPlan | None],  # noqa: ARG002
        planner_shard_target_tokens: int = 12_000,  # noqa: ARG002
    ) -> PreparedArchitecture:
        return PreparedArchitecture()


class PlannedArchitecture:
    """Deterministic source-free scope plus one validated constrained plan."""

    name = "planned"

    def prepare(
        self,
        query: str,
        domain: Any,
        logger: TrajectoryLogger,
        *,
        build_scope: Callable[[Any, str], ScopeManifest],
        plan_scope: Callable[[str, ScopeManifest, TrajectoryLogger], ResearchPlan | None],
        planner_shard_target_tokens: int = 12_000,  # noqa: ARG002
    ) -> PreparedArchitecture:
        scope = build_scope(domain, query)
        plan = plan_scope(query, scope, logger)
        # A rejected plan never reopens the original domain. The normal runtime
        # instead receives a view restricted to deterministic manifest targets.
        fallback_targets = (
            tuple(dict(record.target) for record in scope.records)
            if plan is None and scope.records
            else ()
        )
        return PreparedArchitecture(scope=scope, plan=plan, fallback_targets=fallback_targets)


class PlannedWavesArchitecture:
    """Complete local census, token-safe planner shards, and explicit coverage."""

    name = "planned_waves"

    def prepare(
        self,
        query: str,
        domain: Any,
        logger: TrajectoryLogger,
        *,
        build_scope: Callable[[Any, str], ScopeManifest],
        plan_scope: Callable[[str, ScopeManifest, TrajectoryLogger], ResearchPlan | None],
        planner_shard_target_tokens: int = 12_000,
    ) -> PreparedArchitecture:
        census = build_scope(domain, query)
        artifacts = logger.dir / "artifacts"
        artifacts.mkdir(exist_ok=True)
        (artifacts / "census.jsonl").write_text(
            "".join(
                __import__("json").dumps(r.public_dict(), sort_keys=True) + "\n"
                for r in census.records
            ),
            encoding="utf-8",
        )
        (artifacts / "census-summary.json").write_text(
            __import__("json").dumps(census.to_dict(), sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        shards = self._shards(query, census, planner_shard_target_tokens)
        plans: list[tuple[ResearchPlan, ScopeManifest]] = []
        coverage: list[dict[str, Any]] = []
        shard_lines: list[dict[str, Any]] = []
        for ordinal, shard in enumerate(shards, start=1):
            plan = plan_scope(query, shard, logger)
            selected = set() if plan is None else {item.record_id for item in plan.selected}
            shard_lines.append(
                {
                    "ordinal": ordinal,
                    "digest": shard.digest,
                    "record_ids": [r.id for r in shard.records],
                    "status": "accepted" if plan else "unplannable",
                }
            )
            for record in shard.records:
                coverage.append(
                    {
                        "record_id": record.id,
                        "planner_shard": ordinal,
                        "status": "selected"
                        if record.id in selected
                        else ("unplannable" if plan is None else "not_selected"),
                    }
                )
            if plan is not None:
                plans.append((plan, shard))
        (artifacts / "planner-shards.jsonl").write_text(
            "".join(__import__("json").dumps(x, sort_keys=True) + "\n" for x in shard_lines),
            encoding="utf-8",
        )
        (artifacts / "coverage.jsonl").write_text(
            "".join(__import__("json").dumps(x, sort_keys=True) + "\n" for x in coverage),
            encoding="utf-8",
        )
        logger.event(
            kind="planned_waves_census",
            record_count=len(census.records),
            shard_count=len(shards),
            census_digest=census.digest,
        )
        return PreparedArchitecture(scope=census, planned_waves=tuple(plans))

    @staticmethod
    def _shards(query: str, census: ScopeManifest, target_tokens: int) -> list[ScopeManifest]:
        result: list[ScopeManifest] = []
        pending: list[ScopeRecord] = []
        for record in census.records:
            candidate = pending + [record]
            shard = scope_slice(census, candidate)
            if pending and count_tokens(planner_messages(query, shard, {})) > target_tokens:
                result.append(scope_slice(census, pending))
                pending = [record]
            else:
                pending = candidate
        if pending:
            result.append(scope_slice(census, pending))
        return result


_ARCHITECTURES: dict[str, ResearchArchitecture] = {
    DirectArchitecture.name: DirectArchitecture(),
    PlannedArchitecture.name: PlannedArchitecture(),
    PlannedWavesArchitecture.name: PlannedWavesArchitecture(),
}


def architecture_names() -> tuple[str, ...]:
    return tuple(_ARCHITECTURES)


def get_architecture(name: str) -> ResearchArchitecture:
    try:
        return _ARCHITECTURES[name]
    except KeyError as exc:
        choices = ", ".join(architecture_names())
        raise ValueError(f"Unknown architecture {name!r}; choose one of: {choices}") from exc
