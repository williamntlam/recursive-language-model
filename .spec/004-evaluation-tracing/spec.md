# 004 — Evaluation-Ready Recursive Execution Tracing

**Status:** Draft  
**Date:** 2026-08-25  
**Owner:** William Lam  
**Depends on:** 001 runtime and trajectory logging; 002 comprehensive evaluation program

---

## 1. Purpose

Make every RLM run inspectable as a correlated execution trace, so evaluations can measure *how* an answer was obtained as well as whether it is correct. The trace must cover root-model turns, recursive RLM children, leaf-model calls, REPL cells, callback ingress, batches, and RLM-provided source-inspection tools. It must remain useful after an abort and must not move source data or credentials out of the constrained REPL.

The operational loop this enables is: **mine traces → identify and classify a
failure → minimize it into a versioned evaluation → improve the runtime,
prompt, or routing policy → rerun the same pinned evaluation and compare
traces.** A trace is therefore a first-class research artifact, not merely a
debug log or a report input.

The existing trajectory is the foundation, not an asset to discard. It already records a directory per run, model calls, REPL cells, parse failures, usage, errors, and an offline HTML report. Its flat events cannot reliably express which cell caused a callback, which batch item caused a failure, or which source operations supported a final answer. This specification evolves it into a stable, machine-evaluable trace contract.

## 2. Scope and non-goals

In scope:

- a versioned JSONL event schema with causal IDs and span lifecycle records;
- correlation across host runtime, Docker REPL, and concurrent callbacks;
- summary metrics and deterministic trace-policy checks for evaluation cases;
- a repeatable trace-mining and failure-promotion workflow;
- a backwards-compatible static report that exposes the call/tool tree; and
- opt-in, bounded retention of safe diagnostic previews.

Out of scope:

- a distributed tracing vendor, network exporter, telemetry SDK, or live UI;
- tracing arbitrary Python or operating-system calls made by REPL code;
- recording raw prompts, full model outputs, bound source, tool arguments that contain source, API keys, or unrestricted REPL memory snapshots; and
- turning the read-only REPL into an agent shell or allowing evaluators to replay side-effectful operations.

“All tool calls” means all RLM-provided tools exposed through the REPL namespace (for example repository/corpus search, read, AST/measurement, planning, and `llm_query`/`rlm_query` helpers). Python builtins and arbitrary library calls are not product tools and cannot be completely or safely traced.

## 3. Trace model

Each trajectory directory gains `trace.jsonl` and `trace-summary.json`. The legacy `events.jsonl` remains during the migration and is derived from the same emissions where practical. `meta.json` gains `trace_schema_version: 1` and a random `trace_id`; the existing run ID remains the user-facing identifier.

Every trace record has the following required envelope:

| Field | Meaning |
| --- | --- |
| `schema_version` | Integer schema version, initially `1` |
| `trace_id`, `span_id`, `parent_span_id` | Opaque random IDs; root has no parent |
| `event` | `span_start`, `span_end`, or `span_event` |
| `seq` | Per-trace monotonically increasing integer, allocated under a lock |
| `ts_unix_ms` | Host wall-clock timestamp for ordering across processes |
| `depth` | RLM recursion depth |
| `name`, `kind` | Stable operation name and category |

`span_start` and `span_end` share a span ID. An end record includes `status` (`ok`, `error`, `cancelled`, `blocked`), `duration_ms`, and a bounded, classified error when applicable. A trace writer must flush each JSONL record; an unterminated start span denotes interruption, not success.

The initial stable kinds are:

| Kind | Name examples | Parent |
| --- | --- | --- |
| `run` | `rlm.run` | none |
| `model` | `root.complete`, `leaf.complete` | run, cell, or callback |
| `repl` | `repl.cell` | run/child run |
| `callback` | `llm_query`, `rlm_query` | invoking REPL cell |
| `batch` | `llm_query_batched`, `rlm_query_batched` | callback/cell |
| `tool` | `repo.grep`, `repo.read`, `corpus.search`, `measure_ast` | REPL cell |
| `runtime` | `prompt_guard`, `history_compact`, `parse` | run or model turn |

