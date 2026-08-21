# Domains

The generic RLM binds a string. This product also binds two structured worlds. In every case the source is a **variable**, not prompt text.

## String context — `rlm.completion` / `rlm complete`

Bound names:

- `query: str`
- `context: str` (and `context_0`)

Initial metadata (what the root actually sees):

```
Context bound as `context` (N chars, sha256=abcd…).
Short prefix: '…first 200 chars…'
Access via slices, regex, and llm_query. Do not print the full context.
```

The full string is written to a temp `context.txt` and mounted at `/workspace`. Peek with Python (`context[i:j]`, `re.findall`, chunking loops). Do not `print(context)`.

## Repository — `rlm ask` / `RLM.ask_repo`

Load a directory (git working tree or any folder) as `repo`. There is **no bash**.

### Bound names

- `query: str`
- `repo: Repo`
- `manifest: str` (host-side; the same text is the initial metadata message)

### Manifest shape

```
Repository: /path/to/pytorch
Files: 12,403  |  Text-ish bytes: 184MB  |  Git HEAD: abc123
Top-level:
  pytorch/
  ├── aten/
  └── torch/
Use repo.tree(), repo.grep(), repo.file_text + ast, repo.measure, repo.plan, repo.ask.
Do not print entire files. Classify with code here; llm_query tight slices;
child RLM only if plan_reads / repo.plan says route is child.
```

`Git HEAD` is the short hash from `.git/HEAD` when present, else `none`.

### `Repo` methods

```python
repo.tree(path: str | int | None = None, max_depth: int = 3, ignore: Sequence[str] | None = None) -> str
repo.glob(pattern: str) -> list[str]
repo.read(path: str, start: int | None = None, end: int | None = None) -> str
repo.grep(pattern: str, glob: str | None = None) -> list[GrepHit]
repo.files() -> list[FileMeta]
repo.file_text(path: str) -> str
repo.measure(path: str, start: int | None = None, end: int | None = None) -> dict
repo.plan(spans: list | dict | str) -> dict
repo.ask(path: str, question: str, start: int | None = None, end: int | None = None) -> str
repo.explore(question: str) -> str
```

| Method | Behavior |
|---|---|
| `tree` | ASCII tree. First arg may be a subdirectory (`repo.tree("src/foo")`) or a depth (`repo.tree(3)`). Junk directories omitted |
| `glob` | `fnmatch` on relative path or basename |
| `read` | **1-indexed inclusive** line slice when `start`/`end` given; full file if both omitted |
| `grep` | Regex over text-ish files. Hits: `path`, `line_no`, `line` (line truncated to 400 chars). Attribute or `h["path"]` / `h[0]` |
| `files` | `path`, `n_bytes`, `n_lines`, `sha` (16 hex chars) for text-ish files only |
| `file_text` | Full UTF-8 text as a **value**. Assign it; do not print it |
| `measure` | `n_chars` / `n_tokens` / `route` (`fit` or `child`) for a span. No body. Optional `chunks` when oversized |
| `plan` | `{n_fit, n_child, n_chunks, spans}` for path strings or `{path, start, end}` dicts |
| `ask` | Slice under 24k chars (`ASK_LEAF_CHARS`) → `llm_query`; larger read → child RLM with the same repo |
| `explore` | Always `rlm_query` with this repo. Use when `n_child > 0` and you cannot chunk into leaves |

Paths are resolved under `repo.root`. Escaping the root raises `ValueError` (`Path.relative_to`).

### Ignore rules

Directory names skipped: `.git`, `.hg`, `.svn`, `.idea`, `.vscode`, `.venv`, `venv`, `node_modules`, `__pycache__`, `.mypy_cache`, `.ruff_cache`, `.pytest_cache`, `.tox`, `.eggs`, `dist`, `build`, `target`, `vendor`, `.next`, `coverage`, `.rlm`, `.egg-info`.

Lockfiles skipped: `package-lock.json`, `yarn.lock`, `pnpm-lock.yaml`, `Cargo.lock`, `poetry.lock`, `uv.lock`, `Gemfile.lock`, `composer.lock`.

