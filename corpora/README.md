# Local corpora (gitignored)

Put markdown, text, HTML, or PDFs here to try `rlm research` (read-only synthesis over documents). Git ignores everything in this folder except this README.

```bash
# copy or clone documents into corpora/papers
uv run rlm research corpora/papers -- "Where do these documents disagree?"
```

`corpus.measure` / `corpus.plan` size docs the same way `repo.measure` sizes files. `explore` only if a document is still too large for one leaf.
