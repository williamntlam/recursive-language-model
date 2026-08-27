---
name: observability
description: Change trajectory logging, report generation, or runtime error reporting while preserving useful diagnostics and safe HTML output.
---

# Observability

Use this skill for `rlm/logging/`, report CLI behavior, or errors surfaced to
users.

## Why it matters

RLM's research outputs need to be inspectable when users decide whether to
trust or act on them. Trajectories provide operational evidence without
reintroducing the full source corpus into a model transcript or report.

Inspect the adjacent logger/report code and `tests/integration/test_report.py` first. Read
[`references/trajectory-contract.md`](references/trajectory-contract.md) only
if changing log schema, retention, or HTML rendering. Load `../testing/SKILL.md`
for validation.
