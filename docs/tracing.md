# Execution tracing

Every RLM trajectory contains a machine-readable, local execution trace:

```text
.rlm/logs/<run-id>/
├── trace.jsonl          # append-only causal span records
├── trace-summary.json   # deterministic evaluation metrics and validation
├── report.html          # offline call tree and legacy trajectory report
└── artifacts/           # only with trace_capture = "content"
```

For cross-run REPL diagnosis, `.rlm/repl_errors.jsonl` sits beside the default
`logs/` directory. It is a bounded, redacted index of startup, execution, and
cell failures that links back to the owning trajectory; it does not retain
prompts, source content, or REPL code.

`trace.jsonl` is schema version 1. Each record has a trace/span/parent ID, a
locked monotonic sequence number, timestamp, depth, kind, and lifecycle event.
It records root and leaf model calls, recursive runs, callbacks, batches, REPL
cells, and public source-inspection tools. Interrupted spans intentionally
remain without an end record, preserving partial diagnostic evidence.

The default `trace_capture = "metadata"` stores only counts, timings, costs,
models, statuses, lengths, and digests. It never stores prompts, model output,
source content, callback payloads, or credentials. Set
`trace_capture = "content"` only for controlled local debugging: it adds
redacted, capped prompt/output artifacts under the run directory.

Scoped `repo.explore` / `corpus.explore` callbacks additionally record only
`scoped`, `target_count`, and a digest of the normalized target manifest. Paths,
IDs, and source text are not included in metadata capture.

Use `rlm report <run>` for the offline HTML view, or `rlm traces [log-dir]` to
emit a compact deterministic JSON index without reading artifacts.

The report starts with a static SVG call-graph overview: boxes are spans and
edges follow `parent_span_id`; repeated leaf tool calls are grouped by parent,
operation, and status. The expandable causal tree below it shows safe
operational details (status, duration, token counts, cost, model, result sizes,
and digests). Input and output panels appear only when the run used
`trace_capture = "content"`; they read the capped, redacted local artifacts.
