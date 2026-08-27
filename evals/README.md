# Evals

The supported agent benchmark format is the local
[Harbor task dataset](harbor/README.md). Each task is self-contained and has an
agent environment, Markdown instruction, and `tests/test.sh` verifier. These
are source-reading tasks: source is root-owned and read-only, while the agent
writes only its requested answer artifact.

Run task-structure and deterministic capability checks during development:

```bash
uv run pytest -m harbor
```

Use the frozen `harbor/suites/lite.txt` list for fast iteration and
`harbor/suites/full.txt` for release-gate runs. Use multiple Harbor trials for
reported benchmark results, because agent execution is nondeterministic.

## Legacy LLM judge utilities

The scripts below remain opt-in development utilities. They do not define the
Harbor benchmark entry point and should not be used for reported agent scores.

- Synthetic needle-in-a-haystack over ~1M characters
- Dense aggregation (mini-OOLONG style)
- Fixture monorepo Q&A
- Multi-document synthesis with distractors
- History invariant: bound context never appears in parent `hist`
- Prompt-token ceiling: no send with `prompt_tokens >= 100000`
- Instruction ceiling: no send with `instruction_count > 150`
- Routing: parent `prompt_tokens` stay in the low thousands on a large-repo AST census; `rlm_query` is not the default per file

Optional later: LongBench-v2 CodeQA, BrowseComp-Plus style corpora, if licensing allows.

### Transformers LLM judge

`transformers_causal_lm_judge.py` evaluates the local,
gitignored `codebases/transformers` clone against the causal-LM `forward()`
census query. It is opt-in because it makes a candidate RLM call (with
`--run-rlm`) and a separate judge-model call.

The judge scores scope/coverage, source-grounded evidence, technical
classification, and useful synthesis. It receives the answer plus bounded
source snippets at locations cited in that answer; it does not receive the
whole repository. Passing requires at least 7/10, evidence and classification
scores of at least 1 each, and a usable source citation.

```bash
# Run RLM, then judge its response (requires Docker and OPENAI_API_KEY).
uv run python evals/transformers_causal_lm_judge.py --run-rlm

# Judge a response saved from a prior run.
uv run python evals/transformers_causal_lm_judge.py --response-file answer.md
```

Results are written to `evals/results/` by default, which is gitignored.
See [`transformers-judge.md`](../docs/transformers-judge.md) for the evidence flow,
best practices, limitations, and planned improvements.

### Increasing-context needle ladder

[`context_needle_judge.py`](context_needle_judge.py) is a synthetic,
increasing-context companion benchmark. The checked-in cases generate local
contexts of 8k, 64k, 200k, and 500k `cl100k_base` tokens. The largest case is
therefore a genuine half-million-token bound context, but it does not add a
multi-megabyte fixture to the repository.

```bash
# Run the full ladder in increasing order (each case runs RLM and a judge).
uv run python evals/context_needle_judge.py --all --run-rlm

# Start with only the 500k-token case.
uv run python evals/context_needle_judge.py \
  --case evals/cases/context-needle-500k.json --run-rlm
```

Each case asks RLM to find one unique audit marker. The judge receives the
candidate response and the known marker—not the generated context—and scores
exact extraction, marker evidence, and instruction-following. Passing requires
8/10, including strong correctness and evidence scores.

Optional later: LongBench-v2 CodeQA, BrowseComp-Plus style corpora, if licensing allows.
