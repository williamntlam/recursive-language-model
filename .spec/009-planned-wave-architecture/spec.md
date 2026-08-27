# Planned-wave architecture

## Status

Proposed implementation specification. This adds an opt-in `planned_waves`
execution architecture for repository and corpus research. It extends the
existing `direct` and single-pass `planned` architectures; it does not replace
either or silently change ordinary `rlm ask` behavior.

## Problem

The current constrained planner must receive a compact manifest and may select
only a bounded number of records. Large repositories can therefore have more
admissible evidence than one planner prompt or one execution pass can cover.
Increasing a manifest cap is not sufficient: it can overflow the planner
prompt, final renderer, or model-work budget. In addition, a failed planner
must never cause a Docker REPL to regain access outside its deterministic
scope.

## Goals

- Deterministically inventory every eligible repository file or corpus document
  into a local, source-free census artifact.
- Split that inventory into token-safe planner shards, allowing many bounded
  planner calls over time.
- Execute validated selections in bounded leaf/child waves under one global
  budget and timeout.
- Preserve exact coverage state for every census record.
- Keep source bodies out of planner, reducer, and final-render prompts.
- Enforce fallback scopes across the host-to-Docker boundary.
- Make `direct`, `planned`, and `planned_waves` independently selectable and
  comparable in tests and benchmarks.

## Non-goals

- No uncapped prompt, IPC message, model-call fan-out, or final-render input.
- No child RLM per file by default; deterministic inspection remains preferred
  when it can answer the question.
- No automatic activation for ordinary `ask` or `research`.
- No claim that all records were semantically understood when budget or timeout
  leaves coverage incomplete.
- No source-body persistence in the census, planner, reducer, coverage, or
  report artifacts.

## Terminology

| Term | Meaning |
| --- | --- |
| Census artifact | Complete local metadata inventory for a run. |
| Record | One investigable file, document, or declaration span. |
| Planner shard | A token-safe group of records supplied to one planner call. |
| Planner wave | One planner call plus its validated selected records. |
| Execution wave | The bounded leaf/child work resulting from a planner wave. |
| Reduction batch | Bounded, source-free findings combined for final rendering. |

## Activation and configuration

Select the architecture explicitly:

```bash
rlm ask ./repo --architecture planned_waves -- \
  "Trace every route by which source content can cross the runtime boundary."
```

Configuration adds only bounded controls; it does not provide an unlimited
mode:

```toml
architecture = "planned_waves"
planner_shard_target_tokens = 12000
planner_wave_max_selected = 16
planner_wave_max_leaf_calls = 16
planner_wave_max_child_calls = 8
planner_wave_concurrency = 2
reduction_target_tokens = 12000
```

All values remain constrained by the existing `<100,000` prompt-token and
`≤150` instruction contracts, global `max_budget_usd`, `max_timeout_s`,
`max_depth`, and subcall concurrency. A run with neither a budget nor timeout
is allowed only under the product's existing policy, but it must still report
progress and may be interrupted normally.

`planner_enabled` remains only the compatibility alias for the existing
single-pass `planned` architecture; it never implicitly selects
`planned_waves`.

## Data contracts

### Census record

The host creates stable, ordered records. It may read source to measure or
parse it, but the persisted and planner-visible representation contains no
source body:

```json
{
  "id": "r-000421",
  "target": {"path": "rlm/core/runtime.py", "start": 660, "end": 740},
  "n_chars": 3512,
  "n_tokens_estimate": 878,
  "route": "fit",
  "signals": ["kind:FunctionDef", "name:leaf_complete"],
  "content_digest": "sha256:..."
}
```

The census has no arbitrary record or path cap. It is local data and is written
incrementally as JSONL so a large tree does not require one giant in-memory
manifest. Ignore rules and text-file detection remain deterministic and are
recorded in the artifact metadata.

### Planner shard

A shard is **not** one source artifact or one investigation target. It is a
group of census records. The scheduler builds it greedily in deterministic
record order, serializing the exact planner request after every candidate
addition and measuring it with `count_tokens()`. It stops before the target
token budget or hard prompt ceiling would be exceeded.

Each shard has a digest, ordinal, record-ID list, token count, and count of
records deferred to later shards. The planner receives only the query, schema,
budget summary, and these record metadata. It may select only IDs in its own
shard.

### Coverage record

Every census record has exactly one terminal or pending state:

```json
{
  "record_id": "r-000421",
  "status": "executed",
  "planner_shard": 12,
  "execution_wave": 12,
  "route": "leaf",
  "finding_digest": "sha256:..."
}
```

Allowed statuses are `pending`, `not_selected`, `selected`, `executed`,
`failed`, `skipped_budget`, `skipped_timeout`, and `unplannable`. A record
cannot become `not_selected` merely because a planner call failed; it instead
receives `unplannable` with a reason and remains visible in final coverage.

## Execution lifecycle

```text
full deterministic census (local JSONL; metadata only)
        ↓
token-aware shard builder
        ↓
bounded planner calls, one per shard
        ↓
validated selections and fixed leaf/child routes
        ↓
budgeted execution waves
        ↓
bounded source-free reduction tree
        ↓
final renderer + complete coverage summary
```

