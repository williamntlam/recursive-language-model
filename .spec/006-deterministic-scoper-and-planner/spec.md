# Deterministic scoper and constrained research planner

## Status

Proposed implementation specification. This follows specification 005: its
scoped child views and string-only final contract are prerequisites.

## Problem

Specification 005 made staged research the intended prompt strategy, but the
runtime does not yet enforce the first two stages. A root model can still read
every candidate file in one large REPL cell, then choose weak representatives.
The Transformers trial illustrates both risks: it performed 490 `file_text`
reads and selected two non-causal-LM heads for a causal-LM comparison.

RLM needs a deterministic mechanism that establishes the admissible evidence
set before model planning, plus an optional planner that chooses bounded work
from that set. The planner must not become a second unconstrained research
agent or a source-bearing prompt.

## Goals

- Build a compact, deterministic candidate manifest for repository and corpus
  research before semantic routing.
- Let an optional planner choose inspection order, leaf/child routing, and
  report shape only from manifest records.
- Validate and execute plans deterministically; only the runtime may create
  scoped children.
- Preserve read-only source isolation, prompt and instruction ceilings, and
  the existing direct REPL workflow for small tasks.
- Make planning quality and routing cost observable without recording source
  content in metadata traces.

## Non-goals

- Do not make a model planner mandatory for every request.
- Do not send file/document bodies, target paths, or credentials to a planner
  outside the existing container boundary.
- Do not add write access, shell access, network access, or a general workflow
  language to the REPL.
- Do not promise semantic completeness from syntactic candidate discovery.
- Do not replace explicit `repo.explore(..., targets=...)` compatibility APIs.

## Concepts

### Deterministic scoper

The scoper is host/runtime code, not an LLM. Given a domain and query-derived
configuration, it creates a manifest of bounded metadata records. It may use
paths, filenames, file metadata, AST declarations, regex hits, line/character
spans, and measured sizes. It does not call an LLM and does not return source
bodies.

Repository record example:

```json
{
  "id": "r-017",
  "path": "src/transformers/models/afmoe/modeling_afmoe.py",
  "kind": "ClassDef",
  "qualname": "AfmoeForCausalLM.forward",
  "start": 617,
  "end": 677,
  "n_chars": 2475,
  "route": "fit",
  "signals": ["name:ForCausalLM", "method:forward"]
}
```

Corpus records use `id`, character offsets, measured size, and deterministic
catalog/search signals. The manifest has a stable digest and configurable caps
on records, paths, AST nodes, and metadata bytes.

### Constrained planner

The planner is an optional root-model turn that sees the user question and a
compact manifest, never source bodies. It returns strict JSON matching a
versioned schema. It may select manifest IDs, state an inspection question per
selection, request a leaf for a fit record or a scoped child for an oversized
record, and select a textual report shape.

```json
{
  "version": 1,
  "selected": [
    {"record_id": "r-017", "question": "How are labels shifted?", "route": "leaf"}
  ],
  "report_shape": "cited_markdown"
}
```

It cannot specify a raw path, span, Python code, arbitrary tool call, model
name, budget override, or nested plan. The runtime resolves record IDs to
validated target manifests and rejects anything outside the scoped inventory.

## Workstream A — deterministic scope manifests

### Required behavior

Add a domain-neutral `ScopeManifest` with version, domain, query digest,
records, counts, truncation indicators, and a digest of canonical JSON.
Implement repository and corpus scope builders:

- Repository builders accept explicit deterministic filters (path prefixes,
  glob patterns, class/function-name patterns, and optional AST predicates).
  They enumerate metadata first and parse only candidate source files within
  configured caps.
- Corpus builders filter catalog metadata and use bounded regex/offset
  inspection without copying document bodies into the manifest.
- Every record corresponds to a valid 005 target and includes measured routing
  metadata. Duplicate/overlapping records are normalized deterministically.
- If caps truncate discovery, the manifest exposes that fact so the planner
  can report uncertainty rather than assuming exhaustive coverage.

The ordinary root REPL remains available. Planner mode is explicitly opt-in:

```bash
rlm ask <path> --planner-enabled -- <query>
rlm research <path> --planner-enabled -- <query>
```

`--planner-enabled` builds a scope manifest and permits the planner lifecycle
for that run. Without it, the current direct REPL workflow remains unchanged.
Any future complexity-triggered default requires a separately approved change
after evaluation evidence; it is not part of this specification.

### Acceptance criteria

- Same inputs and configuration produce byte-identical canonical manifests and
  digests.
- Manifest metadata never contains source bodies or exceeds its configured
  size cap.
