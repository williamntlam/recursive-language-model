# Module reference

Installable package name: `recursive-language-model`. Import name: `rlm`. CLI: `rlm`.

## `rlm`

| Module | Role |
|---|---|
| `__init__.py` | Re-exports `RLM`, `Config`, `Completion`, `Usage`, `load_corpus`, `load_repo` |
| `api.py` | `RLM` facade: `completion`, `ask_repo`, `research`, `dry_run`; env factories |
| `cli.py` | argparse, `--` query split, exit-code mapping |
| `config.py` | `Config` dataclass, TOML/YAML load, discovery, hard ceilings |
| `envfile.py` | `.env` loader (does not override existing env vars) |
| `errors.py` | `RLMError` hierarchy |
| `ipc.py` | Length-prefixed JSON framing (`MAX_MESSAGE_BYTES = 32_000_000`) |
| `repl_ns.py` | Namespace, reserved names, restricted import, `run_cell`, `FINAL*` |

## `rlm.core`

| Module | Role |
|---|---|
| `runtime.py` | Iteration loop, `RuntimeHandler`, `leaf_complete`, `child_rlm`, `batched`, string metadata/workspace |
| `types.py` | `Message`, `Usage`, `Completion`, `LMResponse`, `Observation`, `PromptPayload` |
| `history.py` | `format_observation`, `compact_repr`, `measure_text`, `measure_ast`, `plan_reads`, `route_read_subcall`, `ASK_LEAF_CHARS` |
| `parse.py` | Last `repl` / `python` fence |
| `prompt_guard.py` | `count_tokens`, `count_instructions`, `assert_sendable` |
| `budgets.py` | `Budget`, `estimate_cost_usd`, `PRICES_PER_MILLION` |

## `rlm.backends`

| Module | Role |
|---|---|
| `base.py` | `LMClient` protocol, `FakeClient`, `RaisingClient` |
| `openai.py` | Official SDK; Chat Completions vs Responses for `gpt-5` / `o1` / `o3` |

## `rlm.environments`

| Module | Role |
|---|---|
| `base.py` | `Environment` protocol: `execute`, `close` |
| `docker.py` | `DockerEnv`, `CallbackServer`, `ensure_image`, `IMAGE_TAG = "rlm-repl:0.1.13"` |
| `fake.py` | In-memory REPL for tests |

## `rlm.domains`

| Module | Role |
|---|---|
| `repo.py` | `Repo`, `FileMeta`, `GrepHit`, `load_repo`, `repo_manifest`, ignore lists |
| `corpus.py` | `Corpus`, `Document`, `SearchHit`, ingest, `load_corpus`, `corpus_manifest` |

## `rlm.prompts`

| Module | Role |
|---|---|
| `__init__.py` | `compose_system_prompt`, `leaf_system_prompt`, `exposed_methods_for`, `load_prompt` |
| `catalog.py` | `ROOT_BUILTINS`, `REPO_METHODS`, `CORPUS_METHODS` |
| `root.md` / `repo.md` / `research.md` / `leaf.md` | Prompt text |

## `rlm.logging`

| Module | Role |
|---|---|
| `trajectory.py` | `TrajectoryLogger`, `redact`; writes `error.txt` on stderr / parse / abort |
| `html.py` | `write_report`, `resolve_run_dir` — static `report.html` |

## `docker/`

| File | Role |
|---|---|
| `Dockerfile` | `python:3.12-slim`, user `rlm` uid 1000, `PYTHONPATH=/opt/rlm` |
| `repl_server.py` | Bind workspace, serve `init`/`exec`/`shutdown`, RPC `llm_query*` to host |

## Important types

```python
@dataclass
class Message:
    role: str
    content: str

@dataclass
class Observation:
    stdout: str
    stderr: str
    total_stdout_len: int
    total_stderr_len: int
    sha256: str
    final: str | None = None
    error: str | None = None

@dataclass
class PromptPayload:
    system_prompt: str
    exposed_methods: list[str] = []
    user_query: str = ""
    extra_rules: list[str] = []
    developer_prompt: str = ""

@dataclass
class LMResponse:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""
```

`SubcallHandler` (`repl_ns.py`) is the interface the container RPC and `RuntimeHandler` implement: `llm_query`, `llm_query_batched`, `rlm_query`, `rlm_query_batched`.

## Constants worth searching

| Name | Where | Value |
|---|---|---|
| `HARD_MAX_PROMPT_TOKENS` | `config.py` | `99_999` |
| `HARD_MAX_INSTRUCTIONS` | `config.py` | `150` |
| `HARD_PROMPT_TOKEN_EXCLUSIVE` | `config.py` | `100_000` |
| `DEFAULT_CELL_TIMEOUT_S` | `config.py` | `300.0` |
| `ALLOWED_ENVIRONMENTS` | `config.py` | `{"docker"}` |
| `IMAGE_TAG` | `environments/docker.py` | `"rlm-repl:0.1.13"` |
| `ASK_LEAF_CHARS` | `core/history.py` | `24_000` (repo.ask / corpus.ask leaf cutoff) |
| `CHARS_PER_TOKEN` | `core/history.py` | `4` (REPL token estimate) |
| `PARENT_TOKEN_NUDGE` | `core/history.py` | `1500` |
| `HIST_KEEP_RECENT` | `core/history.py` | `4` |
| `RESERVED_NAMES` | `repl_ns.py` | tuple of protected identifiers |
| `BLOCKED_IMPORTS` | `repl_ns.py` | `{"socket"}` (host IPC) |
| `CHILD_QUERY` | `core/runtime.py` | fixed query string for nested RLMs |
