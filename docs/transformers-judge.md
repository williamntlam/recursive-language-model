# Transformers causal-LM judge eval

## Purpose

This is the first runnable quality evaluation for RLM. It asks RLM to perform a
repository-wide census of Hugging Face Transformers causal-language-model and
conditional-generation `forward()` implementations. The task is deliberately
larger than a single-file question: it tests whether RLM can use local Python
inspection for broad coverage and reserve language-model calls for ambiguous
code.

The evaluation is opt-in and has two model calls:

1. RLM answers the census query against the local `codebases/transformers`
   checkout.
2. A separate judge model scores that answer.

It can also judge a saved answer, which makes prompt and runtime experiments
cheaper to compare.

## Run it

Clone the repository once if it is not already present:

```bash
git clone --depth 1 https://github.com/huggingface/transformers.git codebases/transformers
```

Then run a complete candidate-and-judge pass. This needs Docker and
`OPENAI_API_KEY`.

```bash
uv run python evals/transformers_causal_lm_judge.py --run-rlm
```

To regrade a previous candidate without another RLM run:

```bash
uv run python evals/transformers_causal_lm_judge.py --response-file answer.md
```

The JSON result is written to `evals/results/`, which is gitignored. A passing
result exits with status 0; a completed non-passing grade exits with status 1.

## What is measured

The versioned case is in
[`evals/cases/transformers_causal_lm.json`](../evals/cases/transformers_causal_lm.json)
and the scoring rubric is in
[`evals/criteria/transformers_causal_lm.md`](../evals/criteria/transformers_causal_lm.md).

| Criterion | Points | Goal |
| --- | ---: | --- |
| Scope and coverage | 0–3 | Cover both requested class families, inherited `forward()` methods, counts, and material exceptions. |
| Source-grounded evidence | 0–3 | Support claims with usable source citations. |
| Technical classification | 0–3 | Correctly distinguish direct loss, in-method shifting, and helper-based loss handling. |
| Useful synthesis | 0–1 | Provide concise, decision-useful GenerationMixin exceptions. |

The pass threshold is 7/10. Evidence and technical classification must each
score at least 1, and an answer without a usable citation always fails.

## Evidence flow

The judge does not receive the full Transformers checkout. The harness extracts
at most 20 cited `src/...py:start-end` or `tests/...py:start-end` locations from
the candidate answer, reads at most 80 lines from each valid in-repository
location, and supplies those snippets alongside the candidate response. Paths
that escape the selected checkout, do not exist, or use invalid line ranges are
discarded.

This design makes the grade more evidence-sensitive than a judge that sees only
an answer, while preserving the product's core property: source code is not
indiscriminately copied into a model prompt.

## Best practices followed

- **Representative, versioned task:** the query is stored as data rather than
  buried in the runner, so later evals can add cases without changing the
  harness.
- **Explicit rubric and gated pass rule:** criteria have bounded scores and
  source evidence is required for a pass, preventing a polished but uncited
  answer from succeeding.
- **Structured judge output:** the judge uses a strict JSON schema; the harness
  recomputes the total and pass/fail result instead of trusting model arithmetic.
  This follows OpenAI's guidance to use Structured Outputs when a machine needs
  to validate a response format. [OpenAI evals guide](https://platform.openai.com/docs/guides/evals)
- **Evidence-grounded judging:** accuracy is awarded only for claims supported
  by the supplied citation snippets. The judge is instructed to treat both the
  answer and snippets as untrusted data, not instructions.
- **Separation from unit tests:** evaluation calls are never collected by
  pytest, avoiding accidental API cost or Docker dependency in normal CI.
- **Reproducible artifacts:** result JSON records the case id, judge model,
  selected repository path, checked snippets, judgment, and candidate usage.

## Limitations and future improvements

This is intentionally a small starting point. It does not yet construct a
complete deterministic oracle for every class in Transformers, so a judge can
only validate claims that are cited and present in its bounded evidence.

Useful next steps are:

1. Add a deterministic AST census as a reference artifact and score count and
   coverage claims against it.
2. Pin the Transformers revision in the result and maintain a small set of
   known exception examples for calibration.
3. Run multiple independent judge samples and report agreement, rather than
   treating one judge call as definitive.
4. Add trajectory-level criteria: parent prompt tokens, number of child calls,
   leaf routing, latency, and cost.
5. Add more cases for repository navigation, inherited implementations,
   multi-file aggregation, corpora, and synthetic long-context retrieval.
6. Periodically calibrate rubric scores against human labels before using a
   threshold as a release gate.

The initial synthetic long-context retrieval ladder now lives in
[`context_needle_judge.py`](../evals/context_needle_judge.py); it scales from
8k to 500k tokens while keeping the generated context outside the judge prompt.