- A Transformers causal-LM fixture finds `*ForCausalLM` declarations and their
  `forward` spans without admitting unrelated `ForPreTraining` or entity-head
  records under that filter.
- Cap/truncation behavior is deterministic and visible in the manifest.

## Workstream B — planner contract and deterministic execution

### Required behavior

Add an opt-in planner mode, enabled by `--planner-enabled` (and the equivalent
`planner_enabled = true` configuration value), with this lifecycle:

1. Build and validate a deterministic scope manifest.
2. Send the planner only the user question, compact manifest, budget summary,
   and JSON schema.
3. Parse strict JSON; reject malformed output, unknown IDs, duplicates beyond
   configured limits, invalid route choices, and plan costs above remaining
   budget.
4. Resolve selected records to target manifests. Execute fit records locally or
   through leaf calls; execute oversized records only through 005 scoped child
   views.
5. Give the root REPL compact findings/citations and require it to render the
   final string answer. It may not widen the planner-derived scope without an
   explicit, separately logged fallback.

Planner failure is recoverable: fall back to the current staged REPL workflow
with a compact error hint, unless a future strict-planner option is configured.
Do not silently replace an invalid plan with a broad repository scan.

`--dry-run --planner-enabled` must show the planner prompt's token and
instruction counts, manifest record count/truncation status, and schema
version without starting Docker or sending a model request.

### Plan policy

- The runtime, not the planner, chooses the actual model from configured root
  and leaf models.
- A `fit` record may not request a child unless an explicit exceptional policy
  allows it and is traced.
- Each record may be inspected at most once per plan unless an explicit retry
  reason is recorded.
- Number of selections, child calls, leaf calls, and estimated cost are capped
  before execution.
- Planner output and selected manifest IDs are treated as untrusted data, not
  executable instructions.

### Acceptance criteria

- `--planner-enabled` activates planning for `ask` and `research`; omitting it
  does not build a manifest or add a planner turn.
- Planner prompt contains no source bodies and remains below 100,000 tokens
  and 150 instructions.
- Invalid plans fail recoverably without an out-of-scope read or child launch.
- A valid plan cannot cause a child to access any path/span not resolved from
  selected manifest records.
- Repeated runs with a fixed planner response execute the same target sequence
  and produce the same scope digest.
- The direct, non-planner REPL API remains backward compatible.

## Workstream C — observability and evaluation

### Required behavior

Trace planning as compact operational metadata:

- `scope_manifest`: domain, record count, truncation flags, canonical digest,
  and size/count caps.
- `planner`: enabled/fallback status, plan schema version, selected count,
  route counts, validation outcome, and plan digest.
- `plan_execution`: record IDs only as locally redacted/digested references,
  elapsed time, leaf/child counts, rejected actions, and scope digests.

Metadata capture must not contain paths, source text, planner prompt text, or
raw plan values that can include paths. Content capture follows existing
redaction/capping rules.

Add an opt-in multi-file Transformers evaluation comparing current staged REPL
behavior with deterministic-scoper-plus-planner behavior. Record candidate
set size, selected count, `file_text` calls, leaf/child calls, root turns,
timeouts, cost, valid citations, and whether representatives meet the task
filter. Do not run this evaluation from pytest or require a judge per user run.

### Acceptance criteria

- Trace summaries remain schema-compatible or version deliberately with a
  migration test.
- Metadata trace inspection proves source bodies and paths are absent.
- The Transformers evaluation penalizes whole-tree body reads and unrelated
  representatives, while rewarding valid bounded citations and route choices.
- Deterministic tests verify the evaluation case/layout without live model or
  Docker calls.

## Rollout and validation

1. Land manifest data structures and deterministic repository/corpus builders
   with unit fixtures first.
2. Land `--planner-enabled`, its equivalent configuration value, dry-run
   output, and strict planner parsing/validation. Test invalid, over-budget,
   and out-of-scope plans.
3. Connect plan execution to existing 005 scoped children and leaf routing;
   run Docker boundary tests.
4. Add trace/report support and the opt-in Transformers comparison. Evaluate
   repeated trials before changing any default threshold.
5. Consider enabling planning automatically only after evidence shows lower
   broad-read counts and equal-or-better citation quality at acceptable cost.

## Likely implementation areas

- Scope data, builders, and execution: `rlm/domains/`, `rlm/core/history.py`,
  `rlm/core/runtime.py`, `rlm/repl_ns.py`.
- Planner schema, prompt, and budget validation: `rlm/prompts/`,
  `rlm/core/prompt_guard.py`, `rlm/config.py`, `rlm/cli.py`.
- Logging/reporting: `rlm/logging/`, trace summaries, and report tests.
- Validation and evaluation: domain/runtime/prompt/trace tests plus `evals/`.
