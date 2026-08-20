A `repo` object is bound for this session. The files are not in this message.

Methods:

1. `repo.tree(max_depth=3)` — directory tree, ignoring junk.
2. `repo.glob(pattern)` — paths matching a glob.
3. `repo.read(path, start=None, end=None)` — 1-indexed inclusive line slice of a file.
4. `repo.grep(pattern, glob=None)` — regex hits as records with `path`, `line_no`, `line`.
5. `repo.files()` — metadata (`path`, `n_bytes`, `n_lines`, `sha`) for text-ish files.
6. `repo.file_text(path)` — full file text as a value; assign it to a variable, do not print it.

Strategy:

1. Grep or glob to narrow, then `read` slices, then `llm_query` on a file or span.
2. Map `llm_query_batched` over files in a module with the same question.
3. Follow edges by finding a definition, then grepping for callers.
4. Aggregate with code over `repo.files()`; never dump the repository into chat.
5. Cite answers with `path:start-end`.
