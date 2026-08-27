"""Selectable, bounded execution architectures for repository and corpus research."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from rlm.core.planner import ResearchPlan
from rlm.domains.scope import ScopeManifest

if TYPE_CHECKING:
    from rlm.logging.trajectory import TrajectoryLogger


@dataclass(frozen=True)
class PreparedArchitecture:
    """The source-free plan and deterministic fallback boundary for one run."""

    scope: ScopeManifest | None = None
    plan: ResearchPlan | None = None
    fallback_targets: tuple[dict[str, Any], ...] = ()


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


_ARCHITECTURES: dict[str, ResearchArchitecture] = {
    DirectArchitecture.name: DirectArchitecture(),
    PlannedArchitecture.name: PlannedArchitecture(),
}


def architecture_names() -> tuple[str, ...]:
    return tuple(_ARCHITECTURES)


def get_architecture(name: str) -> ResearchArchitecture:
    try:
        return _ARCHITECTURES[name]
    except KeyError as exc:
        choices = ", ".join(architecture_names())
        raise ValueError(f"Unknown architecture {name!r}; choose one of: {choices}") from exc
