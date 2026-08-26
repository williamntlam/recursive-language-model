# Scoped research and rendered final output

## Status

Proposed implementation specification. This is one product change split into
three independently releasable workstreams; land them in the listed order.

## Problem

The 2026-08-25 Transformers research traces exposed three related failure
modes:

1. Root and child models generated very large, all-in-one REPL programs. Small
   Python mistakes then wasted turns and inflated parent history before any
   evidence was produced.
2. A child asked to survey an entire repository repeatedly invoked global
   `repo.grep` calls (including a per-file loop). It consumed its 300-second
   cell timeout and returned lower-quality findings than a targeted inspection.
3. The finalization API silently coerced arbitrary values to strings. A Python
   dictionary therefore became the user-visible answer, leaking internal plan
   data and bypassing deliberate report rendering.

The runtime must preserve its read-only, source-grounded model: deterministic
inspection first, language-model calls only for bounded ambiguity, and final
answers assembled inside the REPL.

## Goals

- Make research execution proceed in small, observable stages.
- Give children an explicit, enforceable set of source spans instead of a
  repository-wide search task.
- Require a deliberately rendered string as the terminal answer.
- Preserve prompt-token and instruction ceilings, Docker isolation, and normal
  non-research `FINAL("...")` use.

## Non-goals

- Do not add a general coding shell, write access, or host credentials to the
  REPL.
- Do not require an LLM judge on every completion.
- Do not guarantee factual correctness from answer shape alone.
- Do not change the existing leaf/child size thresholds in this work.

## Workstream A — staged research strategy

### Required behavior

Replace, rather than append to, prompt wording as necessary to remain within
the instruction ceiling. Root, repo, corpus, and child-facing guidance must
describe this sequence:

1. Run a small inventory cell: count/filter paths and produce compact metadata
   records. Do not delegate in that cell.
2. Use deterministic Python (`ast`, regex, counts, and measured spans) to
   classify the inventory and select only the records whose semantics remain
   ambiguous or which are needed as representative evidence.
3. Read or ask about selected fit-sized spans. Create a child only for a
   selected span that remains oversized after chunking.
4. Reduce records and subcall results into `report_text: str`, then finalize
   that name.

The guidance must explicitly discourage a single cell that both inventories a
large tree, performs a global semantic survey, launches children, and formats
the answer. It should tell the model to execute the inventory before writing
the next stage and to repair an error with a small cell.

### Acceptance criteria

- Prompt tests assert the staged guidance is present without exceeding 150
  instructions.
- A scripted runtime test demonstrates an inventory cell followed by a
  selection/read cell and a final render cell; only compact inventory output is
  appended to history.
- Add an evaluation case based on a multi-file repository question. Its rubric
  rewards a bounded citation set and penalizes broad, repeated repository
  scans. It must be opt-in like the existing Transformers judge evaluation.

## Workstream B — scoped child research

### Public API

Add an optional `targets` argument to domain exploration methods:

```python
repo.explore(question: str, targets: list[dict] | None = None) -> str
corpus.explore(question: str, targets: list[dict] | None = None) -> str
```

Each repository target is `{ "path": str, "start": int | None,
"end": int | None }`; a corpus target is `{ "id": str, "start": int |
None, "end": int | None }`. Reject empty lists, malformed records, paths
outside the bound repository, unknown corpus IDs, and inverted ranges before
starting a child. `targets=None` retains the existing API and behavior for
backward compatibility, but prompts should prefer a non-empty target list.

### Child boundary

When targets are provided, create the child with a scoped domain view rather
than merely mentioning paths in its query:

- `read`, `file_text`, `measure`, `ask`, and equivalent corpus reads may access
  only the target paths/IDs and their declared ranges.
- `files`, `glob`, `tree`, `grep`, and search results are filtered to the
  target set. A request that would escape the target set returns a clear
  `ValueError`/error string naming the scope, not a partial global result.
- The child query includes a compact target manifest and directs it to cite
  only those spans. Source bodies remain in the REPL, never in the parent
  prompt.
- Untargeted children retain the current full-domain view; this compatibility
  path must be visibly marked in trace metadata so it can be measured and
  deprecated later if warranted.

Targets are not a substitute for sizing: a target larger than the leaf limit
must still be chunked or handled by the scoped child according to existing
planning rules.

### Observability

Add only compact metadata to `repo.explore`/`corpus.explore` trace events:
`scoped` (boolean), `target_count`, and a digest of the normalized target
manifest. Do not capture paths or source content under metadata capture.
Content capture may store the child query under its existing rules.

### Acceptance criteria

- Unit tests cover normalization, invalid targets, range enforcement, and
  filtering of each read/search-style domain method.
- A child invoked with two targets cannot grep, read, or measure another file,
  including via a broad glob.
- A child can inspect and cite both permitted targets and return its string to
  the parent.
- Trace-summary-compatible tests verify scoped-call metadata and preserve the
  current trace schema unless a versioned schema change is necessary.
- Update REPL, runtime, domain, and tracing documentation with the new API and
  boundary.

## Workstream C — rendered final-answer contract

### Required behavior

`FINAL(text)`, `FINAL_VAR("name")`, and the legacy `answer` completion path
must accept only `str` values. They must not apply `str(value)` to mappings,
lists, numbers, or custom objects.

For a non-string value, leave the completion unfinished and raise a recoverable
`TypeError` that includes the received type and this remediation:

```python
report_text = render_records(records)
FINAL_VAR("report_text")
```

`FINAL_VAR(name)` retains its bare-name convenience and missing-name help. An
empty string remains subject to the existing final-answer behavior.

Update prompts to make the intended pattern explicit: structured records are
for intermediate storage; format them into a concise prose/table/Markdown
string only at finalization. Do not prescribe a universal report schema:
users' questions determine whether the rendered string is prose, a table, a
JSON string, or another textual format.

### Acceptance criteria

- Existing string-based finalization tests continue to pass.
- New namespace and runtime tests prove `FINAL({"a": 1})`,
  `FINAL_VAR("records")` where `records` is a list/dict, and non-string
  `answer["value"]` do not complete the run and emit the remediation.
- A subsequent cell can render the same records to `report_text` and complete
  normally; this error counts toward the existing consecutive-REPL-error
  policy.
- No final answer can be a Python `repr` produced by implicit coercion.

## Rollout and validation

1. Land Workstream C first. It is local, backward-compatible for documented
   usage, and blocks the most visibly bad terminal output.
2. Land Workstream A with its prompt and evaluation coverage. Compare repeated
   trials on the Transformers case before and after; record turns, subcalls,
   timeout count, answer citations, and cost.
3. Land Workstream B after the scoped-view tests and Docker IPC path are ready.
   Run unit tests plus Docker tests because the child boundary crosses the host
   and container RPC boundary.

Success for the original failure case is: no root syntax/recovery churn from a
monolithic cell, no child global scan, no child cell timeout, a concise string
answer, and source citations for the claims it makes.

## Likely implementation areas

- Prompts and history nudges: `rlm/prompts/root.md`, `repo.md`, `research.md`,
  `rlm/core/history.py`.
- Domain scope and child dispatch: `rlm/domains/repo.py`,
  `rlm/domains/corpus.py`, `rlm/repl_ns.py`, `rlm/core/runtime.py`, and Docker
  IPC/environment plumbing.
- Final contract: `rlm/repl_ns.py`, runtime-loop tests, and REPL documentation.
- Observability: `rlm/logging/trace.py`, trajectory/report tests, and tracing
  documentation.
