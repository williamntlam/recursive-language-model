# 001 — Review artifacts

Companion to [`spec.md`](spec.md). Use this to review decisions. If something here disagrees with the spec, the spec wins until you change it.

**Status:** Draft · **Date:** 2026-08-20 · **Owner:** William Lam

---

## 1. One paragraph

Build an **inference-time** Recursive Language Model (not a trained model): OpenAI on the host, a **Docker Python REPL** for the corpus. The parent never sees the repo or papers — only short metadata and its own code. It writes Python that slices data and calls cheaper models on those slices. Results live in **variables**, not in chat. No LM call (parent or child) may have **100k or more input tokens** or **more than 150 instructions**. Goal: explore large codebases and research corpora without context rot.

Paper: Zhang, Kraska, Khattab, *Recursive Language Models* (arXiv:2512.24601).

---

## 2. Locked decisions (review these first)

| # | Decision | v0 choice |
|---|---|---|
| D1 | What we are | RLM runtime + CLI + library. Not a new base model. Not LangChain. |
| D2 | Where context lives | REPL variable / mounted files. **Never** in parent `hist`. |
| D3 | Where tool output lives | Variables in the container. Parent sees truncated stdout only. |
| D4 | Recursion | Symbolic: `for x in xs: llm_query(x)` in Python. Not ReAct tool traces. |
| D5 | Finish | `FINAL_VAR` (answer can be a long variable). Pick one protocol; see open questions. |
| D6 | Prompt size | Every OpenAI call **`< 100_000` tokens**. 100k is illegal. Config max = 99,999. |
| D7 | Instruction count | Composed prompt **`≤ 150`**. Does not grow mid-session. Fail closed, never drop rules. |
| D8 | Provider | **OpenAI only.** Official `openai` SDK. `OPENAI_API_KEY` from env, never CLI. |
| D9 | Models | Root `gpt-5`, leaves `gpt-5-mini` (overridable). |
| D10 | REPL | **Docker only.** No in-process `exec`. No `--env local`. FakeEnv is tests-only. |
| D11 | Key / network in container | Key unset. No public internet. `llm_query` RPCs to host. |
| D12 | Shell | **No bash.** Codebase via `repo.tree/grep/read`. |
| D13 | Depth | Recurse as deep as the context needs. `max_depth = 16` is a safety cap, not the tree shape. |
| D14 | Product surfaces | `rlm ask` (repo), `rlm research` (corpus), `rlm.completion` (string). |
| D15 | Config file | **TOML or YAML** (`rlm.toml` / `rlm.yaml` / `rlm.yml`). Same keys. `--config` for an explicit path. Auth never in the file. |

---

## 3. What this is vs what it is not

**Is**

- A drop-in `rlm.completion(query, context)` that can take a context far larger than any model window.
- An understanding engine for a local repo and a folder of papers.
- Inspectable: every cell, sub-call, token count, and dollar is logged.

**Is not (v0)**

- Training / fine-tuning an RLM.
- A coding agent that edits, tests, or commits.
- RAG, compaction, or ReAct+subagents as the core loop.
- Anthropic, OpenRouter, local vLLM.
- Unrestricted bash, live web search, hosted UI.

---

## 4. Why not ReAct (the trap)

ReAct puts thoughts, tool calls, and observations **into the parent chat**. The window fills; then you summarize and rot.

RLM: parent writes code; bulky reads stay in variables; semantic work is `llm_query` on a slice. The return value is stored in a variable too — **not** pasted as a long observation.

If a “subagent” answer is stuffed back into `hist`, it is ReAct again.

---

## 5. How one query runs

```
User: rlm ask ./repo -- "How does autocast work?"
        │
        ▼
Host: start Docker, mount repo read-only at /workspace
      bind query + repo in the container (not in the OpenAI prompt)
      parent hist = short manifest only
        │
        ▼
Loop:  gpt-5 writes ```repl``` Python
       container executes (grep / read / llm_query slices)
       host appends truncated stdout to hist   ← never the file dump
       until FINAL_VAR
        │
        ▼
Return answer + usage + trajectory
```

`llm_query` = one cheap OpenAI call (`gpt-5-mini`), no nested REPL. Call it as often as needed at any depth.  
`rlm_query` = child RLM (own container + REPL). Use when the piece is still too big or still needs code. Repeat until slices fit. `max_depth` (default 16) is only a circuit breaker.

---

## 6. Invariants (must stay true)

1. Bound corpus/repo text **never** appears in parent `hist`.
2. `count_tokens(messages) < 100_000` on **every** send (parent and children). Else: do not call OpenAI.
3. `instruction_count ≤ 150` on every send. Extra rules mid-run are a bug.
4. Oversize `llm_query`: error string in the REPL, parent must slice. Do not send.
5. `OPENAI_API_KEY` never in the container; container cannot reach the public internet.
6. No Docker daemon → fail startup. Do **not** exec on the host.
7. Child inherits **remaining** budget/timeout, not the original totals.

---

## 7. Limits cheat sheet

**Hard (cannot raise)**

| Limit | Ceiling |
|---|---|
| Input tokens per LM call | `< 100,000` |
| Instructions per LM call | `≤ 150` |

