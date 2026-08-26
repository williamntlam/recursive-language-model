A `corpus` object is bound for this session. Documents are not in this message.

Methods:

1. `corpus.search(pattern)` — regex hits. Use `h.doc_id`, `h.line_no`, `h.snippet` (or `h["doc_id"]`).
2. `corpus.get(id)` — a `Document` (`id`, `path`, `title`, `text`, `n_chars`). Assign `.text`; do not print it.
3. `corpus.slice(id, start, end)` — character slice of a document's text. Assign it.
4. `corpus.measure(doc_id, start=None, end=None)` — sizes a slice (no body). `corpus.plan(spans)` — `n_fit` / `n_child`. `corpus.ask` — `fit` → `llm_query`; oversized → child.
5. `corpus.explore(question, targets=[{"id": doc_id, "start": s, "end": e}])` — a child restricted to declared spans. Use it only for selected oversized spans.

`catalog` is a list of `{id, title, path, n_chars}` for every document.

Strategy:

1. First run a small inventory cell: filter/count catalog entries into compact metadata only; do not delegate or render there.
2. Deterministically classify and select evidence, then `corpus.measure` / `corpus.plan` selected docs. `corpus.ask` for `route=="fit"`; use scoped `explore` only if selected spans remain oversized.
3. Reduce child answers into rendered `report_text: str`, then `FINAL_VAR("report_text")`.
4. Cite from structured records `{doc_id, span, claim}` assembled in a variable.
5. Ignore distractors that do not bear on the query.
