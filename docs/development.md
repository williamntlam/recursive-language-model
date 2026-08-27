# Development

## Layout

```
recursive-language-model/
├── docs/                          # this documentation
├── .spec/001-initialize-repo/     # product spec (source of design decisions)
├── .spec/003-harbor-readonly-evaluations/ # Harbor evaluation reference spec
├── .githooks/                     # version-controlled repository hooks
├── CHANGELOG.md                   # timestamped changes required before pushes
├── README.md
├── LICENSE                        # MIT
├── pyproject.toml                 # package recursive-language-model, script rlm
├── uv.lock
├── .env.example
├── rlm.toml.example
├── rlm.yaml.example
├── docker/
│   ├── Dockerfile                 # rlm-repl:0.1.14
│   └── repl_server.py             # in-container cell runner + LM RPC client
├── rlm/                           # installable package
├── tests/
│   ├── unit/                      # focused deterministic contracts
│   ├── integration/               # multi-component and Docker-boundary workflows
│   ├── harbor/                    # deterministic Harbor task/verifier checks
│   ├── eval_support/              # deterministic checks for opt-in eval tooling
│   ├── fixtures/small_repo/
│   └── fixtures/tiny_corpus/
├── examples/
├── codebases/                     # README tracked; clones gitignored
├── corpora/                       # README tracked; document dumps gitignored
├── evals/                         # Harbor tasks and legacy opt-in LLM judges
└── .gitignore                     # .env, .rlm/, /codebases/*, /corpora/*, caches
```

Python 3.12+, uv, Ruff (`line-length = 100`, `E,F,I,UP,W`), pytest.

## Tooling

```bash
uv sync --group dev
# Product contracts only; no Docker, eval-support, or Harbor task checks.
uv run pytest -m "not docker and not eval_support and not harbor"
# All deterministic checks.
uv run pytest
uv run ruff check rlm tests
uv run rlm --help
uv run pytest -m harbor
uv run pytest -m eval_support
```

Optional PDF extra: `uv sync --extra pdf`.

Docker tests:

```bash
uv run pytest -m docker
```

The `docker`, `eval_support`, and `harbor` markers are registered in
`pyproject.toml`. Docker marks only tests that start a container; those tests
skip when the daemon is absent.

## Test strategy

Prefer **invariants** over golden transcripts (transcripts churn with prompts).
Follow the lightweight input/output and Arrange → Act → Assert conventions in
[`tests/README.md`](../tests/README.md); they standardize observable contracts
without forcing unrelated test types through one fixture or result wrapper.

Helpers in `tests/util.py`:

- `make_rlm(tmp_path, script, **kwargs)` — named `RLMHarness` with `FakeClient`
  + `FakeEnv`, log dir under `tmp_path`; use `.rlm` / `.client` or tuple unpacking
- `repl(code)` — wrap a cell in a `repl` fence
- `FIXTURE_REPO`, `FIXTURE_CORPUS`

`FakeClient` (`rlm.backends.base`) pops scripted model outputs. It raises if a ≥100k-token payload reaches `complete()`. A prompt containing `FAIL_PLEASE` raises so batched slots can record an error string.

Invariants covered today:

| Test module | What it locks |
|---|---|
| `unit/` | Prompt/history/config/REPL/read-planning contracts |
| `integration/` | CLI, repository/corpus, runtime, tracing, reports, and Docker boundary workflows |
| `eval_support/` | Cases and helpers for opt-in judges and architecture benchmarks; no live calls |
| `harbor/` | Harbor task layout and deterministic verifier behavior |

## Fixtures

**`tests/fixtures/small_repo`** — tiny tree including `src/deep/secret.py` and a `node_modules/junk.js` that must **not** appear in `repo.files()`.

**`tests/fixtures/tiny_corpus`** — `paper_a.md`, `paper_b.md`, `distractor.md` for map-reduce + ignore-distractor tests.

## Prompts

Keep prompts in `rlm/prompts/*.md` so they can be versioned without code changes.

| File | Role |
|---|---|
| `root.md` | RLM rules (classify in REPL; leaf vs child) + builtin list |
| `repo.md` | `repo.*` API including `measure` / `plan` + strategy |
| `research.md` | `corpus.*` API including `measure` / `plan` + strategy |
| `leaf.md` | Extract / classify / summarize only |
| `catalog.py` | Exposed method names for the instruction counter (`measure`, `measure_ast`, `plan_reads`, `repo.measure`, `repo.plan`, …) |

Do not grow the generic rule list without removing something else. The 150-instruction ceiling is load-bearing.

## Evaluations

[Harbor tasks](evaluations.md) are the supported path for benchmarking an
autonomous agent. The checked-in `rlm-reading-contracts` task is read-only:
the agent inspects a source snapshot and writes an answer artifact, while the
Harbor verifier awards a deterministic numeric reward. Install Harbor with
`uv tool install harbor`; local runs need Docker and an agent adapter.

`tests/harbor/` contains the fast deterministic checks for that task dataset.
They run in ordinary pytest and do not require Docker, an API key, or an agent.

The source-grounded Transformers census and synthetic 8k–500k retrieval ladder
remain legacy, opt-in RLM development utilities. Their deterministic case and
judge-helper checks live in `tests/eval_support/` and are marked
`eval_support`; only the live runners require Docker and OpenAI API budget and
must be run explicitly.

The judge results are written to gitignored `evals/results/`. For rubric,
evidence, and expansion guidance, see
[`docs/transformers-judge.md`](transformers-judge.md). Future NIAH,
mini-OOLONG, fixture Q&A, history-invariant, and prompt-ceiling cases remain
useful additions.

## Change tracking and hooks

Update [`CHANGELOG.md`](../CHANGELOG.md) before every GitHub push that changes
the repository. Each Unreleased entry needs a local `YYYY-MM-DD HH:MM TZ`
timestamp. `.githooks/pre-push` checks that the outgoing commits include a
changelog update; this clone activates it with:

```bash
git config core.hooksPath .githooks
```

Use `git push --no-verify` only for an intentional emergency bypass.

## Design source of truth

If documentation and code disagree, **code wins**. If documentation and [`.spec/001-initialize-repo/spec.md`](../.spec/001-initialize-repo/spec.md) disagree on an unimplemented choice, the spec is the intended contract until the code lands.

Locked v0 decisions are summarized in [`.spec/001-initialize-repo/artifacts.md`](../.spec/001-initialize-repo/artifacts.md).
