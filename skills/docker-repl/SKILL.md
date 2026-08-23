---
name: docker-repl
description: Change the Docker REPL image, in-container namespace, RPC boundary, or isolation settings without exposing source writes, credentials, or network access.
---

# Docker REPL

Use this skill for `docker/`, `rlm/environments/docker.py`, `rlm/repl_ns.py`,
or host-container IPC behavior.

## Why it matters

Isolation lets users analyze private or large source material without giving
the execution environment credentials, network access, or write access to the
source. It is a product guarantee, not an implementation detail.

Read [`references/isolation-contract.md`](references/isolation-contract.md)
before changing mounts, environment variables, networking, user identity, or
callback behavior. Run Docker-marked tests only when Docker is available, and
also run focused fake-environment coverage through `../testing/SKILL.md`.

When copied runtime files change, update the image tag wherever the project
uses it so existing images cannot silently run stale code.