Model spans carry model name, API family, requested model, input/output token
counts, estimated cost, latency, retry count, and prompt/output content
references. REPL spans carry the code digest and length, output/error lengths
and digests, final-present flag, and timeout outcome. Tool spans carry a stable
tool name, a safe structured argument summary (never raw source text), result
count/size/digest where available, and outcome. Callback and batch spans carry
requested model, prompt-count or prompt-size summaries, child depth when
relevant, and slot outcomes. Child `rlm.run` spans are children of the specific
`rlm_query` callback—not merely events at `depth + 1`.

## 4. Correlation and instrumentation design

The runtime creates the root run span before environment construction. Before executing a REPL cell it allocates a cell span ID and sends it in the IPC `exec` request. The REPL server installs that ID as the active cell context. `RpcHandler` includes the ID and a per-cell callback sequence in every callback payload, so `CallbackServer` can create a callback span with the correct parent even when batch workers complete out of order.

The REPL namespace receives trace-aware wrappers/proxies for the public RLM tools. A wrapper emits tool start/end records to a per-cell buffer, preserving the active cell ID and local order. The REPL returns that bounded buffer with the cell result; `DockerEnv.execute` exposes it on `Observation`; the host writer assigns global sequence numbers and appends it to `trace.jsonl` before ending the cell span. `FakeEnv` uses the same wrapper API so unit tests cover the contract without Docker.

Instrumentation must be observational: it cannot alter tool return values, tool exceptions, timeout behavior, batching alignment, prompt guard decisions, or access controls. Trace-emission failure is fail-open for the requested RLM operation, except an inability to create the configured log directory before a run starts, which retains current startup behavior.

## 5. Capture policy, data minimization, and security contract

Every model/callback span records the requested subagent model, parent cell,
depth, input and output token counts, cost, latency, status, and a digest and
length for its request and response. This is sufficient to identify unused,
duplicated, unexpectedly expensive, or excessive subagent calls in every
trace, including batched calls and failures.

Capture has two explicit local-only profiles:

| Profile | Stored in `trace.jsonl` | Content artifacts |
| --- | --- | --- |
| `metadata` (default) | Counts, timings, model, status, safe summaries, and content digests/lengths | None |
| `content` (explicit opt-in) | The same metadata plus opaque `prompt_artifact` / `output_artifact` references | Redacted, size-capped request and response files under the run directory |

The `content` profile records the exact prompt sent to each root or leaf model
and the returned visible output, including each recursive subagent's requested
task and final output. It must preserve the parent span and model-call ID, so a
miner can retrieve the request/output pair from the causal call tree. Prompt
and response artifacts are content-addressed within the run, deduplicated when
identical, and have a manifest containing byte length, SHA-256, truncation
state, and redaction state. The trace never inlines those artifacts, keeping
the event stream practical to parse.

`metadata` is the normal product setting because child prompts and responses
can contain source slices. `content` is intended for controlled local
development or evaluation fixtures; enabling it is an informed retention
choice, not an implicit consequence of verbose logging. It must be disabled
by default, documented in CLI/configuration, visibly marked in `meta.json` and
the report, and rejected when writing to a non-local/exported destination.
It must still redact known secrets, cap individual and total artifact bytes,
and never record environment variables or credentials. Redaction is a
backstop, not permission to capture a production corpus.

Default records contain hashes, counts, paths only when the current trajectory already permits them, and bounded semantic-free summaries. They never contain the raw user query, model prompt/completion, `context`, document/file contents, environment variables, callback payload text, or credentials. Existing secret redaction remains a backstop and is applied recursively to all records.

Code previews remain governed by the existing capped `repl` trajectory event; they are not copied into the new trace. A future explicit debug-preview mode may add further bounded data only with a documented retention policy and test coverage. Report HTML must continue to escape every trace-derived value.

## 6. Evaluation interface

At root completion or abort, write a deterministic `trace-summary.json` from `trace.jsonl`; do not make evaluators scrape HTML. It includes schema version, completion status, trace/run IDs, counts and durations by kind/name/status, root turns, cells, leaf calls, child calls, batches and batch slots, tool calls, max recursion depth, prompt/instruction maxima, token/cost totals, timeout and error categories, and a source-operation inventory of tool names/counts only.

The evaluation harness consumes the summary plus a validated, streaming parser for `trace.jsonl`. Cases may declare *reported* or *enforced* trace assertions:

- required or forbidden operation kinds/tool names;
- maximum calls, cells, depth, prompt tokens, instructions, cost, and latency;
- no error/timeout spans; and
- evidence predicates such as a relevant bounded search followed by a read.

