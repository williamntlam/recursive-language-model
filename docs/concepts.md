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

It writes Python. That Python peeks and slices the bound data, stores intermediate results in variables, and calls `llm_query` / `repo.ask` / `rlm_query` on snippets that already fit. The parent does not read file bodies; a leaf does. The final answer can be a long string sitting in a REPL variable (`FINAL_VAR`), so output length is not bounded by the root window.

## Why not bigger windows, RAG, or ReAct

| Approach | Failure |
|---|---|
| Bigger context windows | Cost grows linearly; **context rot** still appears as density grows |
| Compaction / rolling summaries | Lossy. Early details that later become load-bearing disappear |
| RAG / BM25 over the prompt | Retrieval is a guess. Misses dense aggregation and pairwise reasoning |
| ReAct + tools + sub-agents | Observations are *verbalized* into the parent chat. The root still fills up |
| Coding agents with a filesystem | Better for repos, but working memory still lives in the LLM context |

The load-bearing difference versus “an agent with code + sub-agents”:

1. **The prompt lives in the environment, not in `hist`.** The root is not given `P`.
2. **The answer can live in a variable.** `FINAL_VAR(name)` returns a string stored in the REPL.
3. **Recursion is symbolic.** Sub-calls happen *inside Python* (loops, maps, batches), not as a handful of English tool traces.

A scaffold that (a) puts `P` in chat, (b) verbalizes a few `sub_llm` calls, and (c) compact-summarizes when full is **not** an RLM.

## Two failure modes this system is built against

**Hard window limits.** A 100k–1M token window still cannot hold a mid-size monorepo or a multi-paper literature review.

**Context rot.** Even *within* the window, quality degrades as prompts get longer and denser. Needle-in-a-haystack scores hide this. Tasks that require dense access — aggregating facts, tracing a bug, synthesizing a literature — degrade much earlier.

## Product invariants

These are not suggestions. Config may **lower** the numeric ceilings; it cannot raise them.

1. Bound corpus/repo text **never** appears in parent `hist`.
2. Every OpenAI send has `count_tokens(messages) < 100_000`.
3. Every send has composed `instruction_count ≤ 150`. Extra rules mid-run are a bug.
4. An oversize `llm_query` returns an error **string** into the REPL. The parent must slice. The API is not called.
5. `OPENAI_API_KEY` never enters the container. The container has no public internet.
6. No Docker daemon → fail at startup. Do **not** exec on the host.
7. A child RLM inherits **remaining** USD / timeout, not the original totals.

## Recursion depth

Depth is however many nested RLMs the context needs, not a fixed tree of 1.

- `llm_query(prompt)` — one plain completion. No REPL. Cheap (`gpt-5-mini` by default). Use on a tight snippet that already fits.
- `rlm_query(prompt)` — spawn a child RLM with its own REPL and Docker container. **Default** for a file, document, or subproblem. In `ask` / `research`, the child inherits the same `repo` / `corpus` (the subtask string is the query, not a dump of the file). In string `completion`, the prompt is bound as the child's `context`.
- Fan out: one child per file (`repo.explore` / `rlm_query_batched`). Recurse again inside a child if the piece is still large.
- `max_depth` (default **16**) is a **safety cap**, not the operating point. At the cap, `rlm_query` degrades to `llm_query` **only if** the prompt is under 100k tokens. Otherwise it returns an error: slice smaller at this level.

## Two products, one runtime

| | `rlm ask <path>` | `rlm research <path>` | `rlm.completion` |
|---|---|---|---|
| Bound object | `repo` | `corpus` | `context` (string) |
| Peek API | `tree`, `glob`, `grep`, `read`, `file_text`, `ask`, `explore` | `search`, `get`, `slice`, `ask`, `explore` | slices, regex, `len` |
| v0 will not | edit, test, commit, LSP | live web, DOI graphs | — |

There is **no bash**. Exploration is Python helpers inside Docker.

## Non-goals (v0)

- Training or fine-tuning a natively recursive model
- Other LM providers (Anthropic, Gemini, OpenRouter, local vLLM)
- A coding agent that applies patches
- Hosted SaaS or UI
- In-process `exec` as a product REPL (`FakeEnv` is tests-only)
- Matching the official [`alexzhang13/rlm`](https://github.com/alexzhang13/rlm) API 1:1
