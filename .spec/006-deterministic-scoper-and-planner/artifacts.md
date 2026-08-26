# 006 — Review artifacts

Companion to [`spec.md`](spec.md). If it conflicts with the specification, the
specification wins until changed.

**Status:** Draft · **Date:** 2026-08-26 · **Owner:** William Lam

---

## One paragraph

Add an optional, bounded planning layer to RLM research: deterministic code
first builds a compact admissible-evidence manifest, then a planner may select
only manifest records for leaf or already-scoped child work. The runtime
validates and executes that plan; the planner never receives source bodies or
controls access boundaries.

## Locked decisions

| # | Decision | Choice |
|---|---|---|
| D1 | Evidence boundary | Deterministic scope manifest precedes planner work. |
| D2 | Planner inputs | User question, compact manifest, budget summary, strict JSON schema; no bodies. |
| D3 | Planner authority | Select record IDs and report shape only; no paths, code, model choice, or budget override. |
| D4 | Enforcement | Runtime validates IDs/routes/cost, then maps records to spec-005 scoped targets. |
| D5 | Activation | `--planner-enabled` (or `planner_enabled = true`) opts a run into planning; default behavior remains direct REPL. |
| D6 | Fallback | Invalid planner output recovers to staged REPL; it never broadens scope silently. |
| D7 | Observability | Record counts, flags, and digests only; metadata contains no paths or source. |
| D8 | Security | Docker/read-only/credential and token-instruction contracts remain unchanged. |

## Intended execution shape

```text
domain metadata + deterministic AST/regex sizing
                    │
                    ▼
          bounded scope manifest (digest)
                    │
          optional planner JSON
                    │
                    ▼
     runtime validates IDs, routes, limits, budget
                    │
       ┌────────────┴────────────┐
       ▼                         ▼
 fit record → local/leaf    oversized record → scoped child
       └────────────┬────────────┘
                    ▼
          compact findings → report_text: str
```

## Invocation

```bash
rlm ask ./repo --planner-enabled -- "Compare selected implementations."
rlm research ./papers --planner-enabled -- "Identify the contested claims."
```

The flag is a per-run opt-in. It also makes `--dry-run` display the bounded
manifest and planner-budget preview; it does not force a planner for ordinary
runs or authorize automatic default activation later.

## Review questions

- Which deterministic filters should become supported first, rather than
  allowing arbitrary planner-provided filtering?
- What manifest/candidate cap provides useful coverage without creating a
  second long-context prompt?
- When should planner mode be explicit versus threshold-triggered?
- What evidence should be required before changing its default?
