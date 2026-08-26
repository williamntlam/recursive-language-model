# Global metadata candidate search

## Status

Proposed implementation specification. This can supply candidate manifests to
specification 006, but is useful independently and does not require a planner
agent.

## Problem

Narrow AST/name filters can miss relevant files before the system has a chance
to inspect them. Conversely, reading every source body merely to discover
candidates is expensive and undermines staged research. RLM needs a global
first-pass search that maximizes recall using only content-free filesystem and
repository metadata, then exposes its uncertainty and candidate rationale for
later bounded inspection.

## Goals

- Scan the whole bound repository deterministically without reading source-file
  contents.
- Produce compact candidate records ranked by transparent filename, path,
  metadata, and topology signals.
- Identify related files through content-free structural relationships such as
  directory/package membership and conventional filename families.
- Feed a bounded, auditable candidate set into direct REPL research or the
  optional spec-006 planner.
- Preserve read-only isolation, source locality, prompt limits, and a clear
  distinction between candidate discovery and evidence.

## Non-goals

- Do not call `repo.read`, `repo.file_text`, `repo.grep`, AST parsing, regex
  over source files, or an LLM during candidate discovery.
- Do not claim a candidate is semantically relevant based on metadata alone.
- Do not build an import/call graph by reading source files in this work.
- Do not hide a broad source scan behind an index-building implementation.
- Do not automatically launch leaves or children from candidate results.

## Content-free boundary

The metadata pass may read directory entries and file-system metadata only:

- repository-relative path, basename, suffix, directory/package segments;
- file size, modification time where available, and binary/text classification;
- ignored/generated/vendor status inferred from path rules;
- conventional sibling relationships: same stem, `modeling_*` / `configuration_*`
  / `tokenization_*` families, `__init__.py` package membership, test/source
  directory correspondence, and parent/child directory proximity;
- repository-level metadata already available without opening files (for
  example, workspace root and Git HEAD).

It must not open candidate source files. Consequently, terms that occur only
inside source code and true import/inheritance/call relationships are unknown
at this stage. An implementation that needs those signals belongs in a later,
explicit source-inspection phase after candidate selection.

## Public API

Add a repository-bound metadata search API available in the REPL:

```python
repo.discover_candidates(query: str, *, limit: int = 200) -> dict
```

The return value contains compact records and summary counts, never source
bodies:

```python
{
  "version": 1,
  "query_digest": "…",
  "scanned_files": 1240,
  "candidate_count": 37,
  "truncated": false,
  "candidates": [
    {
      "id": "c-0042",
      "path": "src/transformers/models/llama/modeling_llama.py",
      "n_bytes": 128432,
      "suffix": ".py",
      "score": 18,
      "signals": [
        "query-token:causal:basename",
        "query-token:model:directory",
        "family:modeling",
        "package:src.transformers.models.llama"
      ],
      "related_ids": ["c-0043", "c-0044"]
    }
  ]
}
```

`score` is deterministic and explainable, not a probability. `related_ids`
reference records returned in the same manifest. Record ordering is stable:
descending score, then path.

`query` is tokenized locally into conservative lexical terms. Matching applies
only to normalized path segments and filenames; it never triggers a content
search. Empty/no-useful-token queries return a summary with no ranked semantic
candidates and a clear recommendation to refine the query or browse compact
directory metadata.

## Workstream A — deterministic candidate discovery

### Required behavior

Implement a content-free repository walker that honors the existing ignored
directory/file policy. For each eligible file, construct metadata records and
derive signals from:

1. Exact/partial lexical matches between query tokens and path/basename tokens.
2. File role conventions (`modeling_`, `configuration_`, `tokenization_`,
   `processing_`, `convert_`, test prefixes, and configurable project rules).
3. Package/directory proximity to a lexical match.
4. Same-stem and conventional-family sibling relationships.
5. Test/source correspondence inferred only from path transformations.

Score weights are versioned configuration, applied deterministically, and
included as a digest in the result. The API must expose all contributing
signals so users and planners can see why a file appeared.

Candidate expansion is metadata-only: selecting a candidate may add a bounded
number of sibling/family/package-neighbor records with an `expanded-from`
signal. It must not recursively include an entire large package without an
explicit cap and truncation flag.

### Acceptance criteria

- A test guard proves discovery never invokes source-reading APIs and does not
  open regular source files.
