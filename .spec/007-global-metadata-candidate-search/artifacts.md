# 007 — Review artifacts

Companion to [`spec.md`](spec.md). If it conflicts with the specification, the
specification wins until changed.

**Status:** Draft · **Date:** 2026-08-26 · **Owner:** William Lam

---

## One paragraph

Before RLM reads any source body, scan the entire repository's *metadata* to
produce a recall-oriented, explainable candidate inventory. Rank paths by query
and conventional topology signals, include bounded metadata siblings, and make
the absence of semantic/source evidence explicit. Later measured inspection—not
this pass—determines what the code actually does.

## Locked decisions

| # | Decision | Choice |
|---|---|---|
| D1 | Source boundary | Candidate discovery never opens source files or invokes AST/grep/read/file_text. |
| D2 | Globality | It may enumerate all eligible repository paths and filesystem metadata. |
| D3 | Relatedness | Edges are filename/package/test conventions only; they are never called imports or dependencies. |
| D4 | Ranking | Deterministic, versioned weights with every signal exposed. |
| D5 | Recall | Bounded sibling/package expansion improves recall but always reports caps/truncation. |
| D6 | Evidence | Candidates are hypotheses, not source-grounded claims. |
| D7 | Integration | Direct REPL can call it; spec-006 planning may consume it as an optional prefilter. |
| D8 | Privacy | Metadata traces carry counts/digests, never paths, queries, or source. |

## Intended execution shape

```text
query + repository path/metadata
              │
              ▼
global content-free candidate inventory
  (scores, signals, metadata relationships, uncertainty)
              │
       ┌──────┴───────────────┐
       ▼                      ▼
 root REPL selects      optional 006 planner selects
 measured spans                 candidate IDs
       └──────┬───────────────┘
              ▼
    source read / AST only after selection
```

## Important limitation

This cannot discover a relationship that exists only inside a source body.
For example, it cannot prove an import, inheritance edge, registration, or
call-site link. Its value is low-cost, global *candidate recall*, not semantic
completeness. A later bounded source-inspection phase must verify every claim.

## Review questions

- Which filename and directory conventions should be generic versus configured
  per repository family?
- What candidate/neighbor cap gives useful recall without making the compact
  manifest too large?
- Which curated fixtures best demonstrate non-obvious relevant files that this
  intentionally cannot find without an explicit expansion rule?
- Should filesystem modification time be omitted by default to maximize
  reproducibility across checkouts?
