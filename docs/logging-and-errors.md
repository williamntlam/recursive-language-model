# Logging and errors

## Trajectories

Each successful or failed run that reaches `TrajectoryLogger` writes:

```
.rlm/logs/<YYYYMMDD-HHMMSS>-<8 hex chars>/
  meta.json          # models, limits, query hash, domain stats
  events.jsonl       # one record per iteration / subcall / error
  answer.txt         # written on successful finish (depth 0)
  usage.json         # tokens, cost, iterations, subcalls
  report.html        # static timeline; written after the run (also on abort)
```

Open `report.html` in a browser. It is a self-contained file (inline CSS, no network). The header lists **prompt / completion / total tokens** and **USD cost**. A table lists every OpenAI call (`root_lm`, `llm_query`) with the same fields. Recursion depth is left indent; parent prompt tokens are a bar chart so you can see whether `hist` is rotting.

Regenerate without re-running:

```bash
uv run rlm report .rlm/logs
uv run rlm report .rlm/logs/<run-id>
```

`log_dir` is configurable (default `.rlm/logs`). The directory is gitignored via `.rlm/`.

`meta.json` includes `id`, `query_sha256`, `query_n_chars`, plus extras from the facade:

| Domain | Extra fields |
|---|---|
| string | `context_n_chars`, `context_sha256`, `domain=string` |
| repo | `domain=repo`, `repo` (absolute path) |
| research | `domain=research`, `n_docs` |

Also always: `root_model`, `leaf_model`, `max_prompt_tokens`, `max_instructions`, `max_depth`.

The raw query string is **not** stored in `meta.json` (only its length and sha256).

### Event kinds

| `kind` | When |
|---|---|
| `root_lm` | Parent (or child RLM root) completion: model, prompt_tokens, instruction_count, completion_tokens, latency_s, cost_usd, iteration, depth |
| `repl` | Cell executed: code[:4000], stdout[:4000], error, tokens, instruction_count |
| `parse_error` | No `repl` fence |
| `llm_query` | Leaf call |
| `rlm_query` | Child finished: `child_depth`, `answer_n_chars` |

Child RLMs **share** the parent's logger directory (events interleave; `depth` distinguishes them). `answer.txt` / `usage.json` are written only when **depth 0** finishes successfully. An abort after the logger exists may leave `events.jsonl` without those two files.

### Redaction

`TrajectoryLogger` runs a regex over strings (`sk-` + 8+ URL-safe chars) and replaces matches with `sk-REDACTED`. Nested dicts/lists are walked. This is a backstop — the API key should never have been in `hist` or the container.

## CLI usage footer

On success, stderr:

```
# tokens=<prompt>+<completion> cost=$<usd> iters=<n> subcalls=<n> log=<trajectory dir> html=<trajectory dir>/report.html
```

`cost` is four decimal places, or `$?` if `usage.cost_usd` is `None`.

## Exception map

Defined in `rlm.errors`. All inherit `RLMError`.

| Exception | Meaning | CLI exit |
|---|---|---|
| `PromptBudgetError` | Parent hist would be ≥100k tokens (or over configured `max_prompt_tokens`) | 2 |
| `BudgetExhaustedError` | USD, wall-clock, or `max_iterations` exhausted | 2 |
| `ReplErrorsExhausted` | Too many consecutive REPL/parse errors, or identical-code stall | 3 |
| `InstructionBudgetError` | Composed instructions > 150 (or configured cap) | 4 |
| `ConfigError` | Bad file, unknown key, illegal ceiling, both toml and yaml present | 4 |
| `StartupError` | Missing `OPENAI_API_KEY`, Docker down, missing Dockerfile, REPL socket never appeared | 4 |

`FileNotFoundError` (bad `ask` / `research` / `--context-file` path) is also exit `4`.

Leaf oversize prompts do **not** raise to the CLI: they return `Error: …` into the REPL so the parent can recover.

## Debugging rot

If an answer is wrong, open `events.jsonl` and check:

1. Which slices were grepped/read (code cells).
2. Which `llm_query` / `rlm_query` calls ran (`prompt_tokens` per event).
3. That `prompt_tokens` on parent `root_lm` events stays in the low thousands.
4. That `instruction_count` is **constant** across iterations. If it trends up, instructions are leaking into observations — that is a bug.
5. That the bound corpus never appears in parent messages (the history invariant).