**Default (can change, not above the hard caps)**

| Limit | Default |
|---|---|
| `max_depth` | 16 (safety; raise if a run actually hits it) |
| `max_iterations` | 30 |
| `max_observation_chars` | 2000–4000 (config 3000) |
| `max_concurrent_subcalls` | 8 |
| `max_consecutive_errors` | 5 |
| USD / wall-clock | unset (user sets) |
| Container | 2 GiB RAM, 1 CPU, 60s/cell unless timeout set |

**Need to run live:** `OPENAI_API_KEY` + Docker engine.

---

## 8. Two products, one runtime

| | `rlm ask <path>` | `rlm research <path>` |
|---|---|---|
| Bound object | `repo` | `corpus` |
| Peek API | `tree`, `glob`, `grep`, `read`, `file_text` | `search`, `get`, `slice` |
| Pattern | grep → read slice → `llm_query` file | filter → map `llm_query` → reduce + cite |
| v0 will not | edit/test/commit, LSP, remote GitHub | live web, DOI graphs, perfect PDF |

Generic path: `rlm.completion(query, context=huge_string)` — paper-shaped regression surface.

**No bash.** Exploration is Python helpers inside Docker.

---

## 9. Prompts (keep tiny)

Generic root: **8 rules** (you are an RLM; write `repl` Python; do not print large strings; `llm_query` vs `rlm_query`; batch; `FINAL_VAR`; look don’t guess; slice before sub-calls).

Domain files add the object API + a few strategy hints. Authoring budget: generic ≤ 40 instruction units, one domain ≤ 30, user query ≤ 20, **composed ≤ 150**.

---

## 10. Ship surface

```bash
rlm ask ./pytorch -- "Where is autocast implemented?"
rlm research ./papers -- "Where do these papers disagree?"
```

Python: `RLM(...).completion` / `.ask_repo` / `.research` / `RLM.from_config("rlm.yaml")`.

```toml
# rlm.toml  — or the same keys in rlm.yaml
root_model = "gpt-5"
leaf_model = "gpt-5-mini"
max_depth = 16
max_prompt_tokens = 99999
max_instructions = 150
```

```yaml
# rlm.yaml — equivalent
root_model: gpt-5
leaf_model: gpt-5-mini
max_depth: 16
max_prompt_tokens: 99999
max_instructions: 150
```

Config: `rlm.toml` **or** `rlm.yaml` / `rlm.yml` (same properties). `--config path` to pick a file. Do not put both formats in cwd. Auth **only** via `OPENAI_API_KEY`. Trajectories under `.rlm/logs/`.

Exit: `0` ok · `2` budget/timeout/100k abort · `3` REPL errors · `4` config/Docker/key.

---

## 11. Build order

| Phase | What | Done when |
|---|---|---|
| 0 | Package, CLI stub, Dockerfile, README, toml+yaml config | `pytest` + `rlm --help` |
| 1 | Docker REPL + OpenAI + history + prompt guard + `llm_query` | Context never in `hist`; 100k send refused; no Docker → no host exec |
| 2 | Batched + `rlm_query` + budgets | Map 50 chunks; child gets own container |
| 3 | `Repo` + `rlm ask` | Fixture repo Q&A with path:line cite |
| 4 | `Corpus` + `rlm research` | Two docs + distractor, both cited |
| 5 | Hardening | dry-run, config discovery, cost footer, image pin |
| 6 | Evals | After the product works |
| 7 | Later | Train root, edits, web, UI — **not now** |

---

## 12. Open questions (do not block the spec)

1. Wrap `alexzhang13/rlm` vs reimplement the loop? **Bias: reimplement** so invariants are ours.
2. Package name (`rlm` is taken) — `recursivelm` / `rlm_lab`?
3. Finish protocol: `FINAL_VAR(x)` vs `answer["ready"]`.
4. Confirm `gpt-5` / `gpt-5-mini` ids against current OpenAI docs (override in toml or yaml).
5. Git blame/log as `repo.*` later; not bash.

---

## 13. Review checklist

Tick while reading `spec.md`. Change the spec if you disagree; then update this file.

- [ ] I want an RLM (REPL + recursive slices), not ReAct/RAG/compaction.
- [ ] Parent context stays small; tool dumps must not land in `hist`.
- [ ] Every LM call, parent and child, stays **under 100k** tokens.
- [ ] Prompts stay **≤ 150** instructions; I will not keep adding rules.
- [ ] OpenAI + `OPENAI_API_KEY` only for v0.
- [ ] REPL is Docker; I will run Docker on this machine.
- [ ] No bash; `repo.*` / `corpus.*` is enough for v0.
- [ ] v0 is Q&A over a repo and papers, not an editor.
- [ ] Recursion can go as deep as the context needs; `max_depth` is only a safety cap.
- [ ] Config may be TOML or YAML; the API key stays in the environment, not the file.
- [ ] Open questions above can wait until implementation.

**v1 of the product is successful when:** you point the CLI at a real repo and a folder of papers, ask a dense question, get a cited answer, and the trajectory shows the source never entered the parent window.
