# Recursive Language Model documentation

This directory documents the **inference-time Recursive Language Model** in this repository: a runtime, CLI, and Python library that keep arbitrarily long prompts, repositories, and document corpora **out of the model window**. Context lives in a Docker Python REPL. The root model sees only short metadata and truncated stdout, then writes Python that peeks, slices, and recursively calls cheaper models on snippets.

Paper: Zhang, Kraska, Khattab, [*Recursive Language Models*](https://arxiv.org/abs/2512.24601) (arXiv:2512.24601).

## Start here

| Document | What it covers |
|---|---|
| [Getting started](getting-started.md) | Install, Docker image, first `rlm ask` / `rlm research` / library call |
| [Concepts](concepts.md) | What an RLM is, why it is not ReAct/RAG/compaction, product invariants |
| [Architecture](architecture.md) | Host vs container, data flow, security boundary |
| [CLI](cli.md) | `ask`, `research`, `complete`, flags, dry-run, exit codes |
| [Python API](python-api.md) | `RLM.completion`, `ask_repo`, `research`, return types |
| [Configuration](configuration.md) | TOML/YAML keys, discovery, precedence, auth |
| [REPL](repl.md) | Builtins, `FINAL_VAR`, reserved names, Docker policy, IPC |
| [Domains](domains.md) | String context, `repo`, `corpus` |
| [Runtime](runtime.md) | Iteration loop, history policy, prompt guard, recursion, budgets |
| [Logging and errors](logging-and-errors.md) | Trajectories, usage footer, exception map |
| [Development](development.md) | Layout, tests, fixtures, evals |
| [Module reference](module-reference.md) | Package map and important types |

## One-paragraph thesis

Context stays in a REPL. The model recursively reads slices. The root context does not rot. No language-model call — parent or child — may receive **100,000 or more input tokens** or **more than 150 instructions**. Recursion exists so those ceilings are always possible: slice until the piece fits.

## When not to use this

Short prompts are often **worse** under an RLM scaffold than a single base-model call (the paper reports this). Use this when the source would overflow or rot a normal window: a mid-size monorepo, a multi-paper corpus, a haystack that must be aggregated rather than retrieved.
