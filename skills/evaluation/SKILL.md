---
name: evaluation
description: Add or modify RLM evaluations, including Harbor agent tasks, LLM-as-judge utilities, rubrics, cases, or long-context benchmarks while keeping model cost opt-in and source data bounded.
---

# Evaluation

Use this skill for work under `evals/`, including Harbor tasks, judge prompts,
case data, result formats, and benchmark documentation.

## Why it matters

RLM is valuable only if it provides grounded answers efficiently on work that
would otherwise exceed a normal context window. Evals must measure that product
claim without quietly turning normal tests into paid model calls or placing a
large source/context dump in the judge prompt. Harbor tasks additionally let us
measure an autonomous agent in a reproducible sandbox; they must preserve the
read-only product boundary when the task is source analysis.

Read [`references/eval-contracts.md`](references/eval-contracts.md) before
changing an evaluation. Load `../testing/SKILL.md` for local validation.

Keep cases versioned and declarative. Prefer deterministic construction and
checks for facts that code can verify; use an LLM judge for bounded semantic
assessment with an explicit rubric. Do not run a live RLM or judge call unless
the task explicitly requests it.

## Harbor tasks

`evals/harbor/` is the supported agent-benchmark entry point. A Harbor task
must contain at least:

```text
<task>/
├── task.toml
├── instruction.md
├── environment/Dockerfile
└── tests/test.sh
```

- Treat `instruction.md` as the complete, outcome-focused task prompt; do not
  leak verifier rules or ground truth into it.
- Put only agent-visible task inputs in `environment/`. For read-only source
  analysis, run a non-root agent and make the source tree root-owned and
  read-only; name the one writable answer artifact explicitly.
- Keep verifier-only assertions and ground truth under `tests/`. `test.sh` must
  write a numeric result to `/logs/verifier/reward.txt` for both success and
  failure.
- Do not add API keys, public-network dependencies, or paid judge calls to a
  deterministic Harbor task unless the user explicitly requests them.
- Maintain frozen `suites/lite.txt` and `suites/full.txt` manifests. Add new
  maintained tasks to full; add them to lite only when their iteration value
  warrants the cost.
- Report agent results from multiple attempts, with the task revision, agent
  adapter/version, model, attempt count, individual rewards, and aggregate.
- Keep fast deterministic verifier and task-layout tests in `tests/` with the
  `harbor` marker. Put deterministic legacy-judge/case/benchmark-helper tests
  in `tests/eval_support/` with the `eval_support` marker. Agent benchmarks are
  the integration layer, not a replacement for unit tests.

See [`../../evals/harbor/README.md`](../../evals/harbor/README.md) and
[`../../.spec/003-harbor-readonly-evaluations/spec.md`](../../.spec/003-harbor-readonly-evaluations/spec.md)
for the repository-specific workflow.