Binary / media suffixes skipped (`.pyc`, `.so`, `.png`, `.pdf`, `.zip`, fonts, …). Extra `ignore` globs can be passed to `Repo(...)`.

Text-ish detection: known source suffixes, names like `Makefile` / `Dockerfile` / `LICENSE` / `README`, otherwise a UTF-8 sample without NUL.

### Intended patterns

1. Narrow then classify — grep / glob → `file_text` + `measure_ast` / regex in this REPL. `plan_reads` on the spans you care about.
2. Map leftover slices — `llm_query_batched` (or `repo.ask`) on `route=="fit"` functions code cannot decide. Spawn `n_child` children only for oversized spans, or split them into `n_chunks` leaves.
3. Follow edges — find a definition, grep for callers.
4. Aggregate with code over `repo.files()`, not by stuffing the repo into chat.

Cite answers as `path:start-end`.

**Out of scope for v0:** applying patches, running tests, committing, LSP/type graphs, remote GitHub without a local clone.

## Research corpus — `rlm research` / `RLM.research`

Load a directory (or a single file) as `corpus`.

### Bound names

- `query: str`
- `corpus: Corpus`
- `catalog: list[dict]` — `{id, title, path, n_chars}` for every document

### Manifest shape

```
Corpus: N documents.
Bound as `corpus` and `catalog` (list of id/title/path/n_chars).
Use corpus.search, corpus.get, corpus.measure, corpus.ask. Do not print full documents. Explore only if plan says route is child.
Catalog preview:
  doc-0001: 'Title'  path=paper_a.md  n_chars=1234
  ...
```

Preview is the first 12 rows; the rest live in `catalog`.

### Ingest

Walked files (skips `.git`, `.rlm`, `__pycache__`, `.venv`, `venv`):

| Extension | Handling |
|---|---|
| `.md`, `.txt`, `.rst` | UTF-8 as-is |
| `.html`, `.htm` | Tags stripped (`script`/`style` skipped) |
| `.pdf` | `pypdf` if installed; text cached next to the PDF as `<name>.pdf.rlm.txt` |
| other | skipped |

Document ids are `doc-0001`, `doc-0002`, … in sorted path order. Title is the first `# ` heading, else the first non-empty line (120 chars), else the stem.

PDF extra:

```bash
uv sync --extra pdf
```

If `pypdf` is missing, PDFs are skipped. Sidecar `.pdf.rlm.txt` files are gitignored (`*.pdf.rlm.txt`).

### `Corpus` methods

```python
corpus.search(pattern: str) -> list[SearchHit]   # doc_id, line_no, snippet[:400]
corpus.get(id: str) -> Document                  # id, path, title, text, n_chars
corpus.slice(id: str, start: int, end: int) -> str   # Python character slice
corpus.measure(doc_id: str, start: int | None = None, end: int | None = None) -> dict
corpus.plan(spans: list | dict | str) -> dict
corpus.ask(doc_id: str, question: str, start: int | None = None, end: int | None = None) -> str
corpus.explore(question: str) -> str
```

`Document.text` is the full extracted string. Assign it; slice it; `llm_query` a piece. Do not print the whole document. `corpus.measure` / `corpus.plan` match `repo.measure` / `repo.plan` (sizes, no bodies; `n_fit` / `n_child`).

### Intended patterns

1. Filter with regex / keywords from the query.
2. `corpus.measure` / `corpus.plan` remaining docs. `corpus.ask` for `route=="fit"` spans; `explore` only if `n_child > 0`.
3. Reduce in the root (or a second-stage `rlm_query`) over claim objects.
4. Cite from structured records `{doc_id, span, claim}` assembled in a variable.
5. Ignore distractors that do not bear on the query.

**Out of scope for v0:** live web search, DOI / citation graphs, perfect PDF layout or OCR.

## Domain prompts

System prompt = `rlm/prompts/root.md` plus one of:

- `rlm/prompts/repo.md`
- `rlm/prompts/research.md`

Leaves always use `rlm/prompts/leaf.md`. Authoring budget: generic ≤ 40 instruction units, one domain ≤ 30, user query ≤ 20, composed **≤ 150**. CI counts this (`tests/test_prompt_guard.py`).
