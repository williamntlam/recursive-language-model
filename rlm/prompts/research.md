A `corpus` object is bound for this session. Documents are not in this message.

Methods:

1. `corpus.search(pattern)` — regex hits. Use `h.doc_id`, `h.line_no`, `h.snippet` (or `h["doc_id"]`).
2. `corpus.get(id)` — a `Document` (`id`, `path`, `title`, `text`, `n_chars`). Assign `.text`; do not print it.
3. `corpus.slice(id, start, end)` — character slice of a document's text. Assign it.
4. `corpus.measure(doc_id, start=None, end=None)` — sizes a slice (no body). `corpus.plan(spans)` — `n_fit` / `n_child`. `corpus.ask` — `fit` → `llm_query`; oversized → child.
5. `corpus.explore(question)` — `rlm_query` with this same corpus. Use only when `n_child > 0` and you cannot chunk.

`catalog` is a list of `{id, title, path, n_chars}` for every document.

Strategy:

1. Filter with regex or keyword code using prior knowledge of the query.
2. `corpus.measure` / `corpus.plan` remaining docs. `corpus.ask` for `route=="fit"` spans; `explore` only if `n_child > 0`.
3. Reduce child answers into a name you assigned, then `FINAL_VAR("that_name")`.
4. Cite from structured records `{doc_id, span, claim}` assembled in a variable.
5. Ignore distractors that do not bear on the query.
