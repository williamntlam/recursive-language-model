# Semantic sweep map-reduce research mode

## Status

Proposed implementation specification. This is an opt-in, high-cost research
mode for cases where semantic recall is more important than ordinary RLM
cost/latency. It does not replace `rlm ask`, specification 005 scoped
children, specification 006 planning, or specification 007 candidate search.

## Problem

Metadata and deterministic indexing can miss files whose relevance is visible
only in source semantics. A user may instead want every eligible source file
to receive a bounded language-model relevance judgment, then have those
judgments reduced recursively into an auditable candidate set. The standard
`ask` workflow should not silently incur the resulting model-call volume.

## Goals

- Provide a distinct command for an explicit, bounded semantic sweep of a
  repository.
- Inspect every eligible file or size-bounded file chunk with an LLM call that
  remains within token and instruction ceilings.
- Return structured `related`, `not_related`, or `uncertain` verdicts with
  citations and reasons; never rely on free-form child summaries alone.
- Recursively reduce verdicts while preserving all related/uncertain evidence
  and compact audit counts for negative results.
- Produce a rendered string report plus machine-readable local artifacts that
  let a user inspect routing and evidence.
- Preserve Docker isolation, read-only source mounts, host credential
  separation, and explicit cost/time/call caps.

## Non-goals

- Do not make a factual-completeness guarantee from a model sweep.
- Do not alter repository files, propose/apply patches, or become a coding
  shell.
- Do not run automatically from `rlm ask`, planner mode, candidate discovery,
  or test collection.
- Do not send an entire large repository or full child transcripts to a parent
  model.
- Do not discard an `uncertain` verdict merely to make the final set smaller.

## Command and activation

Add a separate CLI subcommand:

```bash
rlm semantic-sweep <path> -- "Which files implement or affect causal-LM loss shifting?"
```

It accepts the ordinary model, trace, budget, timeout, and log-directory
options plus sweep-specific limits:

```text
--max-files N             # hard eligibility cap; default must be conservative
--max-file-chunks N       # hard total chunk cap
--max-sweep-calls N       # hard model-call cap, including reducers
--sweep-leaf-chars N      # may only lower the ordinary safe leaf size
--sweep-concurrency N     # capped worker count
--include-glob PATTERN    # repeatable, explicit eligible-path restriction
--exclude-glob PATTERN    # repeatable additional exclusion
--resume <run-dir>        # resume only from validated local sweep artifacts
--dry-run                 # show deterministic eligibility/cost estimate; no Docker or API call
```

No implicit defaults may sweep an unbounded repository. If eligibility exceeds
a cap, the command exits with a compact, actionable summary unless the user
narrows the include patterns or explicitly raises a permitted cap. `--dry-run`
must report the number of files, chunks, estimated reducers, maximum possible
calls, and explicitly state that estimates are not model usage.

## Core data contracts

### Sweep unit

The runtime deterministically builds `SweepUnit` records before model calls:

```json
{
  "id": "u-000123-02",
  "path": "src/example/model.py",
  "start": 401,
  "end": 760,
  "n_chars": 14882,
  "content_digest": "…"
}
```

Units are whole files at or below `sweep_leaf_chars`; larger files are split
into line-aligned chunks using existing safe sizing behavior. Unit IDs and
ordering are deterministic. Source text is bound inside the leaf REPL/context
only for that unit; it is not copied into reducer or parent prompts.

### Leaf verdict

Each unit produces strict JSON matching a versioned schema:

```json
{
  "version": 1,
  "unit_id": "u-000123-02",
  "verdict": "related",
  "confidence": "medium",
  "reasons": ["normalizes labels before loss"],
  "citations": [{"path": "src/example/model.py", "start": 440, "end": 468}],
  "follow_up_paths": ["src/example/config.py"]
}
```

`verdict` is exactly `related`, `not_related`, or `uncertain`; confidence is
exactly `high`, `medium`, or `low`. Citations must lie inside the assigned unit
and are validated deterministically. Reasons are bounded text and must not
contain source-body quotes beyond existing artifact limits. `follow_up_paths`
are hints only; they never expand the sweep or authorize a read without a
separate deterministic eligibility decision.

Malformed, missing, out-of-unit, or budget-exhausted leaf output becomes an
`uncertain` record with a machine-readable failure reason; it may not be
silently treated as `not_related`.

### Reducer summary

Reducers receive only bounded verdict records, compact reasons, valid
citations, and aggregate counts—not source bodies. They return schema-checked
JSON that may group evidence and identify conflicts, but cannot change an
underlying verdict, delete a related/uncertain record, invent a citation, or
request arbitrary source access.

The deterministic reducer fallback merges records by rule when a model reducer
fails: retain all `related`/`uncertain` records, deduplicate validated
citations, and aggregate `not_related` counts by package.

## Execution lifecycle

