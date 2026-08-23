---
name: evaluation
description: Add or modify RLM LLM-as-judge evaluations, rubrics, cases, or long-context benchmarks while keeping model cost opt-in and source data bounded.
---

# Evaluation

Use this skill for work under `evals/`, including judge prompts, case data,
result formats, and benchmark documentation.

## Why it matters

RLM is valuable only if it provides grounded answers efficiently on work that
would otherwise exceed a normal context window. Evals must measure that product
claim without quietly turning normal tests into paid model calls or placing a
large source/context dump in the judge prompt.

Read [`references/eval-contracts.md`](references/eval-contracts.md) before
changing a live evaluation. Load `../testing/SKILL.md` for local validation.

Keep cases versioned and declarative. Prefer deterministic construction and
checks for facts that code can verify; use an LLM judge for bounded semantic
assessment with an explicit rubric. Do not run a live RLM or judge call unless
the task explicitly requests it.
