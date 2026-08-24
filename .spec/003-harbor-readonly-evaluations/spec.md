# 003 — Harbor Read-Only Agent Evaluations

**Status:** Implemented reference  
**Date:** 2026-08-24  
**Owner:** William Lam  
**Depends on:** 002 comprehensive evaluation program; Harbor 0.22.0 task format

---

## 1. Purpose

Document the Harbor-based evaluation assets added to this repository. The goal
is to evaluate an autonomous agent's ability to inspect source material and
produce a grounded answer in a reproducible sandbox, without changing RLM into
a coding agent or granting the evaluated agent write access to the source.

This specification records the current implementation. It does not claim to
reproduce the external Harbor-Index dataset, nor does it make a Terminal-Bench
score a product-quality gate.

## 2. Scope

The implemented local Harbor dataset is under `evals/harbor/`. Its initial
task, `rlm-reading-contracts`, asks an agent to read a small RLM source snapshot
and write a cited explanation of history and prompt-safety contracts.

The task follows Harbor's standard task layout:

```text
evals/harbor/rlm-reading-contracts/
├── task.toml
├── instruction.md
├── environment/
│   ├── Dockerfile
│   └── source/
└── tests/
    ├── test.sh
    └── verify_answer.py
```

In scope:

- a self-contained Docker environment for a source-reading task;
- an explicit Markdown instruction and a deterministic `tests/test.sh`;
- Harbor's numeric reward protocol;
- frozen lite/full suite manifests;
- fast deterministic capability checks for the task harness; and
- opt-in Harbor trials, including repeated attempts.

Out of scope:

- editing, testing, or otherwise mutating the RLM product source;
- API keys, public network access, or live LLM judging inside the task;
- a Deep Agents adapter implementation;
- importing or republishing Harbor-Index or Terminal-Bench tasks; and
- replacing the legacy Python judge utilities with paid live runs in pytest.

## 3. Read-only environment contract

The environment image is intentionally small and runs the agent as the
non-root `agent` user.

| Location | Access | Purpose |
| --- | --- | --- |
| `/workspace/source` | Root-owned, read-only | RLM source snapshot to inspect |
| `/workspace/answer.md` | Agent-writable | Sole required deliverable |
| `/tests` | Verifier-only | Test entry point and ground-truth checks |
| `/logs/verifier/reward.txt` | Verifier output | Numeric Harbor reward |

`environment/Dockerfile` copies the task source snapshot, makes it read-only
with `chmod -R a-w`, and switches to `USER agent`. The task instruction
explicitly prohibits source edits and names `/workspace/answer.md` as the
required output.

This design preserves RLM's product boundary: the benchmark measures reading
and source-grounded synthesis, not code modification. It is not a security
boundary against a malicious privileged container runtime; Harbor sandboxing
and its configured container provider remain responsible for that broader
boundary.

## 4. Task and verifier contract

`instruction.md` asks for a concise, cited explanation of:

1. why bound context must not enter parent history and how history compacts;
2. the 150-instruction ceiling and 99,999-token maximum; and
3. whether a 100,000-token prompt can be sent.

The answer must cite `rlm/core/history.py`, `rlm/core/prompt_guard.py`, and
`rlm/config.py` using `path.py:line` or `path.py:start-end` notation.

`tests/test.sh` is the Harbor verifier entry point. It runs the verifier-only
Python checker and always writes either `1` or `0` to
`/logs/verifier/reward.txt`. The checker evaluates the actual answer artifact:
it requires a substantial explanation, the three source citations, and each
required safety conclusion. It does not require the agent to use a prescribed
tool or command.

## 5. Benchmark operation

### 5.1 Repeated trials

An agent trial is nondeterministic even when the task and verifier are
deterministic. Reported results therefore use multiple attempts per task. A
run records the task set, task revision, agent/adaptor version, model,
attempt count, individual rewards, and aggregate success rate.

With Harbor 0.22.0, an individual local task is invoked conceptually as:

```bash
harbor run \
  --path evals/harbor/rlm-reading-contracts \
  --agent <deep-agents-adapter> \
  --model <model> \
  --n-attempts 5
```

The repository does not provide `<deep-agents-adapter>`; it must be supplied
by the Deep Agents integration or custom Harbor adapter.

### 5.2 Frozen suite manifests

`evals/harbor/suites/lite.txt` and `evals/harbor/suites/full.txt` are
versioned, one-task-per-line manifests.

- **Lite** is the fast iteration subset, selected for hard-but-solvable and
  representative tasks.
- **Full** is the release-gate set and contains every maintained task.

Both lists currently contain the sole task and are therefore intentionally
identical. As the suite grows, new tasks enter `full.txt` by default and enter
`lite.txt` only through an explicit representativeness/cost decision. A change
to either manifest is a benchmark-version change and must be reviewed as such.
No fixed speed or cost ratio is claimed until measured on a larger suite.

### 5.3 Capability layer

Benchmark trials are integration tests, not a replacement for unit tests.
`tests/capabilities/test_harbor_reading_verifier.py` supplies the fast,
deterministic capability layer for this task's harness:

- a valid cited answer artifact is accepted;
- an answer that omits source citations is rejected; and
- the static task-layout tests enforce the verifier/reward and read-only-source
  contracts.

Run it on task or verifier changes:

```bash
uv run pytest tests/test_harbor_tasks.py tests/capabilities
uv run ruff check evals/harbor tests/test_harbor_tasks.py tests/capabilities
```

Tool-selection, memory, and other Deep Agents-specific capabilities belong in
the Deep Agents integration repository, since this repository does not
implement that harness.

## 6. Relationship to legacy evaluations

`evals/context_needle_judge.py` and
`evals/transformers_causal_lm_judge.py` remain opt-in development utilities.
They can still inform RLM runtime work, but they are not the supported Harbor
benchmark entry point and must not be represented as comparable Harbor scores.

The Harbor task is intentionally deterministic and has no API cost. It
therefore complements, rather than replaces, bounded LLM-judge experiments.

## 7. Acceptance criteria

The implementation is complete when all of the following are true:

1. Every local Harbor task contains `task.toml`, `instruction.md`,
   `environment/Dockerfile`, and `tests/test.sh`.
2. The agent receives a read-only source tree and writes only the stated answer
   artifact.
3. The verifier writes a numeric reward at `/logs/verifier/reward.txt` on both
   pass and fail.
4. Static tests validate task structure and the source-read-only contract.
5. Capability tests exercise both an accepted and a rejected answer artifact.
6. Lite/full suite selection is versioned and documented.
7. Reported agent results use explicit repeated attempts rather than a single
   trial.

## 8. Validation record

The following checks passed when the implementation was added:

```text
5 passed: tests/test_harbor_tasks.py and tests/capabilities
ruff check: all checks passed
```

Harbor 0.22.0 is installed locally. Docker was unavailable in the development
environment at validation time, so an actual Harbor container trial was not
executed. Running the task requires a running Docker daemon or a configured
Harbor sandbox provider and a Deep Agents Harbor adapter.