1. Create the census before the first planner call and write `census.jsonl`.
   The artifact records total eligible paths, records, truncation only for
   actual read/parse failures, and configuration digests.
2. Build the next token-safe shard. Before calling the planner, check global
   budget, timeout, and remaining call capacity.
3. Parse and validate planner JSON against that shard only. Unknown IDs,
   duplicate IDs, invalid routes, or excess per-wave calls reject the plan.
4. Execute selected `fit` records as bounded leaf calls and selected `child`
   records as target-enforced child RLMs. The scheduler may run a bounded
   number of independent execution waves concurrently, never bypassing the
   existing global budget accounting.
5. Append coverage and compact finding metadata after each item. On budget or
   timeout exhaustion, stop launching work and mark only unstarted work as
   skipped; do not call it investigated or irrelevant.
6. Reduce compact findings in token-safe batches. Reducers and final rendering
   receive citations, digests, statuses, and bounded findings—not `repo`,
   `corpus`, a workspace, or source bodies.

## Scope enforcement across Docker

This is a required prerequisite, not optional hardening.

When a plan fails or a child is target-scoped, the exact normalized targets
must cross the host-to-container initialization boundary. The Docker `init`
message carries a versioned `targets` field; `docker/repl_server.py` constructs
the bound `Repo` or `Corpus` with those targets. The container-side domain
object revalidates every target before exposing it through `files`, `grep`,
`read`, `file_text`, `measure`, `ask`, or `explore`.

An absent `targets` field means intentionally unscoped `direct` execution.
An empty target list means an empty scope, never full-domain access. IPC
messages retain their explicit maximum byte limit and are not used to transfer
the full census.

## Planner failure behavior

For `planned_waves`, a rejected planner shard must not reopen the repository.
Choose one explicit policy, recorded per shard:

- `stop`: mark the shard `unplannable` and continue to later shards; or
- `deterministic_fallback`: provide only that shard's targets to a restricted
  REPL phase that performs deterministic inspection without unrestricted child
  delegation.

Initial implementation should use `stop` for the clearest coverage semantics.
The existing `planned` architecture must also transfer its fallback targets
into Docker before it can claim scope enforcement.

## Artifacts and observability

```text
artifacts/
  census.jsonl                 # all source-free census records
  census-summary.json          # totals, ignore policy, digests
  planner-shards.jsonl         # shard IDs, token counts, record IDs, outcomes
  coverage.jsonl               # state transitions for every record
  findings.jsonl               # capped/redacted findings and citations
  reductions.jsonl             # source-free reduction batches
  planned-waves-summary.json   # coverage, costs, timing, incomplete reasons
```

Artifacts are append-only and versioned. Their number is not capped by the
former manifest record limit; disk writes fail clearly rather than silently
dropping records. Per-item and aggregate byte limits remain for optional raw
content capture. Trajectory events contain counts, IDs/digests, token totals,
route counts, coverage transitions, and errors—not source bodies.

The HTML report displays architecture name, completed/pending/skipped counts,
planner-shard outcomes, and an explicit incomplete label when applicable.

## Acceptance criteria

- A repository with more than 256 eligible records produces a complete census
  artifact and multiple planner shards without one planner prompt exceeding
  the configured token limit.
- A planner can never select a record outside its shard; every selection is
  deterministically route-validated.
- A forced planner rejection followed by Docker execution cannot read, grep,
  list, or measure an out-of-scope file. This is covered by a Docker
  integration test, not only `FakeEnv`.
- An empty scoped target set exposes no files.
- Every census record appears in coverage output, including failures and work
  skipped by budget or timeout.
- No planner, reducer, or final-render request contains a source body; leaf
  and child calls remain target-bounded and pass existing prompt guards.
- Final reduction remains below its prompt budget for thousands of findings.
- `direct` and `planned` preserve their current behavior and can be benchmarked
  against `planned_waves` with the same repository, query, budget, and model.

## Test and evaluation plan

- Unit-test greedy exact-token sharding, stable ordering, empty scopes, and
  coverage state transitions.
- Use `FakeClient` to validate multiple accepted/rejected shard plans and
  budget exhaustion without transcript-dependent assertions.
- Add Docker integration tests for host-to-container scope transfer and an
  attempted out-of-scope `repo.read`, `repo.grep`, and `repo.files` call.
- Assert each planner prompt is source-free and below the configured ceiling;
  assert each reducer/final prompt excludes domain bindings and source text.
- Add benchmark cases at small, medium, and large census sizes that report
  coverage, planner calls, selected records, leaf/child calls, latency, cost,
  and citation validity per architecture.

## Rollout

1. Repair host-to-Docker target propagation and add Docker scope regressions.
2. Add streamed census and artifact schemas behind `planned_waves` dry-run.
3. Add exact-token sharding and sequential planner waves with coverage output.
4. Add bounded execution waves and deterministic source-free reduction.
5. Add opt-in benchmarks, then consider bounded planner-wave concurrency.
