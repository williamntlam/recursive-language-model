# 008 — Review artifacts

Companion to [`spec.md`](spec.md). If it conflicts with the specification, the
specification wins until changed.

**Status:** Draft · **Date:** 2026-08-26 · **Owner:** William Lam

---

## One paragraph

Provide an explicitly expensive `rlm semantic-sweep` command that asks an LLM
about every bounded file/chunk, validates structured relevance verdicts, and
reduces those verdicts without ever giving reducers or the parent source
bodies. It is a semantic-recall experiment, not a replacement for normal RLM
research or a guarantee that every relevant file was identified.

## Locked decisions

| # | Decision | Choice |
|---|---|---|
| D1 | Activation | Separate `semantic-sweep` command, never implicit in `ask`. |
| D2 | Limits | Explicit finite budget, timeout, files, chunks, and call caps are mandatory. |
| D3 | Unit | Each leaf receives one deterministic file-sized or line-aligned chunk. |
| D4 | Leaf output | Strict `related` / `not_related` / `uncertain` JSON with in-unit citations. |
| D5 | Failure | Invalid/missing/exhausted leaf output is `uncertain`, never silently negative. |
| D6 | Reduction | Reducers receive verdict metadata only and cannot delete related/uncertain evidence. |
| D7 | Coverage | Unstarted units remain explicitly unscanned. |
| D8 | Isolation | Source stays in leaves; reducers/parent receive no bodies. |
| D9 | Persistence | Resume requires matching repository/config/unit digests and valid artifacts. |
| D10 | Product boundary | Findings identify files to inspect; they do not authorize edits. |

## Execution shape

```text
eligible files → deterministic units/chunks → bounded leaf verdicts
                                                  │
                                   related / not-related / uncertain
                                                  │
                                                  ▼
                                  metadata-only hierarchical reducers
                                                  │
                                                  ▼
                               cited coverage + uncertainty report
```

## Example invocation

```bash
rlm semantic-sweep ./transformers \
  --max-budget 5.00 --timeout 1800 --max-files 500 \
  --max-file-chunks 900 --max-sweep-calls 1100 \
  --include-glob 'src/transformers/**/*.py' -- \
  "Which files implement or affect causal-LM loss shifting?"
```

Run `--dry-run` first. If the eligible set exceeds a cap, narrow it; do not
silently turn an incomplete sweep into a claimed complete result.

## Review questions

- What conservative default caps make experimentation safe without making the
  command impractical?
- Should model reducers be enabled initially, or should deterministic merging
  ship first?
- What exact leaf schema gives useful semantic reasons without encouraging
  unsupported confidence?
- Which evaluation fixtures expose false negatives that a per-file model pass
  still produces?
