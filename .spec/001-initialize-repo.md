# 001 — Initialize Recursive Language Model Repository

**Status:** Draft  
**Date:** 2026-08-20  
**Owner:** William Lam  
**Related:** Zhang, Kraska, Khattab, *Recursive Language Models* (arXiv:2512.24601)

---

## 1. Purpose

This document specifies the first version of this repository: a **Recursive Language Model (RLM)** system for long-context work. The system should let a language model explore large codebases and conduct research over large document corpora **without stuffing the full input into a single context window**, and therefore without the quality collapse known as **context rot**.

The deliverable of this spec is not a trained model. It is an inference-time runtime, CLI, and library that wraps an existing LLM and treats arbitrarily long prompts as an external, programmable environment.

---

## 2. Problem

Frontier models advertise large context windows, but two independent failure modes remain:

1. **Hard window limits.** A 100k–1M token window still cannot hold a mid-size monorepo, a multi-paper literature review, or a long research trail. Stuffing more tokens into the prompt eventually fails outright.
2. **Context rot.** Even *within* the window, quality degrades as prompts get longer and denser. Needle-in-a-haystack tests hide this. Tasks that require dense access — aggregating facts across a whole corpus, tracing a bug through many files, synthesizing a literature — degrade much earlier than NIAH scores suggest.

Common workarounds do not solve this:

| Approach | Failure mode |
|---|---|
| Bigger context windows | Cost grows linearly; rot still appears as density/complexity grows |
| Compaction / rolling summaries | Lossy. Early details that later become load-bearing are discarded |
| RAG / BM25 over the prompt | Retrieval is a guess. Misses dense aggregation and pairwise reasoning |
| ReAct + tools + sub-agents | Sub-calls are *verbalized*, not *programmatic*. The root still fills up. Output length is still bounded by the window |
| Coding agents with a filesystem | Better for repos, but the *user prompt and working memory* still live in the LLM context and rot over a long session |

The Zhang et al. result is the design target: treat the prompt as a variable in a persistent REPL, let the model write code to peek/slice/filter it, and let that code **recursively call the model** on programmatically constructed snippets. Empirically, this processes inputs **two orders of magnitude beyond the native window**, including 10M+ token research corpora, while remaining cost-competitive with a single long call.

This repo specializes that idea to two workloads:

- **Codebase exploration** — understand, search, and reason over large repositories.
- **Research** — read, compare, and synthesize large document sets without forgetting sources.

---

## 3. Goals

### 3.1 Product goals

1. Replace `llm.completion(prompt)` with `rlm.completion(query, context)` such that `|context|` can be far larger than the model window.
2. Keep the **root model's context small and stable**. The root sees metadata, short prefixes, truncated REPL stdout, and its own code — never the full corpus.
3. Support **symbolic recursion**: code in the REPL can loop over slices of the context and spawn `Ω(|P|)` sub-calls, storing results in variables rather than in chat history.
4. Support **unbounded outputs** by returning a REPL variable (`FINAL_VAR`) rather than forcing the root to emit the entire answer token-by-token.
5. Provide first-class environments for:
   - a local (or cloned) **code repository**
   - a **research corpus** (papers, notes, web dumps, markdown)
6. Expose the system as a Python library and a CLI that a human can use for real work.
7. **Never send an LM prompt over 100,000 tokens or 150 instructions.** The runtime fails closed (error to REPL or abort), and these ceilings cannot be raised by config.
8. Run every real REPL cell inside Docker. The host never `exec`s model code.

### 3.2 Quality goals

- No silent dropping of context. If the model did not look at a file or document, that is an explicit choice visible in the trajectory, not a summarizer's accident.
- Trajectories are inspectable: every code cell, stdout snippet, sub-call, and cost is logged.
- Cost and latency are first-class. Recursion must be budgeted (depth, iterations, USD, tokens, wall clock).
- **Hard prompt ceilings (not overridable upward):** no LM call may receive more than **100,000 tokens**, and no prompt payload may contain more than **150 instructions**. These are anti-rot constraints, not suggestions. See §7.5.
- Default path is useful on a laptop with an `OPENAI_API_KEY` and a running **Docker** engine. The REPL always executes in a container.

### 3.3 Non-goals (v0)

