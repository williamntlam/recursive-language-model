# Evaluations

RLM has two complementary evaluation layers:

- **Harbor agent tasks** under [`evals/harbor/`](../evals/harbor/README.md) are
  the supported path for benchmarking an autonomous agent in a reproducible
  sandbox.
- **Legacy LLM-judge utilities** under [`evals/`](../evals/README.md) remain
  opt-in tools for RLM-specific long-context and source-grounding experiments.

The Harbor task evaluates read-only source analysis. It does not turn RLM into
a coding agent and does not replace the legacy judges until equivalent Harbor
tasks exist.

## Harbor task format

Every Harbor task is self-contained:

```text
<task>/
├── task.toml
├── instruction.md
├── environment/Dockerfile
└── tests/test.sh
```

`instruction.md` is the task the agent receives. `environment/Dockerfile`
defines its sandbox and source material. Harbor runs `tests/test.sh` after the
agent finishes; the script writes a numeric result to
`/logs/verifier/reward.txt`.

The initial `rlm-reading-contracts` task makes its source snapshot root-owned
and read-only. The non-root agent may inspect `/workspace/source` and writes
only `/workspace/answer.md`. Verifier rules and expected facts remain under
`tests/`.

## Setup and local run

Install Harbor separately from the RLM package:

```bash
uv tool install harbor
```

Local Harbor execution requires a running Docker daemon and an installed agent
adapter. To run the task repeatedly, supply the adapter and model appropriate
to your agent integration:

```bash
harbor run \
  --path evals/harbor/rlm-reading-contracts \
  --agent <agent-adapter> \
  --model <model> \
  --n-attempts 5
```

Harbor records the per-trial reward, verifier output, and agent trajectory in
its job directory. A cloud sandbox provider can run many isolated trials in
parallel; use local Docker for task development and small runs. Deep Agents
requires a compatible Harbor adapter or custom adapter import path.

## Lite, full, and deterministic checks

[`evals/harbor/suites/lite.txt`](../evals/harbor/suites/lite.txt) is the frozen
fast-iteration subset. [`full.txt`](../evals/harbor/suites/full.txt) is the
release-gate set. Both currently contain the one maintained task. As new tasks
arrive, add them to full by default and select only representative,
hard-but-solvable tasks for lite.

Use multiple attempts for reported benchmark scores: an agent's behavior is
nondeterministic even when the task environment and verifier are deterministic.

Run fast task and verifier checks on every Harbor-task change:

```bash
uv run pytest tests/test_harbor_tasks.py tests/capabilities
uv run ruff check evals/harbor tests/test_harbor_tasks.py tests/capabilities
```

These checks cover task layout, the read-only source contract, reward-file
output, and accepted/rejected answer artifacts. They are the unit-test layer;
Harbor trials are the integration-test layer.

## Change tracking

Repository changes are recorded in [`CHANGELOG.md`](../CHANGELOG.md). Every
entry is timestamped with local date, time, and timezone. The version-controlled
pre-push hook in [`.githooks/`](../.githooks/README.md) blocks a push when its
outgoing commits do not include a changelog update.

See [spec 003](../.spec/003-harbor-readonly-evaluations/spec.md) for the full
read-only Harbor evaluation contract.
