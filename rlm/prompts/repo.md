A `repo` object is bound for this session. The files are not in this message.

Methods:

1. `repo.tree(path=None, max_depth=3)` — directory tree. `repo.tree("src/foo")` scopes to a subdirectory.
2. `repo.glob(pattern)` — paths matching a glob.
3. `repo.read(path, start=None, end=None)` — 1-indexed inclusive line slice. Assign it; do not print it.
4. `repo.grep(pattern, glob=None)` — regex hits. Use `h.path`, `h.line_no`, `h.line` (or `h["path"]`). Print `len(hits)` and a few hits.
5. `repo.files()` — metadata (`path`, `n_bytes`, `n_lines`, `sha`) for text-ish files.
6. `repo.file_text(path)` — full file text as a value; assign it, do not print it.
7. `repo.measure(path, start=None, end=None)` — `n_chars` / `n_tokens` / `route` (no body). `repo.plan(spans)` — `{n_fit, n_child, n_chunks}` for `{path, start, end}` dicts. `repo.ask` — `fit` → `llm_query`; oversized → child.
8. `repo.explore(question, targets=[{"path": p, "start": s, "end": e}])` — a child restricted to declared spans. Use non-empty targets only for selected oversized spans; untargeted exploration is compatibility-only.

Strategy:

1. First run a small inventory cell: count/filter paths and print compact metadata only. Do not delegate or render the answer in that cell.
2. Classify that inventory with deterministic code, then inspect only selected evidence. `repo.file_text` + `measure_ast` / `ast.parse` stay in this REPL; use `repo.plan([{path, start, end}, ...])` for paths. Keep records in variables; do not print bodies.
3. `repo.ask` / `llm_query` only for `route=="fit"` spans code cannot decide. Prefer `n_chunks` leaves over `n_child` gpt-5 children.
4. `repo.explore` only if a selected span remains oversized after chunking; pass explicit targets. Never use a per-file global grep loop.
5. Reduce records into a rendered `report_text: str`, then `FINAL_VAR("report_text")`. Never dump the repository into chat.
6. Cite answers with `path:start-end`.
