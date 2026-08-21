# Python API

Public exports (`rlm/__init__.py`):

```python
from rlm import RLM, Config, Completion, Usage, load_corpus, load_repo
```

## `RLM`

Facade over config, OpenAI, Docker, and the iteration loop.

### Constructor

```python
RLM(
    *,
    config: Config | None = None,
    root_model: str | None = None,
    leaf_model: str | None = None,
    environment: str | None = None,          # must be "docker" if set
    max_depth: int | None = None,
    max_iterations: int | None = None,
    max_prompt_tokens: int | None = None,
    max_instructions: int | None = None,
    max_observation_chars: int | None = None,
    max_budget_usd: float | None = None,
    max_timeout_s: float | None = None,
    cell_timeout_s: float | None = None,
    max_concurrent_subcalls: int | None = None,
    max_consecutive_errors: int | None = None,
    log_dir: str | None = None,
    verbose: bool | None = None,
    extra_instructions: list[str] | None = None,
    config_path: str | Path | None = None,
)
```

Omitted kwargs fall through to `load_config` (file + defaults). See [Configuration](configuration.md).

`environment` other than `"docker"` raises `ConfigError`. There is no in-process product REPL.

Internal-only (tests): `_client` and `_env_factory` inject `FakeClient` / `FakeEnv`. Do not use them in application code.

### `RLM.from_config(path, **kwargs) -> RLM`

Loads `path` then applies the same kwargs as the constructor.

```python
rlm = RLM.from_config("rlm.yaml", verbose=True)
rlm = RLM.from_config("rlm.toml", max_budget_usd=2.0)
```

### `completion(query: str, context: str) -> Completion`

Generic long-prompt path (the paper-shaped regression surface).

- Writes `context` to a temp dir as `context.txt`, mounts it read-only.
- Binds `query` and `context` in the REPL.
- Initial metadata is length + sha256 + a 200-character prefix — **not** the full string.
- Cleans up the temp workspace when the run ends.

```python
out = rlm.completion(
    query="Count how many rows mention La Union and classify each.",
    context=huge_string,
)
```

### `ask_repo(path: str | Path, query: str) -> Completion`

Loads `path` with `load_repo`, binds `query`, `repo`, and `manifest`, uses the repo system prompt. Workspace is the repo root (not deleted afterward).

```python
out = rlm.ask_repo(path="./pytorch", query="How does autograd handle views?")
```

### `research(path: str | Path, query: str) -> Completion`

Loads documents with `load_corpus`. If `path` is a file, the workspace is its parent directory. Binds `query`, `corpus`, and `catalog`. Uses the research system prompt.

```python
out = rlm.research(path="./papers", query="Compare recursive vs compressive memory.")
```

`load_corpus` also accepts a sequence of paths; the `RLM.research` method currently takes a single path.

### `dry_run(query: str, metadata: str, domain: str | None = None) -> str`

Composes the system prompt for `domain` (`"repo"`, `"research"`, or `None`), counts instructions and tokens, returns a printable preview. Raises `ConfigError` if instructions exceed the cap. No Docker, no API.

## Return types

```python
@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float | None = None
    iterations: int = 0
    subcalls: int = 0

@dataclass
class Completion:
    response: str
    usage: Usage
    trajectory: Path | None = None
```

`trajectory` is the run directory under `log_dir` (see [Logging](logging-and-errors.md)).

## Loaders

```python
from rlm.domains.repo import load_repo, Repo, FileMeta, GrepHit
from rlm.domains.corpus import load_corpus, Corpus, Document, SearchHit

repo = load_repo("./pytorch")                 # Repo
corpus = load_corpus("./papers")              # Corpus
corpus = load_corpus(["a.md", "b.pdf"])       # concatenated, re-id'd
```

Loaders are useful on their own for inspection; the RLM methods call them internally.

## Typical session

```python
from rlm import RLM

rlm = RLM(verbose=True, max_budget_usd=2.00, max_timeout_s=180)
out = rlm.ask_repo("./pytorch", "Where is autocast implemented?")
print(out.response)
print(f"tokens={out.usage.prompt_tokens}+{out.usage.completion_tokens}")
print(f"cost=${out.usage.cost_usd:.4f}  log={out.trajectory}")
```
