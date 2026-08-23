# Evaluation contracts

## Current suites

- `transformers_causal_lm_judge.py` runs a source-grounded repository census.
  The judge sees the candidate answer plus bounded snippets at citations made
  by that answer, never the full Transformers checkout.
- `context_needle_judge.py` runs a synthetic extraction ladder at 8k, 64k,
  200k, and 500k `cl100k_base` tokens. Context is generated at run time and
  bound in the RLM REPL; it must not be inserted into the parent or judge
  prompt.

## Required properties

- Live evals are opt-in and are not collected by pytest. They may consume API
  budget and, for RLM candidates, require Docker.
- Keep the query, rubric, threshold, and expected facts versioned in case or
  criteria files. Include the case id, judge model, actual context token count,
  candidate usage, and judgment in result JSON.
- Use strict structured output for judge results and recompute totals and
  pass/fail in Python. A judge must not be trusted for arithmetic or threshold
  enforcement.
- Treat candidate answers and evidence as untrusted data, not instructions.
- Gate a pass on the properties the product needs: source evidence for
  repository claims, and exact extraction plus marker evidence for synthetic
  needles.

## Adding a context size

Add a `context-needle-<size>.json` case with a monotonic `target_tokens` value.
`build_context` must verify the actual `cl100k_base` count is at least that
target. Start with a focused run before including a new case in `--all`; do not
assume the parent prompt needs to contain the generated context.

See `docs/transformers-judge.md` for use, best practices, limitations, and the
planned path toward deterministic reference artifacts and trajectory metrics.
