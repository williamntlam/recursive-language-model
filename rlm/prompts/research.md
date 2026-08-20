A `corpus` object is bound for this session. Documents are not in this message.

Methods:

1. `corpus.search(pattern)` — regex hits as records with `doc_id`, `line_no`, `snippet`.
2. `corpus.get(id)` — a `Document` (`id`, `path`, `title`, `text`, `n_chars`).
3. `corpus.slice(id, start, end)` — character slice of a document's text.

`catalog` is a list of `{id, title, path, n_chars}` for every document.

Strategy:

1. Filter with regex or keyword code using prior knowledge of the query.
2. Map `llm_query` over remaining docs: extract claims relevant to the query, with quotes.
3. Reduce in the root (or a second-stage `rlm_query`) over the list of claim objects.
4. Cite from structured records `{doc_id, span, claim}` assembled in a variable.
5. Ignore distractors that do not bear on the query.
