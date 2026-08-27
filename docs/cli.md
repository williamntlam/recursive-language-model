# CLI

Entry point: `rlm` → `rlm.cli:main` (declared in `pyproject.toml`).

The process loads `.env` first (`rlm.envfile.load_dotenv`), without overriding variables already in the environment.

## Syntax

For `ask` / `research` / `complete`, the user query is everything after `--`. If `--` is missing or the query is empty, the CLI exits `4`. `report` does not take a query.

```
rlm ask <path> -- <query>
rlm research <path> -- <query>
rlm complete --context-file <file> -- <query>
rlm report [path]
```

Examples:

```bash
uv run rlm ask ./pytorch -- "Where is autocast implemented?"
uv run rlm research ./papers -- "Where do these papers disagree?"
uv run rlm complete --context-file haystack.txt -- "Find the needle."
uv run rlm ask ./repo --max-budget 2.00 --leaf-model gpt-5-mini -- "..."
uv run rlm ask ./repo --dry-run -- "preview only"
uv run rlm ask ./repo --planner-enabled -- "Compare the selected implementations."
uv run rlm ask ./repo --config ./rlm.yaml -- "..."
```

## Subcommands

| Command | Bound world | Python equivalent |
|---|---|---|
| `ask <path>` | Local directory as `repo` | `RLM().ask_repo(path, query)` |
| `research <path>` | Directory (or file) as `corpus` | `RLM().research(path, query)` |
| `complete --context-file <file>` | File contents as `context` | `RLM().completion(query, text)` |
| `report [path]` | Write `report.html` for a trajectory | `write_report(resolve_run_dir(path))` |

`report` accepts a run directory, an `events.jsonl` file, or a log parent (default `.rlm/logs`) and picks the latest child. It prints the HTML path on stdout. No API, no container.

There is no `--env local`. The product REPL is Docker. There is no `--api-key` (keys show up in shell history).

For **repo-wide** questions, do not ask the model to `explore` / `rlm_query_batched` one file at a time. That is a stress test of recursion, not a good census. Ask it to grep + `ast` / `measure_ast` in the REPL and `llm_query` only unclear bodies. See the [root README](../README.md) query example.

## Flags

Shared by the root parser and every subcommand:

| Flag | Config key | Notes |
|---|---|---|
| `--root-model` | `root_model` | OpenAI model id for any node with a REPL |
| `--leaf-model` | `leaf_model` | OpenAI model id for `llm_query` |
| `--max-depth` | `max_depth` | Safety cap on nested `rlm_query` (default 16) |
| `--max-iterations` | `max_iterations` | Root loop cells (default 30) |
| `--max-prompt-tokens` | `max_prompt_tokens` | May only go **down** from 99,999 |
| `--max-instructions` | `max_instructions` | May only go **down** from 150 |
| `--max-budget` | `max_budget_usd` | USD cap; unset means unlimited |
| `--timeout` | `max_timeout_s` | Wall-clock seconds for the whole completion |
| `--cell-timeout` | `cell_timeout_s` | Seconds before hung local Python in a cell is killed (default 300) |
| `--log-dir` | `log_dir` | Trajectory parent directory (default `.rlm/logs`) |
| `--verbose` | `verbose` | Print iteration / code / truncated stdout to stderr |
| `--config` | — | Explicit `*.toml` / `*.yaml` / `*.yml`. Skips cwd discovery |
| `--dry-run` | — | Print system prompt + metadata + token/instruction counts. No API, no container |
| `--planner-enabled` | `planner_enabled` | Opt in to deterministic scoping and constrained plan execution for `ask` / `research` |

`--max-prompt-tokens 100000` or `--max-instructions 151` is a config error (exit `4`).

## Dry-run

`--dry-run` still runs on the host. It loads the domain (repo tree, corpus catalog, or string metadata), composes the system prompt, counts tokens and instructions, and prints:

```
=== system prompt ===
...
=== metadata ===
...
prompt_tokens=N instruction_count=M max_prompt_tokens=... max_instructions=...
```

If the composed instruction count already exceeds the cap, it raises `ConfigError` (exit `4`) instead of printing.

With `--planner-enabled`, dry-run additionally prints the scope-manifest record
count and truncation flags plus the planner schema version, token count, and
instruction count. It still makes no model request and starts no Docker container.

## Output

On success:

- **stdout:** the answer string (`FINAL` / `FINAL_VAR` / `answer["value"]`)
- **stderr:** usage footer

```
# tokens=1234+56 cost=$0.0123 iters=4 subcalls=12 log=.rlm/logs/20260820-180000-abcd1234 html=.rlm/logs/20260820-180000-abcd1234/report.html
```

`cost` is `$` plus four decimals, or `$?` if cost is unknown. `subcalls` counts `llm_query` / `rlm_query` (including batches). A large-repo AST census that never left the parent REPL can finish with `subcalls=0`; that is success, not a truncated run. Hundreds of `rlm_query` events usually means the query asked for one child per file.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success (including dry-run) |
| `2` | Budget / timeout / parent prompt-token abort (`PromptBudgetError`, `BudgetExhaustedError`) |
| `3` | Consecutive REPL errors or identical-code stall (`ReplErrorsExhausted`) |
| `4` | User/config/startup: missing query, argparse, `ConfigError`, `InstructionBudgetError`, `StartupError`, missing path, Docker down, missing key |

Argparse's native exit `2` (bad flags) is remapped to **`4`** so `2` stays “budget”.

`--help` returns `0`.

## Query splitting

`rlm.cli._split_argv` splits on the first `--`. The left side is parsed as flags; the right side is joined with spaces into one query string. Quotes are handled by the shell before this split.
