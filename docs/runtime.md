# Runtime

The runtime (`rlm.core.runtime.Runtime`) owns the loop, not the model. It builds the prompt, calls the root LM, parses `repl` fences, executes in Docker, truncates observations, guards every send, and spawns children.

## Root loop

```
payload ← compose_system_prompt(domain) + exposed methods + user query + extra_instructions
hist    ← [system(payload), user(metadata ‖ query)]
env     ← Docker container, persistent namespace
loop i in 0 .. max_iterations-1:
    budget.check()
    assert_sendable(hist, payload)          # <100k tokens, ≤150 instructions
    lm      ← root_model.complete(hist)
    code    ← last ```repl``` fence
    obs     ← env.execute(code)
    hist    ← hist ‖ assistant(code cell) ‖ user(truncated stdout)
    compact older pairs; if FINAL set: return it
abort: max_iterations without FINAL_VAR
```

Startup refusals:

- Static system+metadata already `>= 100_000` tokens → `PromptBudgetError`.
- Composed instructions `> max_instructions` → `InstructionBudgetError` (CLI exit 4).

## Selectable execution architectures

`ask` and `research` accept `--architecture direct|planned|planned_waves` (or
`architecture = "direct"`, `"planned"`, or `"planned_waves"` in configuration). `direct` is the
default root-loop workflow. `--planner-enabled` and `planner_enabled = true`
remain compatibility aliases for `planned`.

Each architecture implements the shared `ResearchArchitecture` interface and
returns a prepared execution boundary. This lets benchmarks select an
architecture without branching the CLI, API, or `Runtime`; future architectures
must retain the same isolation and budget contracts.

### `planned`: opt-in deterministic planning

Planning is an execution boundary, not a second unconstrained research agent:

```
deterministic metadata / AST / regex discovery
    → capped ScopeManifest (records, routes, digest, truncation flags)
    → planner JSON selects record IDs only
    → runtime validates routes and limits
    → fit record: bounded leaf; oversized record: target-enforced child
    → compact cited findings
    → source-free root renderer
```

The planner sees the question, compact manifest, budget summary, and schema;
it never supplies paths, spans, code, models, or budget overrides. The runtime
resolves its IDs. A `fit` record must use a leaf; an oversized record must use
a scoped child. The final renderer receives only the resulting findings in a
string context—no `repo`, `corpus`, or original workspace.

Malformed or failed planner output falls back to the normal staged REPL, but
the REPL is restricted to all records in the already-built manifest. It does
not silently regain full-domain access. Planning events record only counts,
route totals, digests, and truncation/cap metadata.

### `planned_waves`: complete metadata coverage over time

`planned_waves` writes a complete local, source-free census, then greedily groups
record metadata into token-safe planner shards. Rejected shards are marked
`unplannable`; they never reopen the full repository. Selected work produces
append-only coverage and finding artifacts, then compact findings are reduced in
bounded, source-free batches before final rendering.

## Code extraction

`extract_repl_code` matches ```` ```repl ```` first (closed or unclosed), then ```` ```python ```` / ```` ```py ````, then an unlabeled fence (skipping json/markdown/shell), then a bare `repl` / `python` heading. It returns the **last** matching labeled block. No executable cell → user reminder, `parse_error` with a text preview, and a consecutive-error tick.

## Stall and error abort

| Condition | Result |
|---|---|
| Same code cell twice in a row, then a third identical (`identical >= 2`) | `ReplErrorsExhausted` |
| `max_consecutive_errors` parse or REPL exceptions (default 5) | `ReplErrorsExhausted` |
| `max_iterations` without `FINAL*` | `BudgetExhaustedError` |

A successful cell resets the consecutive-error counter.

## History policy (anti-rot)

This is the subsystem naive agent ports get wrong.

Each observation appended to `hist` is truncated stdout (and stderr). A trailing
expression is shown as a **compact repr** (long strings become a length/hash
preview, not the body). Empty cells get a short hint instead of silence.

The parent stores **executed code cells**, not the model's surrounding prose.

After `HIST_KEEP_RECENT` (**4**) code/observation pairs, older pairs are replaced
with stubs (`compacted cell` / `compacted observation`). Values stay in the
REPL. If the next parent send would exceed `PARENT_TOKEN_NUDGE` (**1500** tokens),
the observation includes a reminder to grep/`ast` in the REPL, use
`llm_query` / `repo.ask` on tight slices, and `rlm_query` only if a file is
still too large.

Never appended:

- the full `context` / repo dump / document bodies
- full file contents (they stay in variables)
- full sub-call transcripts (only the child **answer string** returns into a variable; the parent sees it if the model **prints** it, still truncated)
- the model's pre-fence reasoning (only the `repl` cell is kept)

If `hist` itself would be 100k tokens or more on the next parent call, **do not send**. Do not summarize the corpus. Raise `PromptBudgetError` (CLI exit 2). Observation truncation exists so this abort should be rare; if it is common, lower `max_observation_chars`. Compacting the source data is how rot re-enters.

Helper for tests: `hist_contains_context(hist_text, context)`.

## Prompt guard

Module: `rlm.core.prompt_guard`. `LMClient.complete` is **not** responsible for the policy. The runtime wraps every send. `FakeClient` raises `AssertionError` if a ≥100k payload reaches it, so a missed guard is a red test.

### Token counting

- `tiktoken` encoding `cl100k_base`.
- Count the **exact message list** about to be sent (roles + contents + 3 tokens of framing per message).
- Do **not** count bound REPL `context` unless it was copied into those messages.
- Legal: `count_tokens(messages) < 100_000` **and** `<= max_prompt_tokens`.
- Illegal: `>= 100_000` or `> max_prompt_tokens`.
- Batched calls: each prompt is guarded on its own. A 200-item batch of 10k-token prompts is 200 legal calls, not one 2M-token call.

| Caller | Oversize behavior |
|---|---|
| Parent / root loop | Do not call the LM. `PromptBudgetError`. Persist trajectory. |
| `llm_query` / `rlm_query` | Return an error **string** into the REPL (`Error: prompt is N tokens; max is 99999. Slice the argument.`). One oversize leaf does not kill the batch. |

100k is a **backstop**, not a target. The parent should sit in the low thousands of tokens. Leaves should receive only the snippet they need.

### Leaf vs child (`repo.ask` / `corpus.ask`)

`route_read_subcall` in `rlm/core/history.py`:

- Slice **≤ `ASK_LEAF_CHARS` (24,000)** → `llm_query` (`gpt-5-mini`).
- Larger → `rlm_query` with the same `repo` / `corpus` bound. The child prompt names the target; it does not embed the file.

The REPL also exposes `measure`, `measure_ast`, and `plan_reads` (and `repo.measure` / `repo.plan`). `n_tokens` is `(n_chars + 3) // 4` — tiktoken is not in the image. `plan_reads` returns `n_fit`, `n_child`, `n_chunks`. Use `n_child` (or split into `n_chunks` leaves); do not derive cardinality from how full the parent window is.

