# Harbor reading tasks

This directory contains the maintained, Harbor-compatible evaluation suite for
read-only agent work. It is modelled on the self-contained task format used by
Harbor Index, rather than being a copy of the external Harbor-Index dataset.

Every task has the Harbor layout:

```text
<task>/
├── task.toml
├── instruction.md
├── environment/Dockerfile
└── tests/test.sh
```

The agent image exposes source material at `/workspace/source` as a root-owned,
read-only tree. The only expected deliverable is `/workspace/answer.md`.
`tests/` is verifier-only material and writes the numeric Harbor reward to
`/logs/verifier/reward.txt`.

`rlm-reading-contracts` is an autonomous repository-reading task: the agent
must inspect a small RLM source snapshot, produce a cited explanation, and make
no product changes. It has no API key, network dependency, or live LLM judge.

Run an individual local task with Harbor, for example:

```bash
harbor run \
  --path evals/harbor/rlm-reading-contracts \
  --agent <deep-agents-adapter> \
  --model <model> \
  --n-attempts 5
```

The task's `task.toml` contains the authoritative resource limits. Harbor 0.22
accepts local task directories through `--path` and uses `--n-attempts` for
repeat trials. Supply the installed Deep Agents adapter's identifier (or its
custom Harbor adapter import path) in place of `<deep-agents-adapter>`.

The legacy Python judge scripts remain as development utilities for now. They
are not part of the Harbor task dataset and are not the supported benchmark
entry point.

## Running practice

Use repeated trials for every reported score. Agent behavior is
nondeterministic, so a single Harbor trial is only a sample; record the task
set, agent version, model, attempt count, and per-attempt rewards with any
aggregate result. The task itself is deterministic, but an agent's path to the
answer is not.

The checked-in suite manifests are deliberately frozen text lists:

- [`suites/lite.txt`](suites/lite.txt) is the fast iteration subset.
- [`suites/full.txt`](suites/full.txt) is the release-gate set.

They contain the same task while this dataset has one maintained task. When a
new task is added, it must be added to `full.txt`; add it to `lite.txt` only if
it is a hard-but-solvable representative worth the iteration cost. Never
silently change either list: review a manifest edit as a benchmark version
change. This gives us a stable lite/full split without promising a particular
cost ratio before the dataset is large enough to measure one.

[`capabilities/README.md`](capabilities/README.md) describes the accompanying
fast deterministic capability layer. Run it independently of Harbor during
development; it checks verifier/file-output behavior rather than measuring an
agent's end-to-end task completion.
