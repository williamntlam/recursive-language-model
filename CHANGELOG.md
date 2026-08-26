# Changelog

All notable repository changes are recorded here. Update the **Unreleased**
section before every GitHub push that changes this repository. Prefix every
entry with its local date, time, and timezone so the change timing is clear.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
using the categories Added, Changed, Deprecated, Removed, Fixed, and Security.

## [Unreleased]

### Added

- **2026-08-26 18:52 EDT** — Centralized redacted REPL failure indexing at
  `.rlm/repl_errors.jsonl`, linking startup, execution, and cell errors back
  to their trajectories without retaining prompts, source content, or code.
- **2026-08-25 17:52 EDT** — Versioned causal execution traces with JSONL
  spans, deterministic summaries, evaluation indexing, safe capture profiles,
  and offline tree/graph reporting for runtime, REPL, callback, model, and
  source-tool activity.
- **2026-08-25 08:46 EDT** — An `overengineering-check` project skill for
  evidence-based review of unnecessary complexity and speculative abstraction.
- **2026-08-24 17:16 EDT** — A version-controlled pre-push hook that blocks
  outgoing commits without a `CHANGELOG.md` update.
- **2026-08-24 17:14 EDT** — A Harbor-compatible, read-only source-grounding task dataset at
  `evals/harbor/`, including the `rlm-reading-contracts` task.
- **2026-08-24 17:14 EDT** — Frozen `lite` and `full` Harbor suite manifests plus deterministic task and
  verifier capability tests.
- **2026-08-24 17:14 EDT** — Reference specification 003 for the Harbor read-only evaluation workflow.

### Changed

- **2026-08-25 17:56 EDT** — Made `plan_reads` reject unmeasured repository
  path dictionaries, clarified that path planning belongs to `repo.plan`, and
  documented safe handling of nullable AST source segments.
- **2026-08-25 08:50 EDT** — Extended the `overengineering-check` skill to
  review specifications and assess whether added complexity has a clear,
  current justification.
- **2026-08-24 17:17 EDT** — Updated the README and developer documentation for
  Harbor tasks, repeated trials, deterministic checks, and changelog hooks.
- **2026-08-24 17:14 EDT** — Documented Harbor tasks as the supported agent-benchmark entry point.
- **2026-08-24 17:14 EDT** — Reclassified the existing Python LLM-judge scripts as opt-in development
  utilities rather than the reported Harbor benchmark interface.
- **2026-08-24 17:14 EDT** — Updated the evaluation skill and evaluation-contract reference with the
  Harbor task, repeat-trial, suite-manifest, and deterministic-verifier rules.
- **2026-08-24 17:14 EDT** — Established timestamped changelog entries for future repository changes.