```text
deterministic eligibility + sizing
          │  fail before model calls if over cap
          ▼
parallel bounded leaf verdict calls (one unit at a time)
          │  strict validation; failures become uncertain
          ▼
package/batch reducers over verdict metadata only
          │  preserve positive/uncertain evidence
          ▼
deterministic final merge + optional bounded root synthesis
          ▼
rendered report_text: str + local verdict artifacts
```

1. Eligibility uses existing ignore rules plus explicit include/exclude globs.
   It enumerates all eligible paths before starting a leaf call.
2. The runtime measures and chunks paths deterministically, reserves worst-case
   budget/call slots, then schedules leaves up to `sweep_concurrency`.
3. Each leaf is a source-bounded operation. Its prompt asks only whether the
   assigned unit bears on the user question and requires the verdict schema.
4. Reducer batches are hierarchical and bounded by both record count and prompt
   tokens. A reducer sees IDs/citations/reasons, never unit bodies.
5. The terminal report distinguishes `related`, `uncertain`, and scanned-but-
   not-related counts, states cap/truncation/failure status, and cites claims.

## Safety, cost, and correctness policy

- A sweep must require an explicit finite `max_budget`, `max_timeout`,
  `max_files`, and `max_sweep_calls`; there is no unlimited mode.
- The scheduler stops launching new units when remaining budget/time/call slots
  cannot cover the configured reserve. Unstarted units are reported as
  unscanned, never not-related.
- Every model send uses existing `<100,000` prompt and `≤150` instruction
  guards. A chunk is reduced further if needed.
- Source content stays in the leaf context/container. Root and reducers get
  only structured, bounded metadata and citations.
- Results are advisory research findings, not an authorization to change files.
- Resume validates the repository identity, sweep configuration digest, unit
  digest, and artifact schema before reusing any verdict. Mismatches require a
  new run.

## Observability and artifacts

Under the run directory, write versioned local artifacts:

```text
sweep-manifest.json       # eligibility, units, limits, digests; no bodies
verdicts.jsonl            # validated leaf verdicts and failures
reductions.jsonl          # reducer inputs/outputs in capped/redacted form
sweep-summary.json        # counts, coverage, costs, timings, citations
```

Trace events include only compact fields: unit/file/chunk counts, result and
configuration digests, verdict counts, invalid-output count, unscanned count,
reducer levels, costs, timing, and cap-trigger reasons. Metadata capture does
not contain paths, source text, raw prompt text, or raw model content. Existing
content-capture rules may retain capped/redacted artifacts locally.

The HTML report must clearly label semantic-sweep findings as model judgments,
show coverage and uncertainty, and link to local artifact summaries without
dumping source bodies.

## Acceptance criteria

- `semantic-sweep` is absent from ordinary `ask` execution and requires the
  explicit subcommand plus finite caps.
- Dry run computes stable units/call estimates without Docker or an API call.
- A fixture with a related file, unrelated file, oversized related file, and
  malformed leaf output preserves correct unit assignment and turns malformed
  output into `uncertain`.
- No leaf sees a source span outside its assigned unit; no reducer/root prompt
  contains a source body.
- Every related/uncertain record in leaf results survives reduction, with valid
  citations; negative records remain auditable as aggregate counts.
- Budget/time/call exhaustion produces an incomplete coverage report and never
  labels unscanned files not-related.
- Resume reuses only matching, schema-valid artifacts and yields a deterministic
  scheduling order for remaining units.
- Unit, runtime, trace, CLI, prompt-budget, and Docker integration tests pass.

## Evaluation

Add opt-in evaluation fixtures with known semantic relevance that cannot be
recovered reliably from filenames alone. Evaluate repeated trials on:

- file-level recall and precision for `related` plus `uncertain`;
- citation validity and whether citations support the claimed relation;
- coverage/unscanned rate under fixed caps;
- leaf/reducer/root call counts, latency, cost, and reducer compression ratio;
- false-negative rate from `not_related` judgments;
- comparison with metadata candidate search and scoped-planner modes.

Do not present one sweep as a benchmark score. Report model, configuration,
repository revision, artifact schema version, attempts, and individual results.

## Rollout

1. Implement deterministic eligibility, units, strict leaf schema, and dry-run
   with fake-client tests.
2. Add capped parallel leaf scheduling, artifacts, and failure-as-uncertain
   behavior; test budget/call stopping.
3. Add deterministic reducer fallback, then optional model reducers with
   schema validation and citation preservation tests.
4. Add Docker tests, reports, resume validation, and opt-in evaluations.
5. Keep the command experimental until repeated trials establish a useful
   recall/cost trade-off.

## Likely implementation areas

- CLI/configuration: `rlm/cli.py`, `rlm/config.py`, configuration docs/tests.
- Scheduling and model guards: `rlm/core/runtime.py`, budgets, prompt guard,
  history, and a dedicated sweep module.
- Domain sizing/scope: `rlm/domains/repo.py`, `rlm/repl_ns.py`, and Docker IPC
  bindings.
- Artifacts/reporting: `rlm/logging/`, trace summary/report tests.
- Opt-in cases and rubric: `evals/` and focused deterministic fixtures.
