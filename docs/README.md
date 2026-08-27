# Recursive Language Model documentation

This directory documents the **inference-time Recursive Language Model** in this repository: a runtime, CLI, and Python library that keep arbitrarily long prompts, repositories, and document corpora **out of the model window**. Context lives in a Docker Python REPL. The root model sees only short metadata and truncated stdout, then writes Python that peeks, slices, classifies with `ast`, and calls cheaper models only on snippets code cannot decide.

This is a **read-only census engine** for brownfield code and long documents. It is not a coding agent (no patch, test, or commit).

Paper: Zhang, Kraska, Khattab, [*Recursive Language Models*](https://arxiv.org/abs/2512.24601) (arXiv:2512.24601). Product rationale and diagrams: [root README](../README.md).

## Start here

| Document | What it covers |
|---|---|
| [Getting started](getting-started.md) | Install, Docker image, first `rlm ask` / `rlm research` / library call |
| [Concepts](concepts.md) | What an RLM is, why it is not ReAct/RAG/compaction/a coding agent, product invariants, routing |
| [Architecture](architecture.md) | Host vs container, data flow, security boundary |
| [CLI](cli.md) | `ask`, `research`, `complete`, `report`, flags, dry-run, exit codes, query shape |
| [Python API](python-api.md) | `RLM.completion`, `ask_repo`, `research`, return types |
| [Configuration](configuration.md) | TOML/YAML keys, discovery, precedence, auth |
| [REPL](repl.md) | Builtins (`measure`, `measure_ast`, `plan_reads`), `FINAL_VAR`, reserved names, Docker policy, IPC |
| [Domains](domains.md) | String context, `repo` (`measure` / `plan` / `ask` / `explore`), `corpus` |
| [Runtime](runtime.md) | Iteration loop, history policy, prompt guard, leaf vs child routing, budgets |
| [Logging and errors](logging-and-errors.md) | Trajectories, `error.txt`, parse errors, usage footer, exception map |
| [Execution tracing](tracing.md) | Causal JSONL traces, summaries, capture profiles, and local trace index |
| [Development](development.md) | Layout, tests, fixtures, evals |
| [Evaluations](evaluations.md) | Harbor agent tasks, repeated trials, suites, capability checks, and legacy judges |
| [Architecture benchmark playbook](tests.md) | Executable direct-vs-planned trials by source-evidence size, prompts, and trajectory checks |
| [Transformers judge eval](transformers-judge.md) | Source-grounded Transformers census, LLM judge, and long-context ladder |
| [Module reference](module-reference.md) | Package map and important types |

## One-paragraph thesis

Context stays in a REPL. The model recursively reads **slices that still need an LM**. The root context does not rot. Structural work (grep, `ast.parse`, counts) stays in Docker RAM. No language-model call — parent or child — may receive **100,000 or more input tokens** or **more than 150 instructions**. Recursion exists so those ceilings are always possible: classify locally, leaf a fit span, spawn a child only when a piece is still too large.

## When not to use this

Short prompts are often **worse** under an RLM scaffold than a single base-model call (the paper reports this). Spec implementation (patches, tests, PRs) belongs in a coding agent. Use this when the source would overflow or rot a normal window, or when the answer must be a **complete, cited** property of a brownfield tree or a multi-paper corpus.
