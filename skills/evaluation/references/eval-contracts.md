# Evaluation contracts

## Harbor agent benchmark tasks

The supported agent-benchmark entry point is `evals/harbor/`. Harbor tasks are
versioned, self-contained directories with `task.toml`, `instruction.md`, an
`environment/Dockerfile`, and `tests/test.sh`. The verifier reports its
deterministic outcome through `/logs/verifier/reward.txt`.

For source-reading work, the agent must run as a non-root user and receive the
source tree read-only. The instruction names the permitted answer artifact;
the verifier owns its expected facts and checks. Do not put source writes, host
credentials, public-network access, test code, or answer keys in the agent
environment.

Keep `evals/harbor/suites/lite.txt` and `full.txt` frozen between benchmark
revisions. Run multiple attempts for reported agent scores. Pair each Harbor
integration task with fast deterministic tests that validate its layout and
verifier behavior.

## Current suites

- `transformers_causal_lm_judge.py` runs a source-grounded repository census.
  The judge sees the candidate answer plus bounded snippets at citations made
  by that answer, never the full Transformers checkout.
- `context_needle_judge.py` runs a synthetic extraction ladder at 8k, 64k,
  200k, and 500k `cl100k_base` tokens. Context is generated at run time and
  bound in the RLM REPL; it must not be inserted into the parent or judge
  prompt.

These two scripts are legacy, opt-in RLM development utilities. They are not
the Harbor agent-benchmark entry point and must not be presented as comparable
Harbor scores.

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
