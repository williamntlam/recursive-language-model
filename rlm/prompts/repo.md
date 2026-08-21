A `repo` object is bound for this session. The files are not in this message.

Methods:

1. `repo.tree(path=None, max_depth=3)` — directory tree. `repo.tree("src/foo")` scopes to a subdirectory.
2. `repo.glob(pattern)` — paths matching a glob.
3. `repo.read(path, start=None, end=None)` — 1-indexed inclusive line slice. Assign it; do not print it.
4. `repo.grep(pattern, glob=None)` — regex hits. Use `h.path`, `h.line_no`, `h.line` (or `h["path"]`). Print `len(hits)` and a few hits.
5. `repo.files()` — metadata (`path`, `n_bytes`, `n_lines`, `sha`) for text-ish files.
6. `repo.file_text(path)` — full file text as a value; assign it, do not print it.
7. `repo.measure(path, start=None, end=None)` — `n_chars` / `n_tokens` / `route` (no body). `repo.plan(spans)` — `{n_fit, n_child, n_chunks}` for `{path, start, end}` dicts. `repo.ask` — `fit` → `llm_query`; oversized → child.
8. `repo.explore(question)` — `rlm_query` with this same repo. Use only when `plan` says `n_child > 0` and you cannot chunk.

Strategy:

1. Grep or glob to get paths (print counts and a few hits).
2. `repo.file_text` + `measure_ast` / `ast.parse` **in this REPL**. `plan_reads` on the spans you care about (`name == "forward"`, …). Keep records in variables; do not print bodies.
3. `repo.ask` / `llm_query` only for `route=="fit"` spans code cannot decide. Prefer `n_chunks` leaves over `n_child` gpt-5 children.
4. `repo.explore` / `rlm_query_batched` only if `n_child > 0` and the span is still too large to chunk. Prefer `{"question": q, "path": p}` dicts if you batch.
5. Reduce into a name you assigned, then `FINAL_VAR("that_name")`. Never dump the repository into chat.
6. Cite answers with `path:start-end`.
