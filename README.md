# Recursive Language Model

Context stays in a REPL; the model recursively reads slices; the root context does not rot.

This is an inference-time **Recursive Language Model** (Zhang, Kraska, Khattab, [arXiv:2512.24601](https://arxiv.org/abs/2512.24601)): a runtime, CLI, and library that wrap OpenAI and treat an arbitrarily long prompt, repository, or document corpus as data in a **Docker Python REPL**. The parent model never receives the full source — only short metadata and truncated stdout. It writes Python that peeks, slices, and calls cheaper models on snippets. Results live in variables, not in chat. No LM call (parent or child) may have **100,000 or more input tokens** or **more than 150 instructions**.

## Requirements

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- Docker engine (the REPL never `exec`s model code on the host)
- `OPENAI_API_KEY` in the environment (or a gitignored `.env`)

## Install

```bash
uv sync --group dev
cp .env.example .env   # then put your key in .env
```

Build the REPL image on first real completion (or ahead of time):

```bash
docker build -t rlm-repl:0.1.8 -f docker/Dockerfile .
```

## Usage

```bash
uv run rlm ask ./pytorch -- "Where is autocast implemented, and how does it interact with bfloat16 on CPU?"
uv run rlm research ./papers -- "Where do these papers disagree about context rot?"
uv run rlm complete --context-file haystack.txt -- "Find the needle."
uv run rlm ask ./repo --dry-run -- "preview the manifest and prompt; no API, no container"
uv run rlm report .rlm/logs   # rebuild the static HTML timeline for the latest run
```

Python:

```python
from rlm import RLM, load_repo, load_corpus

rlm = RLM(verbose=True)
out = rlm.completion(query="Count mentions of La Union.", context=huge_string)
out = rlm.ask_repo(path="./pytorch", query="How does autograd handle views?")
out = rlm.research(path="./papers", query="Compare recursive vs compressive memory.")
print(out.response)
print(out.usage)
```

Config is **TOML or YAML** (`rlm.toml`, `rlm.yaml`, or `rlm.yml`). Same keys. Do not put both formats in the working directory. Auth is never in the file.

## Documentation

Full docs live in [`docs/`](docs/README.md): getting started, architecture, CLI, Python API, configuration, REPL, domains, runtime invariants, logging, and the module map.

## When not to use this

Short prompts are often worse under an RLM scaffold than a single base-model call (as in the paper). Use this when the source would overflow or rot a normal window.

## Tests

```bash
uv run pytest
```

Docker tests are skipped when the daemon is absent (`pytest -m docker` to select them).
