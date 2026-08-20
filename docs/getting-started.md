# Getting started

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- A running **Docker engine** (Desktop or daemon). Real completions never `exec` model code on the host.
- `OPENAI_API_KEY` in the process environment or a gitignored `.env`

Optional:

- `OPENAI_ORG_ID`, `OPENAI_PROJECT`
- PDF ingest: install the `pdf` extra (`pypdf`)

## Install

From the repository root:

```bash
uv sync --group dev
cp .env.example .env   # then put your key in .env
```

PDF extraction for `rlm research`:

```bash
uv sync --group dev --extra pdf
```

Build the REPL image on first real completion, or ahead of time:

```bash
docker build -t rlm-repl:0.1.0 -f docker/Dockerfile .
```

The runtime builds this tag automatically if it is missing and Docker is reachable.

## First queries

The query always comes **after `--`**. Everything before `--` is flags and paths.

```bash
# Repository Q&A
uv run rlm ask ./pytorch -- "Where is autocast implemented, and how does it interact with bfloat16 on CPU?"

# Document corpus
uv run rlm research ./papers -- "Where do these papers disagree about context rot?"

# Generic string context
uv run rlm complete --context-file haystack.txt -- "Find the needle."

# Preview prompt + manifest; no API, no container
uv run rlm ask ./repo --dry-run -- "preview the manifest and prompt"
```

Stdout is the answer. Stderr gets a one-line usage footer (`tokens`, estimated `cost`, iterations, subcalls, trajectory path).

## Python

```python
from rlm import RLM, load_repo, load_corpus

rlm = RLM(verbose=True)

out = rlm.completion(query="Count mentions of La Union.", context=huge_string)
out = rlm.ask_repo(path="./pytorch", query="How does autograd handle views?")
out = rlm.research(path="./papers", query="Compare recursive vs compressive memory.")

print(out.response)
print(out.usage)
print(out.trajectory)  # .rlm/logs/<timestamp>-<id>/
```

Load tunables from a file:

```python
rlm = RLM.from_config("rlm.yaml")
```

## Config

Copy [`rlm.toml.example`](../rlm.toml.example) or [`rlm.yaml.example`](../rlm.yaml.example) to `rlm.toml` **or** `rlm.yaml` in the working directory. Do not put both formats in cwd. Auth never belongs in the file — only `OPENAI_API_KEY`.

See [Configuration](configuration.md).

## Tests (no API key required)

```bash
uv run pytest
```

Docker-backed tests are skipped when the daemon is absent. Select them with `pytest -m docker`.

## Examples

| Script | What it does |
|---|---|
| [`examples/ask_small_repo.py`](../examples/ask_small_repo.py) | `ask_repo` on the current directory |
| [`examples/research_tiny_corpus.py`](../examples/research_tiny_corpus.py) | `research` on `tests/fixtures/tiny_corpus` |

Both need Docker and `OPENAI_API_KEY`.
