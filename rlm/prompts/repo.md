A `repo` object is bound for this session. The files are not in this message.

Methods:

1. `repo.tree(path=None, max_depth=3)` — directory tree. `repo.tree("src/foo")` scopes to a subdirectory.
2. `repo.glob(pattern)` — paths matching a glob.
3. `repo.read(path, start=None, end=None)` — 1-indexed inclusive line slice. Assign it; do not print it.
4. `repo.grep(pattern, glob=None)` — regex hits. Use `h.path`, `h.line_no`, `h.line` (or `h["path"]`). Print `len(hits)` and a few hits.
5. `repo.files()` — metadata (`path`, `n_bytes`, `n_lines`, `sha`) for text-ish files.
6. `repo.file_text(path)` — full file text as a value; assign it, do not print it.
7. `repo.ask(path, question, start=None, end=None)` — tight slice → `llm_query`; larger read → child RLM.
8. `repo.explore(question)` — `rlm_query` with this same repo. Default way to investigate a file or module.

Strategy:

1. Grep or glob to get paths (print counts and a few hits).
2. Spawn `repo.explore` / `rlm_query` per interesting file or module. The child has the same `repo`.
3. Use `repo.ask` only for a handful of lines you have already isolated.
4. Map `rlm_query_batched` over files in a module with the same question.
5. Reduce child answers in variables here; never dump the repository into chat.
6. Cite answers with `path:start-end`.
