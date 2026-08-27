# Architecture benchmark playbook

Use the executable runner under
[`tests/architecture_benchmark.py`](../tests/architecture_benchmark.py) to
compare the direct REPL workflow with opt-in deterministic scoping and
constrained planning. It runs each case in both modes with the **same target
and exact same question**.

This is a repeatable manual integration test, not a replacement for the
offline pytest suite or a reported benchmark. It needs Docker and
`OPENAI_API_KEY`.

## What “size” means

Choose a band by the estimated amount of source evidence required to answer
the question, not by the repository checkout size or parent prompt size. A
useful rough estimate is source characters divided by four. The REPL can hold
much more than these amounts without putting it in the root prompt.

| Band | Evidence to inspect | Approximate source characters | Purpose |
|---|---:|---:|---|
| Small | ≤25k tokens | ≤100k chars | One or a few files; planning overhead may not pay for itself. |
| Medium | 25k–150k tokens | 100k–600k chars | Several modules/documents with real candidate selection. |
| Large | >150k tokens | >600k chars | Broad codebase/corpus census where uncontrolled reads and bad splits are costly. |

The `fit`/`child` route is different: a fit record is at most 24,000
characters (about 6k tokens) for a single leaf. A medium or large test is an
aggregate of many potential records, not one enormous model call.

## Run the benchmark

The runner is opt-in and is not collected by pytest. It needs Docker and
`OPENAI_API_KEY`; each attempt makes one direct and one planned RLM run per
case.

```bash
export OPENAI_API_KEY='...'

# All small/medium/large cases, three paired attempts each.
UV_CACHE_DIR=/tmp/rlm-uv-cache uv run python tests/architecture_benchmark.py \
  --target . --attempts 3

# One large case against a local Transformers clone.
UV_CACHE_DIR=/tmp/rlm-uv-cache uv run python tests/architecture_benchmark.py \
  --target codebases/transformers \
  --case large-representative-census --attempts 3

# A corpus target uses the same cases but calls RLM.research.
UV_CACHE_DIR=/tmp/rlm-uv-cache uv run python tests/architecture_benchmark.py \
  --target ./papers --domain corpus --case medium-boundary-audit
```

It writes a versioned JSON comparison to `evals/results/architecture-benchmark.json`
by default. Override that with `--output`. Each trial contains usage, root
turns, REPL cells, planner acceptance/fallback, manifest/selection size,
planned leaf/child counts, answer digest, and valid-citation count.

## Manual equivalent

Set a target and a run directory. Keep the question in a shell variable so it
cannot drift between the baseline and planner run.

```bash
export OPENAI_API_KEY='...'
target=./path/to/repository
runs=.rlm/planner-tests
question='Replace this with one of the questions below.'

# Confirm the planned run builds a bounded manifest without starting Docker.
uv run rlm ask "$target" --planner-enabled --dry-run -- "$question"

# Direct baseline.
uv run rlm ask "$target" --log-dir "$runs/baseline" -- "$question"

# New architecture.
uv run rlm ask "$target" --log-dir "$runs/planner" --planner-enabled -- "$question"
```

Run each pair at least three times before comparing quality or cost. Model
output is nondeterministic even when the manifest is deterministic. For a
corpus, replace `ask` with `research` and use a document-oriented question.

## Small: focused implementation trace

Use a small repository or a tightly bounded module. This checks that planning
does not regress a task that direct REPL already handles well.

```bash
question='Trace the implementation of the public configuration loading path:
from CLI/API inputs through config discovery, coercion, validation, and final
Config construction. Identify precedence and every explicit failure condition.
Cite each claim with file and line spans.'
```

Expected result: both modes should have valid citations and a short answer.
The planner may cost more than the baseline; that is useful evidence that it
should remain opt-in for small work.

## Medium: cross-module boundary audit

Use a repository where the answer requires several modules but not an entire
monorepo. This checks whether the planner chooses a compact, representative
set of records and routes them correctly.

```bash
question='Audit every path by which source content, paths, prompts, model
output, credentials, or errors cross the CLI/config, API, runtime, Docker/IPC,
REPL namespace, leaf/child, and trajectory logging boundaries. For each path,
state the enforcing code, whether the protection is deterministic or
prompt-guided, and a relevant regression test. Separate confirmed guarantees
from assumptions and cite all claims.'
```

Expected result: the planned run should produce `scope_manifest`, an accepted
`planner` event, `plan_execution`, and a small number of leaf/child calls. It
should not need a broad root-REPL scan before collecting evidence.

## Large: representative census

Use a substantial codebase or corpus. Hugging Face Transformers is a suitable
example if it is locally checked out under `codebases/transformers`.

```bash
target=codebases/transformers
question='Under src/transformers/models, compare the implementations of all
classes whose names end in ForCausalLM. Determine where labels are shifted,
how loss is computed, and which representative differences are architectural
rather than incidental. Exclude ForPreTraining and task/entity heads. Report
coverage limits explicitly and cite every representative finding.'
```

For a large corpus, use:

```bash
question='Across the full corpus, identify the strongest contested claims about
the topic. Group evidence by claim, explain the disagreement, distinguish
primary support from rebuttal, and cite document IDs and character spans. Say
where the catalog or candidate scope is incomplete.'
```

Expected result: a truncated manifest is an honest coverage signal, not a
failure. Compare whether the planned run avoids whole-tree body reads and
unrelated representatives while retaining valid citations.

## Inspect and compare each run

The CLI prints a trajectory directory. Create a readable report for either
run:

```bash
uv run rlm report <trajectory-directory>
```

For a planned run, inspect `events.jsonl` in that directory:

```bash
rg 'scope_manifest|planner|plan_execution|planner_fallback_scope|rlm_query' \
  <trajectory-directory>/events.jsonl
```

Successful constrained planning has:

- `scope_manifest` with record count, caps, truncation flags, and digest;
- `planner` with `validation: accepted`;
- `plan_execution` with leaf/child totals; and
- `plan_execution_item` records with digested references, never raw source.

An invalid planner response is still a useful test outcome. It records
`planner` with `fallback: true` and `planner_fallback_scope`; the staged REPL
remains limited to the deterministic manifest rather than reopening the full
domain.

Record each paired trial in a small table:

| Band / trial | Mode | Planner accepted? | Manifest records / truncated | Selected | Leaf / child | Root turns | Cost | Citation quality / notes |
|---|---|---|---|---:|---|---:|---:|---|
| Medium 1 | direct | n/a | n/a | n/a | — | | | |
| Medium 1 | planner | yes/no | | | | | | |

Prefer evidence over intuition when deciding whether to use planning for a
workload: compare valid citations, representative relevance, broad-read/tool
counts, root turns, timeout rate, and cost—not answer fluency alone.

## Deterministic checks

These do not require Docker or an API key and should pass before live trials:

```bash
UV_CACHE_DIR=/tmp/rlm-uv-cache uv run pytest tests/test_scope.py -q
UV_CACHE_DIR=/tmp/rlm-uv-cache uv run ruff check rlm tests
```

They cover stable manifests, strict plan validation, fit-to-leaf execution,
oversized target-enforced child execution, and manifest-scoped fallback.