These assertions judge observable product behavior, never an exact code string or a single prescribed route. A trace missing required schema fields, containing duplicate sequence numbers, orphaned non-root spans, or claiming a completed span without an end is an invalid trajectory and produces a distinct harness failure. Correctness remains independently graded according to spec 002; trace efficiency initially reports rather than gates new cases.

## 7. Compatibility, reporting, and retention

`events.jsonl`, `usage.json`, `error.txt`, and current report commands remain supported. During the first release, both old event kinds and trace records are written; report rendering prefers `trace.jsonl` when present and otherwise uses legacy events. The report adds a compact expandable call tree and tool summary, without embedding prompts or source data. `rlm report` must render both formats offline.

Trace files live under the existing gitignored `.rlm/logs/` retention model. No automatic upload, aggregation, or cross-run linking is introduced.

## 8. Trace mining and evaluation promotion

Trace mining is an explicit, human-reviewable workflow. A future local
`rlm traces` command (or an equivalent library interface) must scan one or
more trajectory directories and emit a compact, deterministic index from
`trace-summary.json` plus validated trace fields. It groups runs by runtime /
prompt / model configuration and exposes failure signatures without reading
raw source or asking another model to interpret the trace by default.

Initial signatures include: incorrect or missing final answer as supplied by
the evaluator; parse/repeated-cell/REPL/tool/model/timeout/budget failure;
unusually high calls, depth, token, cost, or latency; missing expected source
operation; and suspicious route patterns such as a child spawned without a
preceding bounded inspection. The index retains trace/run ID, case ID and
version when known, source/config revision, model names, metric values, and
the minimal set of span IDs needed to open the causal path in the report.

Promoting a mined failure into an evaluation requires a reviewer to:

1. select the actual failure signature and causal span path;
2. redact and minimize the source into a distributable fixture or deterministic
   generator, never copying the production trace wholesale into the case;
3. declare the desired outcome and independently checkable facts or a bounded
   rubric;
4. attach trace expectations as initially reported metrics, unless the failure
   is a hard safety/policy violation; and
5. pin the case, source/generator revision, runtime configuration, and baseline
   trace IDs before comparing an improvement.

An improvement is accepted only when it is rerun on the pinned regression
case and the relevant broader suite. Results must retain before/after trace
summaries and explain any correctness, cost, or route trade-off. The system
must not train or automatically rewrite prompts from raw traces; trace mining
proposes evidence for a reviewed evaluation and change.

## 9. Delivery sequence

1. Add trace types/writer, schema validation, root/model/REPL spans, and compatibility tests.
2. Propagate cell context through Docker and FakeEnv; trace callback, child, batch, guard, parse, and abort outcomes.
3. Add wrappers for every documented REPL namespace tool and tests proving wrappers preserve returns/errors and do not record source content.
4. Generate summaries, update the static report/docs, and add fixture-based parsers for incomplete and legacy trajectories.
5. Add a small set of opt-in evaluation cases that consume trace assertions; promote efficiency thresholds only after reviewed baseline data exists.

## 10. Acceptance criteria

The feature is complete when:

1. A successful recursive/batched run yields a valid, causally linked trace from root run through each cell, callback, leaf/child model call, and public source tool operation.
2. Failed guards, model calls, tool calls, parse errors, REPL errors, timeouts, and aborts have classified end states and leave a readable partial trace.
3. Concurrent batch work preserves parent/slot association and a unique total event order without relying on completion order.
4. Metadata traces exclude raw source, prompts, query text, and credentials;
   opt-in content traces store only redacted, size-capped local artifacts with
   explicit capture metadata; HTML safely escapes untrusted data.
5. Existing trajectory consumers and `rlm report` still work for legacy runs.
6. Deterministic tests cover schema, correlation, data minimization, partial runs, batch alignment, Docker IPC propagation, and evaluator assertions; no test requires a live model call.
7. At least one opt-in evaluation reports trace-derived efficiency/evidence metrics alongside outcome quality, without making a brittle ideal path a mandatory correctness condition.
8. A reviewed mined failure can be linked from its trace ID and causal span path
   to a minimized, versioned regression evaluation, and a before/after rerun
   retains comparable trace summaries.
9. A content-capture test proves that a leaf and recursive subagent request,
   output, token use, model, and causal parent can be recovered from a single
   local trace, while the default metadata profile writes none of those raw
   content artifacts.
