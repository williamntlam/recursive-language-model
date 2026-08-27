# Concepts

## What this project is

An **RLM** here is not a trained model. It is an inference-time wrapper around OpenAI with the same external type as a normal completion:

```
RLM : (query: str, context: Context) → response: str
```

`Context` may be a huge string, a local repository, or a folder of documents. The caller does not chunk it. The runtime binds it as data in a persistent Python REPL running **inside Docker**. The root model (`gpt-5` by default) never receives that blob. It receives:

- a short **manifest** (length, hash, tree or catalog preview)
- the user **query**
- its own previous code cells
- **truncated** REPL stdout/stderr

It writes Python. That Python peeks and slices the bound data, stores intermediate results in variables, classifies with `ast` when it can, and calls `llm_query` / `repo.ask` only on snippets that already fit **and** that code cannot decide. `rlm_query` / `repo.explore` run when a file or document is **still too large** for one leaf. The parent does not read file bodies into chat. The final answer can be a long string sitting in a REPL variable (`FINAL_VAR`), so output length is not bounded by the root window.

v0 is **read-only**. It ingests and understands. It does not edit, test, or commit.

## Why not bigger windows, RAG, ReAct, or a coding agent

| Approach | Failure |
|---|---|
| Bigger context windows | Cost grows linearly; **context rot** still appears as density grows |
| Compaction / rolling summaries | Lossy. Early details that later become load-bearing disappear |
| RAG / BM25 over the prompt | Retrieval is a guess. Misses dense aggregation and pairwise reasoning |
| ReAct + tools + sub-agents | Observations are *verbalized* into the parent chat. The root still fills up |
| Coding agents (Claude Code, Codex, Cursor, …) | They already grep large trees. They still guess when they did not look, compact the session, and mix **this repo** with pretrained library memory. Better for **patches**. Weaker as a frozen, cited census |

The load-bearing difference versus “an agent with code + sub-agents”:

1. **The prompt lives in the environment, not in `hist`.** The root is not given `P`.
2. **The answer can live in a variable.** `FINAL_VAR("name")` returns a string stored in the REPL.
3. **Recursion is symbolic.** Sub-calls happen *inside Python* (loops, maps, batches), not as a handful of English tool traces.
4. **Children are sized from the span, not from leftover parent window.** `measure` / `plan_reads` answer “would this slice overflow a leaf?”, not “the parent still has 98k tokens.”

A scaffold that (a) puts `P` in chat, (b) verbalizes a few `sub_llm` calls, and (c) compact-summarizes when full is **not** an RLM.

Coding agents **can** scan a huge tree if they write an `ast` walker. This runtime **requires** the source to stay in the REPL and caps every send. That is the product: ingest/understand brownfield code without stuffing it into a window. Spec-driven development can use a cited RLM plan as input to an editor agent; the RLM is not the editor.

## Two failure modes this system is built against

**Hard window limits.** A 100k–1M token window still cannot hold a mid-size monorepo or a multi-paper literature review.

**Context rot.** Even *within* the window, quality degrades as prompts get longer and denser. Needle-in-a-haystack scores hide this. Tasks that require dense access — aggregating facts, tracing a bug, synthesizing a literature — degrade much earlier.

## Two token accounts

Do not mix these:

| Account | Calculable? | What it is |
|---|---|---|
| **Workload** | Yes | Sum of file / span characters (`repo.files()`, `measure_ast`). Disk, not prompt |
| **Parent `hist`** | Yes, each turn | System + query + recent cells + truncated stdout. Independent of repo size |
| **Leaf / child input** | Yes, per span | `measure` / `ASK_LEAF_CHARS` (24k chars ≈ 6k tokens) |
| **Session USD / all API tokens** | No | Adaptive. Cap with `max_budget_usd` / `max_timeout_s` |

The parent never grows by repo size. Children do not pour their hist into the parent — only a `FINAL` string, and only if printed (still truncated).

## Product invariants

These are not suggestions. Config may **lower** the numeric ceilings; it cannot raise them.

1. Bound corpus/repo text **never** appears in parent `hist`.
2. Every OpenAI send has `count_tokens(messages) < 100_000`.
3. Every send has composed `instruction_count ≤ 150`. Extra rules mid-run are a bug.
4. An oversize `llm_query` returns an error **string** into the REPL. The parent must slice. The API is not called.
5. `OPENAI_API_KEY` never enters the container. The container has no public internet.
6. No Docker daemon → fail at startup. Do **not** exec on the host.
7. A child RLM inherits **remaining** USD / timeout, not the original totals.

## Recursion and routing

Depth is however many nested RLMs a **leftover oversized piece** needs, not a fan-out of one child per file.

- `measure(text)` / `measure_ast(source)` / `plan_reads(spans)` — `n_chars`, estimated `n_tokens` (~4 chars/token), `route` (`fit` or `child`), `n_chunks`. No bodies in the return value for `repo.measure`.
- `llm_query(prompt)` — one plain completion. No REPL. Cheap (`gpt-5-mini` by default). Use on a tight snippet that already fits **and** that code cannot classify.
- `rlm_query(prompt)` — spawn a child RLM with its own REPL and Docker container. Use when a file or document is **still too large** for one leaf. In `ask` / `research`, the child inherits the same `repo` / `corpus`. In string `completion`, the prompt is bound as the child's `context`.
- `repo.ask` / `corpus.ask` — under **24,000 characters** → leaf; larger → child RLM (`ASK_LEAF_CHARS` in `rlm/core/history.py`).
- Parent work: grep / `ast` / counts in the REPL. Fan out `llm_query_batched` on unclear `fit` slices. `n_child` is how many oversized spans need `rlm_query` (or split into `n_chunks` leaves).
- `max_depth` (default **16**) is a **safety cap**, not the operating point. At the cap, `rlm_query` degrades to `llm_query` **only if** the prompt is under 100k tokens. Otherwise it returns an error: slice smaller at this level.

100k is a backstop. The **smart zone** is much smaller: parent in the low thousands, a typical function as one leaf.

### Planned routing for large research

For large `ask` and `research` jobs, `--planner-enabled` adds an optional
deterministic scoper before recursion. It creates bounded records from paths,
sizes, AST declarations, and corpus regex/offset metadata; source bodies are
not in the manifest. A planner may choose only record IDs and their already
valid route. The runtime, rather than the planner or root REPL, performs each
leaf/child call and turns it into a compact cited finding. A separate root pass
then renders from those findings only. This makes recursive splitting
auditable and prevents an accepted plan from widening its source scope.

## Two products, one runtime

| | `rlm ask <path>` | `rlm research <path>` | `rlm.completion` |
|---|---|---|---|
| Bound object | `repo` | `corpus` | `context` (string) |
| Peek API | `tree`, `glob`, `grep`, `read`, `file_text`, `measure`, `plan`, `ask`, `explore` | `search`, `get`, `slice`, `measure`, `plan`, `ask`, `explore` | slices, regex, `len`, `measure`, `measure_ast`, `plan_reads` |
| v0 will not | edit, test, commit, LSP | live web, DOI graphs | — |

There is **no bash**. Exploration is Python helpers inside Docker (ordinary stdlib except `socket`).

## Non-goals (v0)

- Training or fine-tuning a natively recursive model
- Other LM providers (Anthropic, Gemini, OpenRouter, local vLLM)
- A coding agent that applies patches
- Hosted SaaS or UI
- In-process `exec` as a product REPL (`FakeEnv` is tests-only)
- Matching the official [`alexzhang13/rlm`](https://github.com/alexzhang13/rlm) API 1:1