- Training or fine-tuning a natively recursive model (the paper's RLM-Qwen3-8B recipe). That is a later phase.
- Building a new base LLM, long-context architecture, or KV-cache system.
- Replacing a full coding agent (edit/apply/test loop, PR workflows). Exploration and Q&A first; mutation later.
- A hosted SaaS, multi-tenant control plane, or web UI.
- A formally verified sandbox or gVisor/Firecracker. Docker is the v0 isolation boundary, not a kernel exploit guarantee.
- In-process `exec` as the product REPL. A host-side fake environment exists only for unit tests.
- Matching the official `alexzhang13/rlm` API 1:1. This repo may depend on or reimplement the core loop, but the product surface is ours.
- Other LM providers (Anthropic, Gemini, OpenRouter, local vLLM). v0 talks to **OpenAI only**. Extra backends are a later phase if needed.

---

## 4. Background: Recursive Language Models

This section is the contract with the paper. Implementation should preserve these properties. If a shortcut violates one of them, it is not an RLM.

### 4.1 Interface

An RLM has the same external type as an LLM:

```
RLM : (query: str, context: Context) → response: str
```

`Context` may be a string, a list of documents, a repository handle, or any object that can be bound as a REPL variable. The caller should not have to chunk it.

### 4.2 Algorithm (root loop)

```
state ← InitREPL(context = P)
state ← AddFunctions(state, {llm_query, rlm_query, batched variants})
hist  ← [Metadata(state)]          # length, short prefix, how to access P
                                       # NOT the full prompt
loop:
    code   ← LM(hist)              # root model, small context
    (state, stdout) ← REPL(state, code)
    hist   ← hist ‖ code ‖ Metadata(stdout)   # truncated, constant-size
    if Final is set:
        return Final
```

Three design choices distinguish this from “an agent with code + sub-agents”:

1. **The prompt lives in the environment, not in `hist`.** The root is not given `P`. It is given handles and metadata. This is the difference between unbounded input and “we hope it fits.”
2. **The answer can live in a variable.** `FINAL_VAR(name)` returns the string stored in the REPL, so output length is not bounded by the root window.
3. **Recursion is symbolic.** Sub-calls happen *inside code* (including loops and batch maps), not as a handful of tool calls the model has to write in English. This is what makes linear and quadratic work over `|P|` possible.

An apparently similar scaffold that (a) puts `P` in the chat, (b) verbalizes a few `sub_llm` tool calls, and (c) compact-summarizes when full is **not** an RLM. The paper's Algorithm 2 is exactly that trap.

### 4.3 What the root is allowed to see

Each REPL turn returns only **constant-size metadata** about stdout: a short prefix, a length, maybe a hash. Long strings stay in variables. If stdout is huge, the model is forced to slice it in code rather than reread it in the transcript. That constraint is load-bearing; relaxing it reintroduces rot. Independently, the full message list sent to any LM must stay ≤ 100k tokens with ≤ 150 instructions (§7.5).

### 4.4 Recursion depth

- `llm_query(prompt)` — one plain completion. No REPL. Cheap. Use for extract / classify / summarize a snippet that already fits.
- `rlm_query(prompt)` — spawn a child RLM with its own REPL. Use when the subtask itself is long or needs code.
- At `max_depth`, `rlm_query` degrades to `llm_query`.
- v0 default: `max_depth = 1` (root RLM, leaf LLM), matching the paper's main experiments. Depth > 1 is supported in the runtime but not required for the first evals.

### 4.5 Empirical targets from the paper (orientation, not v0 gates)

On GPT-5-class models, RLMs beat base calls, CodeAct+BM25, CodeAct+sub-calls, and summary agents on:

- LongBench-v2 CodeQA (repo understanding, 23K–4.2M tokens)
- BrowseComp-Plus deep research (6–11M tokens)
- OOLONG (linear aggregation)
- OOLONG-Pairs (quadratic pairwise reasoning)

Ablation: REPL-without-subcalls is already enough to exceed the window. Sub-calls matter most on information-dense tasks. This repo should preserve both knobs so we can measure the same split.

---

## 5. Product vision

A user should be able to do the following without managing context themselves.

### 5.1 Codebase exploration

```bash
rlm ask ./pytorch -- "Where is autocast implemented, and how does it interact with bfloat16 on CPU?"
```

Expected behavior:

1. Bind the repository as a structured object in the REPL (`repo`), not as a concatenated dump of every file.
2. Root model inspects the tree, greps, reads file slices, and recursively asks sub-models questions about specific files or modules.
3. Intermediate notes live in REPL variables (`findings`, `callgraph`, `suspects`).
4. Final answer cites file paths and line ranges. Those citations are produced from variables, not from a rotting chat log.

The system is an **understanding engine**, not an editor. It may propose patches as text. It does not apply them in v0.

### 5.2 Research

```bash
rlm research ./corpus -- "What do 2024–2026 papers say about context rot vs recursive inference, and where do they disagree?"
```

Expected behavior:

1. Bind a corpus (PDFs converted to text, markdown, HTML dumps) as `documents: list[Document]`.
2. Root model samples, filters, and maps `llm_query` / `rlm_query` over documents or chunks.
3. Claims, quotes, and citations accumulate in variables.
4. Final report is assembled in the REPL and returned via `FINAL_VAR`. Sources survive because they were never compacted away.

### 5.3 Generic long prompt

```python
result = rlm.completion(
    query="Count how many rows mention La Union and classify each.",
    context=huge_string,
)
```

This is the paper's default path and the regression surface for the core runtime.

---

## 6. Design principles

1. **Context is data, not prompt.** If a string might be large, it is a variable. Prompts to any LM (root or leaf) must stay under **100k tokens** and **150 instructions**. Exceeding either cap is a runtime error, never a send.
2. **The model chooses the decomposition.** Do not hard-code chunk sizes or retrieval pipelines as the only strategy. Provide primitives (slice, grep, tree, parse) and let the root write the strategy. Optional heuristics may be offered as *tools*, not as a mandatory DAG.
3. **Truncate observations, never the source.** Stdout shown to the model is capped. The underlying variable is not.
4. **Budgets are hierarchical.** A child inherits *remaining* timeout / USD / tokens, not the original totals.
5. **Trajectories are the unit of debugging.** If an answer is wrong, a human must be able to see which slices were read and which sub-calls were made.
6. **Cheap leaves, expensive root.** Default OpenAI routing: `gpt-5` at depth 0, `gpt-5-mini` for `llm_query`. This is how the paper stayed cost-competitive. Both must be OpenAI model ids.
7. **Don't rot the root with success.** Even a correct long session must not grow `hist` without bound. Cap per-turn observation size and max iterations; if the root needs more memory, it must write variables, not reread transcripts.
8. **The REPL runs in Docker.** Model-generated Python never `exec`s in the host process. The OpenAI key stays on the host; the container reaches it only through a narrow LM-callback channel.

---

## 7. System architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  CLI / Python API                                               │
│  rlm ask | rlm research | rlm.completion(query, context)        │
└───────────────────────────────┬─────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  RLM Runtime                                                    │
│  - iteration loop                                               │
│  - history policy (metadata-only observations)                  │
│  - recursion (llm_query / rlm_query / batched)                  │
│  - budgets (depth, iterations, $, tokens, time, errors)         │
│  - prompt guard (≤100k tokens, ≤150 instructions per call)      │
│  - trajectory logger                                            │
└───────────────┬─────────────────────────────┬───────────────────┘
                │                             │
                ▼                             ▼
┌───────────────────────────┐   ┌─────────────────────────────────┐
│  OpenAI backend           │   │  Docker REPL                    │
│  official openai SDK      │   │  containerized Python namespace │
│  OPENAI_API_KEY (host)    │   │  no API key in the container    │
│  gpt-5 root, mini leaves  │   │  repo/corpus mounted read-only  │
└───────────────────────────┘   └─────────────────────────────────┘
```

### 7.1 Runtime

The runtime owns the loop, not the model. Responsibilities:

- Build the initial system prompt describing the REPL, available names, and how to finish (`FINAL` / `FINAL_VAR`, or `answer["ready"]=True` — pick one convention and stick to it).
- Call the root LM with `hist` only.
- Parse fenced code blocks (```repl or ```python — decide in implementation; prefer a single fence type).
- Execute in the **Docker** environment (or FakeEnv in unit tests).
- Append truncated stdout/stderr to `hist`.
- Detect completion, errors, stalls (repeated identical code), and budget exhaustion.
- **Refuse to send** any LM request that would exceed the prompt-token or instruction ceilings (§7.5).
- Spawn child RLMs for `rlm_query`, each with its own container, callback port, and remaining budget.

Hard ceilings (may be *lowered* by config, never raised):

| Limit | Ceiling | Why |
|---|---|---|
| `max_prompt_tokens` | **100,000** | No single LM call — root or leaf — may ingest more than this |
| `max_instructions` | **150** | Instruction-following collapses past a short list of rules |

Recommended v0 limits (overridable, including upward unless they would violate the ceilings):

| Limit | Default | Why |
|---|---|---|
| `max_depth` | 1 | Matches paper; enough for CodeQA and research map-reduce |
| `max_iterations` | 30 | Prevents infinite peek loops |
| `max_observation_chars` | 2000–4000 | Forces variable use; also the main lever to stay far below 100k |
| `max_concurrent_subcalls` | 8 | Batch maps without melting the API |
| `max_budget_usd` | unset | User sets per session |
| `max_timeout_s` | unset | User sets per session |
| `max_consecutive_errors` | 5 | Abort on broken code loops |

### 7.2 LM backend (OpenAI)

v0 has **one** backend: the official [`openai`](https://github.com/openai/openai-python) Python SDK talking to `api.openai.com`. No LangChain, no Anthropic, no OpenRouter, no local-server shim.

```python
from openai import OpenAI

class OpenAIClient:
    def complete(self, messages: list[Message], *, model: str, **kwargs) -> Completion:
        ...
```

**Auth.** Read `OPENAI_API_KEY` from the environment (or a gitignored `.env` loaded at process start). Never log it, never write it into trajectories, never accept it as a CLI flag (flags show up in shell history). If the key is missing, fail at startup with a clear error (CLI exit `4`). Optional: `OPENAI_ORG_ID` / `OPENAI_PROJECT` if the user has them set; not required.

**Models.**

| Role | Default | Override |
|---|---|---|
| Root (`depth = 0`) | `gpt-5` | `root_model` / `--root-model` |
| Leaves (`llm_query`, and `rlm_query` at `max_depth`) | `gpt-5-mini` | `leaf_model` / `--leaf-model` |

Both values are OpenAI model ids. The user can point them at whatever their key can call (`gpt-4.1`, `gpt-4.1-mini`, etc.) without changing code.

**API surface.** Chat Completions (`client.chat.completions.create`) unless a given model id requires the Responses API — then use Responses for that id only, still through the official SDK. Do not invent a second provider abstraction for that.

**Usage.** Record `prompt_tokens`, `completion_tokens`, and OpenAI-reported cost when present; otherwise estimate from `tiktoken` + a small OpenAI price table. This feeds `max_budget_usd` and the usage footer.

**Tests.** Production code path uses `OpenAI`; CI uses a `FakeClient` with the same `complete()` shape. No live API calls in CI.

### 7.3 Environment (Docker REPL)

Model-generated code runs in a **Docker container**. That is the product path, not an optional hardening step. The host process owns the RLM loop, prompt guard, trajectory log, and OpenAI calls. The container owns the persistent Python namespace and any `repo` / `corpus` bytes it is allowed to see.

If Docker is not running, a real `completion()` fails at startup (CLI exit `4`) with a message to start Docker. Do not silently fall back to in-process `exec`.

```
Host                                              Container (rlm-repl image)
────                                              ─────────────────────────
RLM loop                                          persistent Python interpreter
OpenAI client + OPENAI_API_KEY                    context / repo / corpus variables
prompt guard                                      llm_query stubs → RPC to host
LM callback server (localhost)  ◄── JSON/RPC ──►  execute ```repl``` cells
bind-mount repo/corpus (ro)  ──────────────────►  /workspace
```

**Why a callback server.** `llm_query` / `rlm_query` are called *from code inside the container*. The container must not receive `OPENAI_API_KEY`. The host listens on a loopback (or docker-gateway) port for the duration of the completion; the container's injected `llm_query` is an RPC client to that port. Same framing idea as the official RLM `LMHandler`: length-prefixed JSON is fine. Close the port when the completion ends.

**Image.** Ship `docker/Dockerfile` in this repo, tag `rlm-repl:<version>`. Base: `python:3.12-slim`. Non-root user. No compiler toolchain, no SSH, no cloud CLIs. Build on first use if the tag is missing. Pin the image digest in lock notes once it exists.

**Container policy (v0 defaults):**

| Knob | Default | Why |
|---|---|---|
| Network | No public internet. Only the host LM-callback port | Stops `requests.get`, accidental exfil, prompt-injected crawlers |
| `OPENAI_API_KEY` in container env | **unset** | Key stays on the host |
| Root filesystem | Read-only, with a small writable tmpfs (`/tmp`, `/repl`) | Persistence is the Python process, not the disk |
| Host mounts | Only the session workspace (context files, repo, or corpus) at `/workspace`, **read-only** | Model cannot scribble on the user's tree |
| User | Non-root | |
| Privileged / host PID/net | Off | |
| Memory | 2 GiB | |
| CPUs | 1 | |
| PIDs | 256 | |
| Cell timeout | inherits remaining `max_timeout_s`; otherwise 60s per cell | Hung `while True` dies |

**Lifecycle.** `completion()` starts one container, keeps a single Python interpreter alive so the namespace persists across cells, and `stop` + `rm` in `finally`. Default `max_depth = 1` means only the root needs a REPL container (`llm_query` is a host OpenAI call, no child REPL). If `max_depth > 1`, each child RLM gets **its own** container and callback port. Never Docker-in-Docker.

**How context enters the container.** Do not pickle host objects across the boundary.

- String `context`: write to `/workspace/context.txt` (or a tmpfs file) and bind `context = Path(...).read_text()` at REPL init, or stream it over the RPC once. Prefer a file in the session mount for large payloads.
- `repo` / `corpus`: bind-mount the directory read-only at `/workspace`. Domain helpers inside the container read from that path.
- Reserved functions (`llm_query`, …) are injected by the REPL server at start, not imported from the host.

**Host-side fake environment.** Unit tests use an in-memory `FakeEnv` that implements the same `execute(code) -> Observation` interface. It must not be selectable from the CLI. `--env local` is **not** a product flag.

**Reserved names** that the model cannot clobber (restore after each cell):

- `context` / `context_0` — primary payload
- `query` — user question
- `llm_query`, `llm_query_batched`
- `rlm_query`, `rlm_query_batched`
- `SHOW_VARS()`
- domain objects: `repo` or `corpus` when those loaders are used
- `answer` or the FINAL helpers

**Stdlib inside the container.** Inject or allow `re`, `json`, `pathlib`, `collections`, `textwrap`. Do not give the model `os.system`, `subprocess`, `socket` (except the injected RPC), or `import` of host-only packages. The container has no OpenAI SDK.

### 7.4 History policy (anti-rot)

This is the most important subsystem that naive agent ports get wrong.

On every turn, the observation appended to `hist` is:

```
<stdout truncated to N chars>
...[truncated, total_len=L, sha256=...]
<stderr truncated similarly>
```

Never append:

- the full `context`
- full file contents (those stay in variables; the model prints slices if it wants to see them)
- full sub-call transcripts (return the child *answer string*, optionally a short metadata summary)

If `hist` itself would exceed **100,000 tokens** on the next root call, **do not send**. Do not summarize the corpus. Stop with `PromptBudgetError` (CLI exit `2`) and keep REPL state inspectable so the user can continue from variables. Compacting the source data is how rot re-enters. Observation truncation exists so this abort should be rare; if it is common, `max_observation_chars` is too high.

### 7.5 Hard prompt limits (100k tokens, 150 instructions)

These two numbers are **product invariants**. The backend must not issue an LM HTTP request that violates them. Config may set a *lower* `max_prompt_tokens` or `max_instructions`. Setting a higher value is a config error at startup (CLI exit `4`).

| Name | Hard ceiling | Applies to |
|---|---|---|
| `MAX_PROMPT_TOKENS` | `100_000` | Every call: root turn, `llm_query`, `rlm_query`, batched items each counted separately |
| `MAX_INSTRUCTIONS` | `150` | The composed prompt payload for that same call |

**100k is a ceiling, not a target.** The root should usually sit in the low thousands of tokens. Leaves should receive only the snippet they need. Hitting 100k means the history policy or a `llm_query` argument failed.

#### Token counting

- Count **input tokens of the exact message list** about to be sent (system + developer + hist + the current user/query message). Do not count the bound REPL `context` unless it was actually copied into those messages.
- Use `tiktoken` `cl100k_base` for the guard (OpenAI-native, deterministic in tests).
- If OpenAI later reports a higher token count than our estimate, log it; still never *send* a payload we already counted over 100k.
- Batched calls: each prompt in the batch is guarded on its own. A 200-item batch of 10k-token prompts is 200 legal calls, not one 2M-token call.

**If a send would exceed 100k:**

| Caller | Behavior |
|---|---|
| Root loop | Do not call the LM. Abort the completion with `PromptBudgetError`. Persist trajectory. |
| `llm_query` / `rlm_query` | Do not call the LM. Return an error *string* into the REPL (`"Error: prompt is N tokens; max is 100000. Slice the argument."`) so the root can recover by slicing. One oversize leaf must not kill the whole batch (same per-item failure rule as §8.3). |
| Prompt composition at startup | If the *static* system+domain prompt alone is > 100k (should be impossible if prompts stay small), refuse to start. |

#### Instruction counting

An **instruction** is a discrete directive the model is expected to obey. Observations, model-written code, stdout, and corpus/repo *data* are not instructions.

Count **1** for each of:

1. Each numbered or bulleted list item in system and developer prompts (the usual form of a rule).
2. Each REPL builtin or domain method the prompt exposes as something the model may call (`llm_query`, `rlm_query`, batched variants, `SHOW_VARS`, `FINAL` / `FINAL_VAR`, each `repo.*` / `corpus.*` method listed). A method listed twice still counts once.
3. The user query (the actual task).
4. Each extra rule injected at runtime (CLI flags that add constraints, `custom_system_prompt` fragments, per-eval instructions).

Do **not** count:

- REPL stdout/stderr, truncation notices, hashes, lengths
- Code cells the model already ran
- Manifest / catalog / file-tree **data** (even when shown in the first observation)
- Prose that is purely descriptive (“`repo` is a Repo object”) unless it is also a list item or an exposed method

The composed instruction set for a call is: static prompts ∪ exposed methods ∪ user query ∪ runtime extras. That total must be `≤ 150` **before the first token is sent**, and it must not grow during the session. New observations must not add instructions. If a code path tries to append more rules mid-run, that is a bug; reject the append.

**Authoring budget.** Keep static prompts lean so there is headroom:

| Layer | Target instruction units |
|---|---|
| Generic root prompt (rules + builtins) | ≤ 40 |
| One domain add-on (repo *or* research) | ≤ 30 |
| User query + optional CLI extras | ≤ 20 |
| **Composed total** | **≤ 150, fail closed** |

CI must parse `rlm/prompts/*.md` (or whatever structured format we use) and fail if generic + any single domain file would already exceed 150 before the user query.

**If composed instructions would exceed 150:** fail at startup or at custom-prompt load with `InstructionBudgetError`. Do not drop rules silently to fit. The fix is to delete or merge rules, not to ship a 151st.

#### Implementation notes

- Module: `rlm/core/prompt_guard.py` with `count_tokens(messages) -> int`, `count_instructions(payload) -> int`, `assert_sendable(...)`.
- `LMClient.complete` is not responsible for the policy. The runtime wraps every send. Tests can use a client that raises if called with an oversize payload, so a missed guard is a red test.
- Log `prompt_tokens` and `instruction_count` on every event in `events.jsonl`.

---

## 8. Domain environments

The generic RLM binds a string. This product binds **structured worlds**. Both worlds must still obey “context is a variable.”

### 8.1 Codebase environment

Load a git working tree (or any directory) into the REPL as `repo`.

**Data model**

```python
class Repo:
    root: Path
    def tree(self, max_depth: int = 3, ignore: Sequence[str] = DEFAULT_IGNORE) -> str: ...
    def glob(self, pattern: str) -> list[str]: ...
    def read(self, path: str, start: int | None = None, end: int | None = None) -> str: ...
    def grep(self, pattern: str, glob: str | None = None) -> list[GrepHit]: ...
    def files(self) -> list[FileMeta]: ...   # path, n_bytes, n_lines, sha
    def file_text(self, path: str) -> str: ...  # full text as a variable, not printed
```

`DEFAULT_IGNORE` excludes `.git`, `node_modules`, virtualenvs, build artifacts, lockfile blobs, and other high-entropy junk unless the user overrides.

**What is bound at start**

- `query: str`
- `repo: Repo`
- `manifest: str` — a short tree + file count + total bytes (fits in the initial metadata message)
- optionally `context: str` as a lazy concatenation **only if the user asked for dump mode**; default is structured `repo`, not a blob

The root's first observation should look like:

```
Repository: /path/to/pytorch
Files: 12,403  |  Text-ish bytes: 184MB  |  Git HEAD: abc123
Top-level:
  aten/  caffe2/  torch/  test/  ...
Use repo.tree(), repo.grep(), repo.read(), repo.file_text(path).
Do not print entire files. Assign them to variables and llm_query slices.
```

**Exploration patterns we want the model to learn (via prompt, later via traces)**

1. *Narrow then read* — grep / glob → read slices → sub-call on a file.
2. *Map over a module* — `llm_query_batched` on each file in a directory with the same question.
3. *Follow edges* — find definition, then grep for callers, recurse.
4. *Aggregate* — “how many modules import X?” answered by code over `repo.files()`, not by stuffing the repo into chat.

**Out of scope for v0**

- Language-server / SCIP / precise type graphs. Grep + files is enough to beat dump-into-context.
- Applying patches, running tests, committing.
- Remote GitHub browsing without a local clone.

### 8.2 Research environment

Load a directory (or explicit file list) of documents as `corpus`.

**Data model**

```python
class Document:
    id: str
    path: str
    title: str | None
    text: str
    n_chars: int

class Corpus:
    docs: list[Document]
    def search(self, pattern: str) -> list[SearchHit]: ...
    def get(self, id: str) -> Document: ...
    def slice(self, id: str, start: int, end: int) -> str: ...
```

Ingest v0:

- `.md`, `.txt`, `.rst` as-is
- `.pdf` via a local extractor (pypdf or pymupdf) to plain text; store extracted text next to the source so re-runs are cheap
- `.html` stripped to text
- skip binaries

**What is bound at start**

- `query`
- `corpus`
- `catalog` — id, title, path, length for every doc (may itself be large; if so, bind as a variable and show only `len(catalog)` + a few rows)

**Research patterns**

1. *Filter* with regex / keyword code using prior knowledge (“papers mentioning 'context rot'”).
2. *Map* `llm_query` over remaining docs: “extract claims relevant to Q, with quotes.”
3. *Reduce* in the root (or a second-stage `rlm_query`) over the list of claim objects.
4. *Cite* from structured records `{doc_id, span, claim}` assembled in a variable, then rendered into the final markdown.

**Out of scope for v0**

- Live web search (can be a later tool; changes the trust model).
- Bibliographic databases, DOI resolution, citation graphs.
- Perfect PDF layout / equation recovery.

### 8.3 Shared REPL primitives

Always available:

```python
llm_query(prompt: str, model: str | None = None) -> str
llm_query_batched(prompts: list[str], ...) -> list[str]
rlm_query(prompt: str, ...) -> str
rlm_query_batched(prompts: list[str], ...) -> list[str]
SHOW_VARS() -> str
```

Each `prompt` argument is a full LM payload and is subject to §7.5: **≤ 100k tokens and ≤ 150 instructions**. The runtime prepends only a short leaf system prompt (extract/classify/summarize; a handful of instructions). If the model concatenates a huge slice into `llm_query`, the call returns an error string and does not hit the API.

Batch helpers must be **index-aligned** and **per-item failure tolerant**: one failed leaf (including a prompt-budget failure) returns an error string in that slot, others succeed.

A small standard library in the container namespace is allowed if it does not pull the source into `hist`: `re`, `json`, `pathlib` (constrained to `/workspace`), `collections`, `textwrap`. The model must not `import os` / `subprocess` on the host — it cannot; that code does not run on the host.

---

## 9. User-facing API

### 9.1 Python

```python
from rlm import RLM, load_repo, load_corpus

rlm = RLM(
    root_model="gpt-5",          # OpenAI
    leaf_model="gpt-5-mini",     # OpenAI
    environment="docker",        # required for real completions
    max_depth=1,
    max_iterations=30,
    max_prompt_tokens=100_000,  # ceiling; smaller is allowed
    max_instructions=150,       # ceiling; smaller is allowed
    verbose=True,
)

# Generic
out = rlm.completion(query="...", context="huge string ...")

# Codebase
out = rlm.ask_repo(path="./pytorch", query="How does autograd handle views?")

# Research
out = rlm.research(path="./papers", query="Compare recursive vs compressive memory.")

print(out.response)
print(out.usage)       # tokens, cost, iterations, subcalls
print(out.trajectory)  # optional path to JSONL
```

`completion` is the primitive. `ask_repo` / `research` are loaders + system-prompt variants on top of it.

### 9.2 CLI

```
rlm ask <path> -- <query>
rlm research <path> -- <query>
rlm complete --context-file <file> -- <query>

rlm ask ./repo --max-budget 2.00 --leaf-model gpt-5-mini -- "..."
rlm ask ./repo --dry-run -- "..."     # show manifest + prompt, no API calls
```

Global flags: `--root-model`, `--leaf-model`, `--max-depth`, `--max-iterations`, `--max-prompt-tokens`, `--max-instructions`, `--max-budget`, `--timeout`, `--log-dir`, `--verbose`.

There is no `--env local`. The REPL is Docker. `--dry-run` still runs on the host (manifest + prompt only, no container, no API calls).

`--max-prompt-tokens` and `--max-instructions` may only go **down** from 100,000 and 150. A higher value is a config error.

Exit codes: `0` success, `2` budget/timeout (including prompt-token abort), `3` REPL errors exhausted, `4` user/config error (including instruction-budget / illegal ceiling / Docker not running).

### 9.3 Configuration

Resolved in order: CLI flags > `rlm.toml` in cwd > env vars > defaults.

```toml
# rlm.toml
root_model = "gpt-5"
leaf_model = "gpt-5-mini"
environment = "docker"
max_depth = 1
max_iterations = 30
max_observation_chars = 3000
max_prompt_tokens = 100000
max_instructions = 150
log_dir = ".rlm/logs"
```

Auth is **not** in `rlm.toml`. Required:

```
OPENAI_API_KEY=sk-...
```

Optional: `OPENAI_ORG_ID`, `OPENAI_PROJECT`. Ship a `.env.example` with empty keys; add `.env` to `.gitignore`. Document this in the README. Missing key → startup error, no API call.

---

## 10. Repository layout

Greenfield layout for a Python package. Names can shift slightly during implementation, not conceptually.

```
recursive-language-model/
├── .spec/
│   └── 001-initialize-repo.md      # this document
├── README.md
├── pyproject.toml                  # package: rlm (or recursive_lm); deps: openai, tiktoken, docker
├── uv.lock
├── .env.example                    # OPENAI_API_KEY=
├── .gitignore                      # includes .env
├── docker/
│   ├── Dockerfile                  # rlm-repl image: python 3.12-slim, REPL server
│   └── repl_server.py              # in-container cell runner + LM RPC client
├── rlm/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   ├── core/
│   │   ├── runtime.py              # iteration loop
│   │   ├── types.py                # Completion, Message, Usage
│   │   ├── history.py              # truncation / metadata policy
│   │   ├── parse.py                # extract fenced REPL code
│   │   ├── prompt_guard.py         # 100k token + 150 instruction ceilings
│   │   └── budgets.py
│   ├── backends/
│   │   ├── base.py                 # FakeClient lives here for tests
│   │   └── openai.py               # official openai SDK; v0's only backend
│   ├── environments/
│   │   ├── base.py                 # execute(code) -> Observation
│   │   ├── docker.py               # product REPL
│   │   └── fake.py                 # tests only; not a CLI env
│   ├── domains/
│   │   ├── repo.py
│   │   └── corpus.py
│   ├── prompts/
│   │   ├── root.md
│   │   ├── repo.md
│   │   └── research.md
│   └── logging/
│       └── trajectory.py
├── tests/
│   ├── test_history_policy.py
│   ├── test_prompt_guard.py        # never send >100k tokens or >150 instructions
│   ├── test_runtime_loop.py        # fake LM client + FakeEnv
│   ├── test_docker_repl.py         # marked; requires Docker daemon
│   ├── test_repo_env.py
│   ├── test_corpus_env.py
│   └── fixtures/
├── evals/
│   ├── README.md
│   └── ...                         # later: CodeQA-style, research fixtures
├── examples/
│   ├── ask_small_repo.py
│   └── research_tiny_corpus.py
└── .gitignore
```

Packaging: Python 3.12+, `uv`, Ruff, pytest. Keep the installable extra set small (`[pdf]`, `[docker]`).

---

## 11. Prompts

Prompts are part of the system, not comments. They must teach the three RLM moves **and stay inside the 150-instruction ceiling**.

Root system prompt (generic) should state only the rules below — do not grow this list without removing something else:

1. You are an RLM. The full context is in the variable `context` (or `repo` / `corpus`). You have **not** been given it in this message.
2. Write Python in fenced `repl` blocks. State persists across cells.
3. Peek with slices, regex, and domain helpers. **Do not print large strings.**
4. For semantic work on a snippet that already fits, call `llm_query`. For a subproblem that needs its own code loop, call `rlm_query`.
5. Prefer `llm_query_batched` when mapping the same question over many chunks.
6. Accumulate results in variables. Finish with `FINAL_VAR(name)` (or the chosen `answer` dict).
7. If you are unsure, write code to look; do not guess from the short prefix.
8. Never pass a string into `llm_query` / `rlm_query` that you have not already measured as fitting the 100k-token leaf budget; slice first.

That is **8 rules**, plus builtins counted per §7.5. Domain prompts add only the object API (each method = 1) and **at most a few** strategy hints (grep before read; map then reduce; cite paths / doc ids). Do not bake benchmark-specific recipes into the default prompt. Do not add a long “always / never” appendix — that is how we blow the 150 cap and how models stop following any given rule.

Keep prompts in files under `rlm/prompts/` so they can be versioned and A/B'd without code changes. A unit test must count instructions in those files on every CI run.

---

## 12. Logging and observability

Each `completion` writes a trajectory directory:

```
.rlm/logs/<timestamp>-<id>/
  meta.json          # models, limits, query hash, context stats
  events.jsonl       # one record per iteration / subcall / error
  answer.txt
  usage.json
```

Each event includes: iteration, depth, code, truncated stdout, subcall ids, tokens, `prompt_tokens`, `instruction_count`, latency. Sub-RLMs nest as children.

Verbose CLI mode pretty-prints iterations. Default CLI prints the answer and a one-line usage footer.

This is how we debug rot: if `hist` token count trends up while `context` is untouched, the history policy is broken. If `instruction_count` trends up across iterations, instructions are leaking into observations — that is also a bug.

---

## 13. Implementation plan

Work is sequenced so each phase is usable and testable. Do not start evals before the history policy is locked.

### Phase 0 — Repo bootstrap (this spec)

- Python package skeleton, `uv`, Ruff, pytest, `.gitignore`
- README: what an RLM is, why this repo exists, how to run a stub, `OPENAI_API_KEY`, Docker required
- `.env.example`, `.gitignore` including `.env`
- Config + CLI stubs
- `docker/Dockerfile` stub
- Dependency: `openai`, `tiktoken`, `docker`

**Exit:** `uv run pytest` passes on empty/placeholder tests; `rlm --help` works.

### Phase 1 — Core RLM loop (generic string context)

- DockerREPL: session container, persistent interpreter, host LM-callback (no key in the container)
- FakeEnv + Fake LM client for tests that do not need Docker
- Real OpenAI backend (`openai` SDK + `OPENAI_API_KEY`)
- History truncation
- Prompt guard (100k tokens / 150 instructions) wrapping every send
- `FINAL` / `FINAL_VAR`
- `llm_query` (no recursion yet) via the callback, not from inside the container's network
- Trajectory logging

**Exit:** Given a 100k-character string that does **not** fit in a tiny fake window, the root never receives the full string, can grep/slice it in code, and returns the correct needle via `FINAL_VAR`. Tests assert the full context never appears in `hist`. A second test builds a 100,001-token `llm_query` argument and asserts the API is not called. A third test composes prompts with 151 instructions and asserts startup failure. A Docker test (skipped if no daemon): a cell cannot `os.environ["OPENAI_API_KEY"]`, cannot hit the public internet, and `print(context[:20])` works after the payload was mounted — not stuffed into `hist`. Completing without Docker raises a startup error instead of exec'ing on the host.

### Phase 2 — Symbolic recursion

- `llm_query_batched`
- `rlm_query` with `max_depth`
- Remaining-budget inheritance
- Leaf vs root model routing
- Concurrent batch cap

**Exit:** A scripted test where the root maps `llm_query` over 50 chunks and concatenates results in a variable. A second test where `rlm_query` spawns a child with its own **container**. Cost/token accounting is populated.

### Phase 3 — Codebase domain

- `Repo` loader, ignore rules, tree/grep/read
- `rlm ask` CLI
- Repo system prompt
- Example on a small fixture repo (tens of files) and a medium public repo (optional, documented)

**Exit:** Fixture test: question whose answer is in a deep file; dump-all-files baseline would exceed the fake window; RLM finds it and cites path:line.

### Phase 4 — Research domain

- `Corpus` loader, text/markdown, PDF extract extra
- catalog + search + slice
- `rlm research` CLI
- Research system prompt
- Tiny multi-document fixture (contradictory claims) requiring map-reduce

**Exit:** Fixture test: answer requires combining two documents and ignoring a distractor; citations include both source ids.

### Phase 5 — Hardening

- Stall detection, max errors, dry-run
- `rlm.toml`
- Usage footer, budget abort
- Image digest pinning, tighter seccomp/cap-drop if easy
- README cookbook (good queries, cost expectations, Docker Desktop notes, when *not* to use RLM — short prompts are often worse, as in the paper)

### Phase 6 — Evaluation (after the product works)

Not a v0 blocker, but the north star:

| Eval | What it tests |
|---|---|
| Synthetic NIAH over 1M chars | Window bypass |
| Dense aggregation (mini-OOLONG style) | Sub-calls vs grep-only |
| Fixture monorepo Q&A | Code domain |
| Multi-doc synthesis with distractors | Research domain |
| History invariant | `full_context in hist` is always false |
| Prompt-token ceiling | No recorded send has `prompt_tokens > 100000` |
| Instruction ceiling | No recorded send has `instruction_count > 150`; static prompt files pass the counter |
| Cost regression | Median USD vs “stuff it in GPT-4.1/5” when it fits |

Optional later: LongBench-v2 CodeQA, BrowseComp-Plus style corpora, if licensing allows.

### Phase 7 — Later (explicitly not now)

- Train a small root model on traces (paper Appendix A: ~1k traces, improve REPL discipline)
- Depth > 1 as default for huge repos
- Mutation tools (edit, test, commit) on top of the same runtime
- Live web tools
- UI / notebook frontend

---

## 14. Testing strategy

Prefer **invariants** over golden transcripts (transcripts churn with prompts).

Must-have tests:

1. **History never contains the bound context** when context length > observation cap.
2. **Reserved names restored** after the model assigns `llm_query = 1`.
3. **FINAL_VAR** returns the variable, not a truncated print.
4. **Batch alignment:** 5 prompts, middle one fails, list length 5.
5. **Budget inheritance:** child timeout < parent remaining.
6. **Repo ignore:** `node_modules` not in `repo.files()`.
7. **Grep/read** return contents that were never copied into the initial metadata message.
8. **Parser** extracts a `repl` block and ignores prose.
9. **Prompt-token ceiling:** `complete()` is never invoked with `count_tokens(messages) > 100_000`. Oversize `llm_query` returns an error string.
10. **Instruction ceiling:** composed payload with 151 counted instructions raises before any send. Checking in `rlm/prompts/` stays ≤ 150 when combined with builtins + a one-line user query.
11. **Ceilings are not raisable:** constructing `RLM(max_prompt_tokens=100_001)` or `max_instructions=151` fails.
12. **Missing OpenAI key:** constructing a real `OpenAIClient` without `OPENAI_API_KEY` fails before any HTTP. FakeClient does not need a key.
13. **Docker is the only product REPL:** `completion()` without a daemon fails; it does not `exec` on the host. FakeEnv is unused by the CLI.
14. **Key and network stay out of the container:** Docker test asserts `OPENAI_API_KEY` is unset inside and outbound HTTP to a public URL fails.

Use a deterministic `FakeClient` and `FakeEnv` that return queued code strings / observations. Default CI does not require network or an API key. Docker tests are marked and skipped when the daemon is absent; they **are** required in the environment that ships a release.

---

## 15. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Root model dumps `print(context)` and rot returns through stdout | Truncate observations; prompt against it; optionally refuse prints over N chars and tell the model to slice |
| `llm_query` stuffed with a huge slice | Prompt guard returns an error string; model must slice. Never send >100k |
| Instruction bloat (tools, extra “always/never” rules) | Counter + CI on prompt files; fail closed at 151 rather than drop rules |
| Runaway cost from nested batched calls | Hard caps on concurrent subcalls, iterations, USD, tokens; remaining-budget children |
| Local `exec` as a security hole | Not the product path. Docker REPL; no silent fallback |
| API key inside the container | Never set `OPENAI_API_KEY` in container env; LM calls RPC to the host |
| Container reaches the internet | Default network: callback port only |
| Docker missing on the laptop | Fail at startup with install/start instructions; do not exec locally |
| PDF extraction garbage | Keep raw extract on disk; let the model slice; don't pretend OCR is solved |
| Model writes O(n) serial `llm_query` in a loop, 10× slower than batch | Prompt + examples for `llm_query_batched`; later, lint the code cell |
| RLM worse than base LM on *short* inputs (paper observation) | CLI can skip the scaffold below a token threshold, or document the tradeoff |
| OpenAI key leaked via CLI flags or logs | Key only from `OPENAI_API_KEY`; never `--api-key`; redact from trajectories |

---

## 16. Success criteria for “repo initialized”

This spec is done, and Phase 0 is complete, when:

1. This document lives at `.spec/001-initialize-repo.md` and describes problem, architecture, domains, and phased plan.
2. The repository has a Python package skeleton, toolchain, and README that states the thesis in one paragraph: *context stays in a REPL; the model recursively reads slices; the root context does not rot.*
3. Subsequent work can implement Phase 1 without re-litigating whether we are building a summarizer, a RAG pipeline, or an RLM. The 100k-token and 150-instruction ceilings, OpenAI-only backend, and Docker REPL are already decided.

v1 of the *product* (Phases 1–5) is successful when a user can point the CLI at a real repository and a folder of papers, ask a dense question, and get a cited answer whose trajectory shows the full source never entered the root window.

---

## 17. Open questions

Resolve during Phase 0–1 implementation, not by blocking this spec:

1. **Wrap `alexzhang13/rlm` vs reimplement.** Wrapper is faster; reimplement is cleaner for custom history policy and domain objects. Default bias: reimplement a small loop so this repo's invariants are testable without tracking upstream.
2. **Package name.** `rlm` is already the official library. Consider `recursivelm` / `rlm_lab` to avoid PyPI clash.
3. **Finish protocol.** `FINAL_VAR(x)` vs `answer["ready"]`. Pick one; adapters can come later.
4. **Default model ids.** Spec defaults are `gpt-5` / `gpt-5-mini` to match the paper. If the user's key does not have those ids, they override in `rlm.toml` — no code change. Confirm the exact ids at implementation time against current OpenAI docs.
5. **Git history as context.** v0 is working tree only; blame/log can be a Phase 5 tool.

---

## 18. References

- Zhang, A. L., Kraska, T., Khattab, O. *Recursive Language Models.* arXiv:2512.24601 (2025). https://arxiv.org/abs/2512.24601
- Zhang, A. L. *Recursive Language Models* (blog). https://alexzhang13.github.io/blog/2025/rlm/
- Official runtime: https://github.com/alexzhang13/rlm
- Context rot (working definition): quality of a model on a *fixed task* degrades as irrelevant or merely lengthy context grows, even when the gold span still fits in the window. Distinct from “the window overflowed.”
- Contrast: compaction agents, CodeAct, ReAct+BM25, MemWalker-style memory trees — useful baselines, insufficient for dense long context.

---

## 19. One-paragraph brief

Build an inference-time Recursive Language Model on **OpenAI** (`OPENAI_API_KEY`, official `openai` SDK) with a **Docker REPL**: a containerized persistent Python interpreter that holds the user's codebase or research corpus as data, a root LLM (`gpt-5` by default) on the host that only sees truncated metadata and writes code, and recursive cheap OpenAI calls (`gpt-5-mini` by default) invoked from that code via a host callback (the key never enters the container). Every LM call is refused if it would exceed **100k input tokens** or **150 instructions**. The point is to explore large repositories and document collections without ever loading them into a single context window, so context rot cannot eat the session. Ship a library, a CLI (`rlm ask`, `rlm research`), inspectable trajectories, and tests that prove the source text never entered the root history and that no send broke those two ceilings.
