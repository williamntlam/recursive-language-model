A `corpus` object is bound for this session. Documents are not in this message.

Methods:

1. `corpus.search(pattern)` — regex hits. Use `h.doc_id`, `h.line_no`, `h.snippet` (or `h["doc_id"]`).
2. `corpus.get(id)` — a `Document` (`id`, `path`, `title`, `text`, `n_chars`). Assign `.text`; do not print it.
3. `corpus.slice(id, start, end)` — character slice of a document's text. Assign it.
4. `corpus.ask(doc_id, question, start=None, end=None)` — tight slice → `llm_query`; larger doc → child RLM.
5. `corpus.explore(question)` — `rlm_query` with this same corpus. Default way to work a document.

`catalog` is a list of `{id, title, path, n_chars}` for every document.

Strategy:

1. Filter with regex or keyword code using prior knowledge of the query.
2. Spawn `corpus.explore` / `rlm_query` (or `rlm_query_batched`) per remaining document.
3. Reduce child answers into a name you assigned, then `FINAL_VAR("that_name")`.
4. Cite from structured records `{doc_id, span, claim}` assembled in a variable.
5. Ignore distractors that do not bear on the query.
