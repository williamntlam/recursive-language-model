# Development

## Layout

```
recursive-language-model/
├── docs/                          # this documentation
├── .spec/001-initialize-repo/     # product spec (source of design decisions)
├── README.md
├── pyproject.toml                 # package recursive-language-model, script rlm
├── uv.lock
├── .env.example
├── rlm.toml.example
├── rlm.yaml.example
├── docker/
│   ├── Dockerfile                 # rlm-repl:0.1.0
│   └── repl_server.py             # in-container cell runner + LM RPC client
├── rlm/                           # installable package
├── tests/
│   ├── fixtures/small_repo/
│   └── fixtures/tiny_corpus/
├── examples/
├── evals/                         # planned; not a v0 blocker
└── .gitignore                     # .env, .rlm/, *.pdf.rlm.txt, caches
```

Python 3.12+, uv, Ruff (`line-length = 100`, `E,F,I,UP,W`), pytest.

## Tooling

```bash
uv sync --group dev
uv run pytest
uv run ruff check rlm tests
uv run rlm --help
```

Optional PDF extra: `uv sync --extra pdf`.

Docker tests:

```bash
uv run pytest -m docker
```

The `docker` marker is registered in `pyproject.toml`. Those tests skip when the daemon is absent.

## Test strategy

Prefer **invariants** over golden transcripts (transcripts churn with prompts).

Helpers in `tests/util.py`:

- `make_rlm(tmp_path, script, **kwargs)` — `FakeClient` + `FakeEnv`, log dir under `tmp_path`
- `repl(code)` — wrap a cell in a `repl` fence
- `FIXTURE_REPO`, `FIXTURE_CORPUS`

`FakeClient` (`rlm.backends.base`) pops scripted model outputs. It raises if a ≥100k-token payload reaches `complete()`. A prompt containing `FAIL_PLEASE` raises so batched slots can record an error string.

Invariants covered today:

| Test module | What it locks |
|---|---|
| `test_history_policy.py` | Bound context does not leak into `hist` |
| `test_prompt_guard.py` | Never send ≥100k tokens or >150 instructions; static prompts fit; ceilings not raisable |
| `test_config.py` | TOML ↔ YAML equivalence; both-present error; auth keys rejected |
| `test_runtime_loop.py` | Reserved names restored; batch alignment; budget inheritance; `rlm_query` child |
| `test_cli.py` | `--help`; `--dry-run` without Docker |
| `test_repo_env.py` | Ignore rules, grep/read, path safety |
| `test_corpus_env.py` | Ingest, search/slice, distractors |
| `test_docker_repl.py` | Marked: no key in container, no public net, mount works |
| `test_report.py` | Static `report.html`; XSS escaped; `rlm report` |

## Fixtures

**`tests/fixtures/small_repo`** — tiny tree including `src/deep/secret.py` and a `node_modules/junk.js` that must **not** appear in `repo.files()`.

**`tests/fixtures/tiny_corpus`** — `paper_a.md`, `paper_b.md`, `distractor.md` for map-reduce + ignore-distractor tests.

## Prompts

Keep prompts in `rlm/prompts/*.md` so they can be versioned without code changes.

| File | Role |
|---|---|
| `root.md` | 8 RLM rules + builtin list |
| `repo.md` | `repo.*` API + strategy hints |
| `research.md` | `corpus.*` API + map-reduce hints |
| `leaf.md` | Extract / classify / summarize only |
| `catalog.py` | Exposed method names for the instruction counter |

Do not grow the generic rule list without removing something else. The 150-instruction ceiling is load-bearing.

## Evals

[`evals/README.md`](../evals/README.md) lists planned evals (NIAH, mini-OOLONG, fixture Q&A, history invariant, ceiling checks). They are **not** a v0 blocker. Add them after history policy, prompt ceilings, and both domains are solid.

## Design source of truth

If documentation and code disagree, **code wins**. If documentation and [`.spec/001-initialize-repo/spec.md`](../.spec/001-initialize-repo/spec.md) disagree on an unimplemented choice, the spec is the intended contract until the code lands.

Locked v0 decisions are summarized in [`.spec/001-initialize-repo/artifacts.md`](../.spec/001-initialize-repo/artifacts.md).
