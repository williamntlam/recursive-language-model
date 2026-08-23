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
uv run pytest tests/test_<area>.py
uv run pytest
uv run ruff check rlm tests
```

For fake runtime tests, read [`references/fake-runtime.md`](references/fake-runtime.md).
Docker tests are separate and require a running daemon:

```bash
uv run pytest -m docker
```

Prefer invariants over exact model-output transcripts.
