# 009 — Planned-wave architecture decisions

Companion to [`spec.md`](spec.md). If it conflicts with the specification, the
specification wins until changed.

**Status:** Draft · **Date:** 2026-08-27 · **Owner:** William Lam

## One paragraph

`planned_waves` makes complete metadata coverage of a large repository possible
without putting its entire inventory in one model prompt. A local census holds
all record metadata; token-aware shards drive multiple constrained planner
calls; validated selections execute in bounded waves; coverage records make
unselected, failed, and unstarted work explicit. Scope targets must survive the
host-to-Docker boundary, including planner fallback.

## Locked decisions

| # | Decision | Choice |
| --- | --- | --- |
| D1 | Activation | Explicit `architecture = "planned_waves"`; no implicit upgrade from `planner_enabled`. |
| D2 | Census | Complete streamed local metadata inventory; no source body. |
| D3 | Shard | Token-safe group of many records, not a single artifact or source target. |
| D4 | Planner | One constrained planner request per shard; IDs may only come from that shard. |
| D5 | Limits | Hard prompt/IPC/execution/reduction guards remain; coverage is unbounded only over time. |
| D6 | Coverage | Every record is represented with a terminal or pending status. |
| D7 | Fallback | Rejected planner shards never regain full-domain access. |
| D8 | Docker | Normalized targets travel in versioned `init` IPC and are revalidated in-container. |
| D9 | Reduction | Source-free, token-bounded batches before final rendering. |
| D10 | Baselines | Keep `direct` and `planned` intact for benchmark comparison. |

## Review questions

- What conservative shard and reduction token targets leave enough room for
  planner system instructions and future schema growth?
- Should `planned_waves` initially stop on an invalid shard plan, or use a
  deterministic restricted fallback for that shard?
- What coverage/artifact retention policy is appropriate when a census has
  millions of records?
- Which benchmark corpus best exposes the prior Docker fallback-scope gap?
