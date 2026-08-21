# REPL

Model-generated Python runs in a **Docker container**. The host never `exec`s that code. Unit tests use an in-memory `FakeEnv` with the same namespace helpers; it is not a CLI environment.

## Persistent namespace

One container, one Python interpreter, for the life of a `completion` / `ask_repo` / `research` call. Variables survive across cells. Each `rlm_query` child gets a **new** container.

## How the model writes code

The root model must emit a fenced block:

````
```repl
# python here
FINAL_VAR("result")
```
````

The parser (`rlm.core.parse.extract_repl_code`) takes the **last** `repl` fence (case-insensitive), including an **unclosed** fence (body until end of the turn). If none, it falls back to ````python` / ````py`, then an unlabeled ```` fence. gpt-5 often writes a bare `repl` heading with no backticks, including after a prose preamble or glued to the previous line (`")repl`). That is treated as a cell too. Multiple bare `repl` headings in one turn are joined (intermediate heading lines are stripped). JSON/markdown/shell fences are ignored. If nothing executable is found, the runtime logs a preview, appends a reminder, and counts a consecutive error.

## Builtins always injected

```python
llm_query(prompt: str, model: str | None = None) -> str
llm_query_batched(prompts: list[str], model: str | None = None) -> list[str]
rlm_query(prompt: str, model: str | None = None) -> str
rlm_query_batched(prompts: list[str] | list[dict], model: str | None = None) -> list[str]
SHOW_VARS() -> str
FINAL(text) -> str
FINAL_VAR(name: str) -> str
```

Each `prompt` is a full LM payload and is subject to the [prompt guard](runtime.md): **< 100k tokens** and **≤ 150 instructions**. The runtime prepends a short leaf system prompt (`rlm/prompts/leaf.md`). If the model concatenates a huge slice into `llm_query`, the call returns an error string and does not hit the API.

Batch helpers are **index-aligned** and **per-item failure tolerant**: one failed leaf (including a prompt-budget failure) returns an error string in that slot; others succeed. Concurrency is capped by `max_concurrent_subcalls` (default 8). `rlm_query` / `rlm_query_batched` also accept `{"question": q, "path": p}` dicts and turn them into a child prompt that names that file.

`SHOW_VARS()` lists names with a size hint (`str n_chars=…`, `list len=…`) without dumping values.

`repo.ask(path, question, start=None, end=None)` and `corpus.ask(...)` read a slice: a tight span goes to `llm_query`, a larger read spawns `rlm_query`. `repo.explore(question)` / `corpus.explore(question)` always spawn a child RLM that **inherits the same repo or corpus**. Prefer `explore` over printing `repo.read`.

A cell's **last expression** is displayed like a notebook (compact repr). `FINAL` / `FINAL_VAR` as the last expression are not displayed. `print` of a large string is truncated in the container before it reaches the host.

### Finish protocol

Any of these ends the loop and becomes `Completion.response`:

| Form | Behavior |
|---|---|
| `FINAL(text)` | Stores `str(text)` as the answer |
| `FINAL_VAR("name")` or `FINAL_VAR(name)` | Looks up that name and `FINAL`s it. A bare identifier is quoted before exec. Raises `NameError` (with bound user names) if missing |
| `answer["ready"] = True` with `answer["value"]` | Honored if `_rlm_final` was not set |

`answer` starts as `{"ready": False, "value": None}`. Prefer `FINAL_VAR` so long answers never have to be printed.

## Reserved names

These are snapshotted at init and **restored after every cell**, so the model cannot clobber them:

`context`, `context_0`, `query`, `llm_query`, `llm_query_batched`, `rlm_query`, `rlm_query_batched`, `SHOW_VARS`, `FINAL`, `FINAL_VAR`, `answer`, `repo`, `corpus`, `catalog`, `manifest`

User-created names (`findings`, `hits`, …) persist.

`context_0` is a copy of `context` when the host did not bind it separately.

## Stdlib

Docker is the sandbox (`network_mode=none`, no API key, read-only `/workspace`). Inside the container the REPL is ordinary CPython, including `os`, `sys`, `ast`, `open`, `subprocess`, and the rest of the stdlib the model was trained on.

The only blocked import is `socket` (the host RPC sockets live under `/ipc`). Banned builtins: `breakpoint`, `exit`, `quit`, `help`. `__build_class__` is kept so `class` statements work. `pathlib` / `open` can see `/workspace` (read-only) and tmpfs.

The container image does not include the OpenAI SDK.

## Cell execution

`rlm.repl_ns.run_cell`:

1. `compile` + `exec` in the namespace with stdout/stderr redirected. If the last statement is an expression (and not `FINAL` / `FINAL_VAR`), it is evaluated and shown as a compact repr.
2. In the container, `SIGALRM` kills **local** Python after `cell_timeout_s` (config default 300s). That timer is **paused** for the duration of `llm_query` / `rlm_query`. The host waits for the cell until `--timeout` / `max_timeout_s` remains, or **blocks with no cap** when those are unset. `FakeEnv` does not use alarms.
3. Restore reserved names.
4. Return an `Observation`: truncated stdout/stderr (sent to the host), full lengths, sha256 of stdout, optional `final`, optional traceback in `error`.

Stdout shown to the **model** is further truncated by `max_observation_chars` on the host (see history policy). The underlying variables are not truncated.

## Docker IPC

Framing (`rlm.ipc`): 4-byte big-endian length + UTF-8 JSON. Max message 32 MiB.

Sockets (unix, under a host temp dir mounted at `/ipc`):

| Path | Direction | Role |
|---|---|---|
| `/ipc/repl.sock` | host → container | `init`, `exec`, `shutdown` |
| `/ipc/lm.sock` | container → host | `llm_query`, `llm_query_batched`, `rlm_query`, `rlm_query_batched` |

Init payload: `query`, `mode` (`string` / `repo` / `research`), `max_stdout_chars`, `cell_timeout_s`. The container binds workspace objects, then ACKs.

Image: `rlm-repl:0.1.11`. Built from `docker/Dockerfile` on first use if missing. Copies a **subset** of the package into the image (`ipc`, `repl_ns`, `errors`, `core/types`, `core/history`, `domains/repo`, `domains/corpus`, `repl_server.py`) — not the OpenAI client or runtime loop.

## Isolation recap

See [Architecture](architecture.md) for the full table. Practical consequences:

- `os.environ.get("OPENAI_API_KEY")` inside a cell is empty.
- Outbound HTTP from the container fails (`network_mode=none`).
- The user's tree is mounted **read-only** at `/workspace`. The model cannot scribble on it.
- Hung `while True` dies at the cell timeout.

If Docker is not running, `docker_client()` raises `StartupError` with a message to start the engine. There is no silent fallback to host `exec`.