- Same repository/query/configuration produces identical result records and
  digest order.
- Queries matching `causal`, `llama`, or `modeling` identify expected
  Transformers path families by name while retaining nearby conventional
  siblings as clearly marked expansions.
- A query with no filename/path match reports zero semantic candidates rather
  than pretending the repository was searched semantically.
- Ignored/vendor/generated paths remain excluded under existing policy.

## Workstream B — relationship and uncertainty model

### Required behavior

Candidate relationships are directional, typed metadata edges:

| Edge | Meaning | Source-content required? |
| --- | --- | --- |
| `same_stem` | Same basename after a known role prefix/suffix is removed | No |
| `family_sibling` | Same package and conventional role family | No |
| `package_neighbor` | Same or parent package within a configured radius | No |
| `test_counterpart` | Deterministic `src` ↔ `tests` path convention | No |
| `name_match_anchor` | Both records share a normalized query/path token | No |

Do not call these import, dependency, inheritance, or call edges. The result
must prominently label them as *metadata relationships*, and report why a
semantic relationship cannot yet be known.

Every result includes discovery limitations: whether candidate limit was hit,
how many files had no lexical match, ignored-path counts, enabled rule-set
version, and a statement that source bodies were not searched. This lets a
later planner request bounded source inspection or an explicit deterministic
scope expansion rather than assuming completeness.

### Acceptance criteria

- Relationship edges are stable, bounded, deduplicated, and only reference
  returned candidate IDs.
- Tests distinguish metadata siblings from actual imports: no result field or
  prompt may call an edge an import/dependency without a later evidence pass.
- Candidate limits/expansions always expose truncation and originating IDs.

## Workstream C — routing, planner integration, and observability

### Required behavior

The first release does not automatically inspect candidates. It provides two
explicit consumers:

1. The root REPL can use candidate IDs/paths as compact inventory and decide
   which spans to inspect with existing `repo.measure`, AST, leaf, and scoped
   child mechanisms.
2. When spec-006 planner mode is enabled, its deterministic scope builder may
   consume this result as a high-recall prefilter. The planner receives only
   compact candidate metadata and can select candidate IDs, never bypass the
   subsequent measured-span validation.

Trace one `repo.discover_candidates` tool span plus optional summary events:
scanned file count, candidate count, edge count, truncation flags, rule-set
digest, result digest, and duration. Metadata capture must not include paths,
query text, source text, or raw signal strings that expose paths; content
capture follows existing capping/redaction rules.

Update REPL/domain/tracing documentation to state that discovery is a recall-
oriented metadata inventory, not evidence or a semantic code search.

### Acceptance criteria

- A planner-enabled run cannot turn an unmeasured candidate into a child target
  without the existing scope/size validation.
- Trace summaries contain counts/digests but no candidate path or source body.
- The direct REPL workflow remains unchanged unless it explicitly calls
  `repo.discover_candidates`.

## Evaluation

Create an opt-in repository evaluation with known relevant files whose names
are both obvious and non-obvious. Measure candidate recall at fixed limits,
candidate count, false-positive burden, metadata-pass elapsed time, and number
of later source reads. Report the metadata discovery result separately from
semantic answer quality. Do not score metadata candidates as factual evidence.

For Transformers, compare:

- a direct AST/body census;
- metadata candidate discovery followed by selected measured spans; and
- metadata discovery used as a spec-006 planner prefilter.

Record missed known-relevant paths and explain whether they were absent due to
the content-free constraint, tokenization, weighting, expansion caps, or
ignored-path policy.

## Rollout and validation

1. Implement the walker, record schema, lexical scorer, and source-read guard
   with small deterministic fixtures.
2. Add relationship/uncertainty fields and property tests for stable ordering,
   cap behavior, and no content reads.
3. Bind the REPL API and metadata trace event; document its limitations.
4. Integrate as an optional spec-006 prefilter only after standalone recall and
   cost measurements are available.

## Likely implementation areas

- Candidate builder and domain API: `rlm/domains/repo.py` and focused helper
  modules under `rlm/domains/`.
- REPL catalog/prompt representation: `rlm/repl_ns.py`, `rlm/prompts/`, and
  prompt-budget tests.
- Tracing and reports: `rlm/core/runtime.py`, `rlm/logging/`, and trace tests.
- Evaluation fixtures and opt-in comparison: `evals/`, domain tests, and
  documentation.
