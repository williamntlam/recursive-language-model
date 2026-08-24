# Changelog

All notable repository changes are recorded here. Update the **Unreleased**
section before every GitHub push that changes this repository. Prefix every
entry with its local date, time, and timezone so the change timing is clear.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
using the categories Added, Changed, Deprecated, Removed, Fixed, and Security.

## [Unreleased]

### Added

- **2026-08-24 17:14 EDT** — A Harbor-compatible, read-only source-grounding task dataset at
  `evals/harbor/`, including the `rlm-reading-contracts` task.
- **2026-08-24 17:14 EDT** — Frozen `lite` and `full` Harbor suite manifests plus deterministic task and
  verifier capability tests.
- **2026-08-24 17:14 EDT** — Reference specification 003 for the Harbor read-only evaluation workflow.

### Changed

- **2026-08-24 17:14 EDT** — Documented Harbor tasks as the supported agent-benchmark entry point.
- **2026-08-24 17:14 EDT** — Reclassified the existing Python LLM-judge scripts as opt-in development
  utilities rather than the reported Harbor benchmark interface.
- **2026-08-24 17:14 EDT** — Updated the evaluation skill and evaluation-contract reference with the
  Harbor task, repeat-trial, suite-manifest, and deterministic-verifier rules.
- **2026-08-24 17:14 EDT** — Established timestamped changelog entries for future repository changes.
