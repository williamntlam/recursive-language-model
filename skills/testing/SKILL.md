---
name: testing
description: Add, update, or diagnose pytest coverage for RLM behavior using focused fake environments and optional Docker integration tests.
---

# Testing

The important regressions here are silent contract failures: an oversized
prompt sent to a model, source data leaking into history, a path escaping its
workspace, or an error that destroys usable diagnostics. Test observable
invariants rather than a model's wording.

Run the smallest relevant module first, then the full suite for changes that
cross runtime boundaries:

```bash
uv run pytest tests/unit/test_<area>.py
uv run pytest tests/integration/test_<area>.py
# Fast RLM product contracts (excludes optional boundaries and eval tooling).
uv run pytest -m "not docker and not eval_support and not harbor"
uv run pytest
uv run ruff check rlm tests
```

For fake runtime tests, read [`references/fake-runtime.md`](references/fake-runtime.md).
Docker tests are separate and require a running daemon:

```bash
uv run pytest -m docker
```

Use `eval_support` for deterministic tests of opt-in judge, case, or benchmark
helpers; never make a live model call from pytest. Use `harbor` for deterministic
Harbor task-layout/verifier checks. Harbor runs themselves are repeated
autonomous-agent integration benchmarks, not pytest tests.

Test placement follows the behavior under test: focused deterministic contracts
go in `tests/unit/`; workflows crossing RLM components, domains, CLI, logging,
or Docker boundaries go in `tests/integration/`; Harbor harness checks go in
`tests/harbor/`; and live-evaluation support stays in `tests/eval_support/`.

Follow [`tests/README.md`](../../tests/README.md): arrange explicit inputs, act
through the public boundary, and assert observable results or artifacts. Use
`make_rlm` for scripted fake-runtime tests; its named `RLMHarness` exposes
`.rlm` and `.client` while preserving tuple unpacking. Do not force pure unit,
Docker, Harbor, and evaluation-support tests into one generic scenario type.

Prefer invariants over exact model-output transcripts.

For planned execution, test both routes with `FakeClient`: a fit record must
consume a bounded leaf before final rendering, and an oversized record must
launch a target-enforced child. Also assert the renderer bindings exclude the
original repo/corpus and that planner fallback remains manifest-scoped.
