# Agent Guide

`recursive-language-model` is a Python 3.12+ package and CLI for read-only
recursive language-model workflows over repositories, corpora, and large
strings.

## Product context

This project exists to produce trustworthy, source-grounded answers from large
codebases and document collections without stuffing those sources into a model
context window. The source remains data in a constrained REPL; the parent model
uses code to inspect it and sees only compact findings. This avoids context rot,
reduces unnecessary model cost, and makes answers more auditable through paths,
spans, and trajectory logs.

It complements coding agents rather than replacing them: RLM is for a
read-only census or research pass that informs an implementation plan. Preserve
that distinction—do not turn its runtime into a general-purpose coding shell,
or trade groundedness and isolation for convenience.

## Progressive disclosure

Start with this file only. Load a matching skill below, then read only the
references that skill explicitly calls for. Do not preload `docs/`, all source
files, or every skill merely to orient yourself.

| Task | Load |
| --- | --- |
| Runtime, domain, backend, environment, or public API change | `skills/runtime-development/SKILL.md` |
| Prompt, prompt catalog, token guard, or history-policy change | `skills/prompt-safety/SKILL.md` |
| CLI or TOML/YAML configuration change | `skills/cli-and-config/SKILL.md` |
| Docker REPL image, namespace, or host-container boundary change | `skills/docker-repl/SKILL.md` |
| Add or modify an LLM-as-judge evaluation, rubric, case, or long-context benchmark | `skills/evaluation/SKILL.md` |
| Tests, regression diagnosis, or validation | `skills/testing/SKILL.md` |
| Trajectory reports, logging, or error presentation | `skills/observability/SKILL.md` |
| Review a change or design for unnecessary complexity, speculative abstraction, or premature extensibility | `skills/overengineering-check/SKILL.md` |
| Documentation or examples only | Inspect the relevant document directly. |

For an unfamiliar task, inspect the closest source file and focused test first;
load a skill only when its additional context becomes relevant.

## Always preserve

- Source data is read-only to the runtime; credentials remain on the host,
  outside the Docker container.
- Prompt token and instruction ceilings are behavioral contracts, not targets
  to raise for convenience.
- Prefer deterministic REPL/Python inspection over unnecessary model calls.
- Make focused changes and run proportional validation.

## Change log

Before every GitHub push that changes this repository, update
[`CHANGELOG.md`](CHANGELOG.md). Add a concise entry under **Unreleased** using
the relevant Keep a Changelog category and prefix it with the local
`YYYY-MM-DD HH:MM TZ` timestamp. Do not rewrite prior entries; move the
Unreleased entries into a dated/versioned section only when preparing a release.
The version-controlled [pre-push hook](.githooks/pre-push) enforces that the
outgoing commits include a `CHANGELOG.md` change.
