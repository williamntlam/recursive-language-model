# Evals

Not a v0 blocker. After the product works (history policy, prompt ceilings, repo and research domains), add:

- Synthetic needle-in-a-haystack over ~1M characters
- Dense aggregation (mini-OOLONG style)
- Fixture monorepo Q&A
- Multi-document synthesis with distractors
- History invariant: bound context never appears in parent `hist`
- Prompt-token ceiling: no send with `prompt_tokens >= 100000`
# Evals

Not a v0 blocker. After the product works (history policy, prompt ceilings, repo and research domains), add:

- Synthetic needle-in-a-haystack over ~1M characters
- Dense aggregation (mini-OOLONG style)
- Fixture monorepo Q&A
- Multi-document synthesis with distractors
- History invariant: bound context never appears in parent `hist`
- Prompt-token ceiling: no send with `prompt_tokens >= 100000`
- Instruction ceiling: no send with `instruction_count > 150`
- Routing: parent `prompt_tokens` stay in the low thousands on a large-repo AST census; `rlm_query` is not the default per file

Optional later: LongBench-v2 CodeQA, BrowseComp-Plus style corpora, if licensing allows.

Optional later: LongBench-v2 CodeQA, BrowseComp-Plus style corpora, if licensing allows.
