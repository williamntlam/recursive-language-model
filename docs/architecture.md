# Architecture

The host process owns the RLM loop, OpenAI calls, prompt guard, and trajectory log. The container owns a persistent Python interpreter and any `repo` / `corpus` / `context` bytes it is allowed to see.

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
│  - budgets (depth, iterations, USD, tokens, time, errors)       │
│  - prompt guard (<100k tokens, ≤150 instructions per call)      │
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

## Host vs container

```
Host                                              Container (rlm-repl:0.1.7)
────                                              ─────────────────────────
RLM loop                                          persistent Python interpreter
OpenAI client + OPENAI_API_KEY                    context / repo / corpus variables
prompt guard                                      llm_query stubs → RPC to host
LM callback server (unix socket)  ◄── JSON ──►    execute ```repl``` cells
bind-mount workspace (ro)  ──────────────────►    /workspace
IPC dir (rw)               ──────────────────►    /ipc
```

`llm_query` and `rlm_query` are called **from code inside the container**. The container must not receive `OPENAI_API_KEY`. For the duration of a completion the host listens on a unix socket; the injected `llm_query` is an RPC client to that socket. The container network mode is `none` — no public internet, only the bind-mounted IPC directory.

## One query, end to end

```
User: rlm ask ./repo -- "How does autocast work?"
        │
        ▼
Host: load config, require OPENAI_API_KEY
      start Docker, mount repo read-only at /workspace
      bind query + repo in the container (not in the OpenAI prompt)
      parent hist = system prompt + short manifest + user query
        │
        ▼
Loop:  gpt-5 writes ```repl``` Python
       container executes (grep / read / llm_query slices)
       host appends truncated stdout to hist   ← never the file dump
       until FINAL / FINAL_VAR / answer["ready"]
        │
        ▼
Return answer + usage + trajectory directory
```

Each `rlm_query` child is a full RLM: **its own** container, callback socket, and remaining budget. There is no Docker-in-Docker. Repo/research children **inherit the same workspace**, so they can keep grepping; they do not need the parent to stuff the file into the prompt. Fan out with `rlm_query_batched` / `repo.explore`; nest again when a piece is still large.

## How context enters the container

Host objects are not pickled across the boundary.

| Mode | Host | Container |
|---|---|---|
| String (`completion`) | Write `context.txt` into a temp workspace, mount it | `context = Path("/workspace/context.txt").read_text()` |
| Repo (`ask`) | Bind-mount the directory read-only | `repo = Repo("/workspace")` |
| Research | Bind-mount the corpus directory read-only | `corpus = Corpus(ingest_path("/workspace"))` plus `catalog` |

Reserved functions (`llm_query`, …) are injected by the in-container REPL server at init, not imported from the host process.

## Package layout (runtime path)

```
CLI (rlm.cli)  →  RLM (rlm.api)  →  Runtime (rlm.core.runtime)
                                        │
                    ┌───────────────────┼───────────────────┐
                    ▼                   ▼                   ▼
              OpenAIClient        DockerEnv            TrajectoryLogger
              (or FakeClient)     (or FakeEnv)         .rlm/logs/...
                    │                   │
                    │                   ├─ CallbackServer  (host, lm.sock)
                    │                   └─ container       (repl_server.py)
                    │                          │
                    └──── leaf / child LM ◄────┘  RPC over /ipc/lm.sock
```

## Isolation defaults

| Knob | Value |
|---|---|
| Image | `rlm-repl:0.1.7` from `docker/Dockerfile` (`python:3.12-slim`, non-root uid 1000) |
| Network | `network_mode="none"` |
| `OPENAI_API_KEY` in container | unset |
| Root filesystem | read-only; tmpfs on `/tmp` and `/repl` (64 MiB each) |
| Host mounts | workspace → `/workspace` (ro); IPC dir → `/ipc` (rw) |
| User | `1000:1000` |
| Capabilities | `cap_drop=["ALL"]`, `no-new-privileges` |
| Memory | 2 GiB |
| CPUs | 1 |
| PIDs | 256 |
| Cell timeout | `cell_timeout_s` (default 300s) `SIGALRM` for local Python; paused during host RPCs. Host wait is remaining `max_timeout_s`, or unlimited if unset |

`FakeEnv` implements the same `execute(code) -> Observation` protocol for unit tests. It is **not** selectable from the CLI. There is no `--env local`.

## OpenAI backend

v0 talks to **OpenAI only**, via the official `openai` SDK.

- Auth: `OPENAI_API_KEY` from the environment or `.env`. Never a CLI flag.
- Root / any node with a REPL: `gpt-5` by default (`root_model`).
- Leaves (`llm_query`): `gpt-5-mini` by default (`leaf_model`).
- Model ids starting with `gpt-5`, `o1`, or `o3` use the **Responses** API; others use **Chat Completions**.
- Cost is estimated from `tiktoken`-reported usage and an in-repo price table when OpenAI does not report dollars.

See [Runtime](runtime.md) for the prompt guard that wraps every send.
