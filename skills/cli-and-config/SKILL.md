---
name: cli-and-config
description: Change CLI commands, flags, TOML/YAML configuration, precedence, or startup errors while keeping authentication out of config files.
---

# CLI and configuration

Use this skill for `rlm/cli.py`, `rlm/config.py`, config examples, or related
documentation.

## Why it matters

The CLI is the boundary where users choose a read-only research workflow and
its cost/safety limits. Clear, fail-closed configuration prevents accidental
credentials exposure and makes an RLM run reproducible.

Read [`references/config-contracts.md`](references/config-contracts.md) before
adding a configuration key or changing a command. Inspect `tests/test_cli.py`
or `tests/test_config.py` as applicable, then load `../testing/SKILL.md`.

Update the matching example and user documentation when the public interface
changes. Do not add API credentials as a flag or configuration value.
