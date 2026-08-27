---
name: runtime-development
description: Change RLM runtime behavior, repository or corpus domains, backends, or the Python API while preserving data isolation and budget behavior.
---

# Runtime development

Use this skill for functional changes under `rlm/core/`, `rlm/domains/`,
`rlm/backends/`, or `rlm/api.py`.

## Why it matters

Runtime design separates cheap, deterministic inspection from model judgment,
and keeps large source material out of the parent context. That separation is
the product's answer to context rot, escalating inference cost, and unsupported
claims about an unfamiliar codebase.

Inspect the closest implementation and focused test first. Read
[`references/runtime-architecture.md`](references/runtime-architecture.md)
only when a change crosses those module boundaries or changes recursion,
budgets, or data binding. Load `../testing/SKILL.md` for validation details.

Preserve data locality: source bytes stay in the REPL/container, while model
calls receive only metadata or a narrow slice. Prefer Python analysis over a
model call when it can determine the answer.

For planner-enabled work, treat the scope manifest as the admission boundary:
the planner may select only IDs, while runtime code resolves targets and
executes their fixed leaf/child route. Keep final rendering source-free (only
compact findings), and make failed planning fall back to a manifest-restricted
view rather than an unrestricted domain.
