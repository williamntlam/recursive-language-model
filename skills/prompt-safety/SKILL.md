---
name: prompt-safety
description: Change root or leaf prompts, exposed-method catalogs, history handling, or prompt-budget enforcement without weakening anti-context-rot guarantees.
---

# Prompt safety

Use this skill for files in `rlm/prompts/`, `rlm/core/prompt_guard.py`, or
`rlm/core/history.py`, and for behavior that changes what reaches a model.

## Why it matters

The product's value depends on a parent model that reasons from compact,
observable findings rather than a growing transcript or copied source dump.
The token and instruction limits protect reliability as well as cost.

Read [`references/prompt-contracts.md`](references/prompt-contracts.md) before
changing limits, routing, or history. Inspect the narrow prompt or guard test
before editing; load `../testing/SKILL.md` to run it.

Keep generic prompts concise. New exposed REPL or domain methods affect the
instruction count and must be represented in the prompt catalog.