See [REPL](repl.md) and [Domains](domains.md).

This limit is on **input context of an LM call**, not on REPL memory and not on the final answer. `FINAL_VAR` may return a long string assembled in the container. That string is not prompt text unless a later `llm_query` tries to send it.

### Instruction counting

An **instruction** is a discrete directive the model is expected to obey. Observations, model-written code, stdout, and corpus/repo *data* are not instructions.

Count **1** for each of:

1. Each numbered or bulleted list item in system and developer prompts.
2. Each exposed REPL builtin or domain method (`llm_query`, `repo.grep`, …). Listed twice still counts once.
3. The user query (one unit).
4. Each `extra_instructions` string.

Do **not** count stdout, truncation notices, hashes, code cells, or manifest/catalog/tree **data**.

The composed set is computed **before the first token is sent** and must not grow during the session. New observations must not add instructions. Exceeding 150 → `InstructionBudgetError`. Do not drop rules silently to fit.

Exposed-method catalogs live in `rlm/prompts/catalog.py`.

## Recursion

### `llm_query` (leaf)

`Runtime.leaf_complete`:

1. `budget.check()`; on exhaustion return `Error: …` rather than raising (so a batch can continue).
2. Messages = leaf system prompt + user prompt.
3. `assert_sendable(..., as_parent=False)`.
4. Complete with `leaf_model` (or the `model=` override).
5. Record tokens/cost/subcalls under a lock (batches are concurrent).

### `rlm_query` (child RLM)

`Runtime.child_rlm`:

1. `child_depth = depth + 1`.
2. If `child_depth > max_depth`: degrade to `llm_query` **only if** the prompt is under 100k; else return `Error: depth cap; slice smaller…`.
3. Else spawn a new `Runtime` with `budget.inherit()`:
   - **repo / research:** same workspace and domain. A child with `targets` receives an enforced path/ID and span view for reads and searches; untargeted children retain the full-domain compatibility view. The prompt is the child's *query* and file bytes never enter the parent prompt.
   - **string:** the prompt is bound as `context` with a fixed child query (“Execute the task described in the `context` variable…”).
4. Own container (product path) or own `FakeEnv` (tests). Each child clones `repo` / `corpus` so `_query_fn` is not shared across concurrent batches.
5. Fold child spent USD / tokens / iterations / subcalls into the parent budget.
6. Return `result.response` (not the child trajectory dump).

Child extra instructions and verbose flag are inherited. `max_budget_usd` / `max_timeout_s` on the child config are the **remaining** values.

### Batches

`Runtime.batched` uses `ThreadPoolExecutor` with `min(max_concurrent_subcalls, len(prompts))` workers. Exceptions become `Error: …` strings in that index.

## Budgets

`rlm.core.budgets.Budget`:

- Optional `max_usd` and `max_timeout_s` (deadline = monotonic start + timeout).
- `check()` raises `BudgetExhaustedError` if remaining time or USD is `<= 0`.
- `record(LMResponse)` estimates USD from a small price table (`PRICES_PER_MILLION` in `budgets.py`) and accumulates tokens.
- `inherit()` gives the child remaining timeout and remaining USD, with spent reset to 0.

Checked at the start of each root iteration and each subcall. After recording a completion, `check()` runs again so an over-budget last call still aborts the next step.

Default models in the price table: `gpt-5`, `gpt-5-mini`, `gpt-5-nano`, `gpt-4.1`, `gpt-4.1-mini`, `gpt-4.1-nano`, `gpt-4o`, `gpt-4o-mini`. Unknown ids use `(1.00, 4.00)` per million (input, output).

## Verbose mode

When `verbose=True`, each iteration prints to stderr:

```
--- iteration i depth=d tokens=N inst=M ---
<repl code>
<truncated observation>
```

The CLI sets verbose when `--verbose` is passed; otherwise it follows config (CLI currently forces `verbose=True` only if the flag is set, else `None` so the file/default applies).
