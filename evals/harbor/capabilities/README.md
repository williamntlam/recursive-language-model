# Deterministic capability suite

The Harbor tasks are the integration layer: they measure whether an autonomous
agent can read source material and produce a grounded answer. This directory
describes the complementary deterministic layer, implemented in
[`tests/harbor`](../../../tests/harbor).

The current checks target the boundaries this read-only harness owns:

- file operation: a valid `/workspace/answer.md` is accepted;
- source grounding: missing required source citations are rejected;
- verifier protocol: either outcome produces Harbor's numeric reward file.

Run these on every change to a task or verifier:

```bash
uv run pytest -m harbor
```

Add harness-specific tests for tool selection, memory, or other Deep Agents
behaviors in the Deep Agents integration repository. Those behaviors are not
implemented by this RLM package, so this dataset must not pretend to test them.
