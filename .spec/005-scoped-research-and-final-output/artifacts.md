# 005 — Review artifacts

Companion to [`spec.md`](spec.md). Use this to review decisions. If something
here disagrees with the spec, the spec wins until you change it.

**Status:** Draft · **Date:** 2026-08-26 · **Owner:** William Lam

---

## 1. One paragraph

Make RLM research more reliable by separating deterministic inventory from
bounded semantic inspection, restricting child RLMs to explicit source spans,
and accepting only intentionally rendered text as an answer. This addresses
the observed failure pattern of giant generated REPL cells, repeated global
child scans, and raw Python data structures being presented to users as
reports. The source stays read-only in Docker and never enters parent history.

---

## 2. Locked decisions (review these first)

| # | Decision | Choice |
|---|---|---|
| D1 | Research flow | Inventory → deterministic classification → selected span inspection → rendered report. |
| D2 | First cell | Small census only; it does not also launch children or format the answer. |
| D3 | Semantic calls | Use a leaf on a fit selected span; use a child only for a selected span still too large after chunking. |
| D4 | Child inputs | `repo.explore` / `corpus.explore` gain optional explicit `targets`. |
| D5 | Enforcement | A targeted child gets a scoped domain view, not merely path names in its prompt. |
| D6 | Scoped search | Reads, greps, globs, trees, and searches cannot escape declared targets. |
| D7 | Compatibility | Untargeted children remain supported initially and are marked in trace metadata. |
| D8 | Final value | `FINAL`, `FINAL_VAR`, and legacy `answer` accept strings only. |
| D9 | Intermediate data | Dicts/lists are valid internal records; they must be rendered to text before finalization. |
| D10 | Quality mechanism | No per-run LLM judge; enforce scope/type contracts and measure behavior with opt-in evaluations. |
| D11 | Security | No new source exposure to parent history, no write access, no host credentials, no network. |
| D12 | Rollout | Final contract first, staged prompts second, scoped child boundary third. |

---

## 3. Intended execution shape

```
small inventory cell
        │  compact counts / metadata only
        ▼
deterministic classification + select evidence spans
        │
        ├── fit span ─────────────► leaf call / local read
        │
        └── oversized selected span ► scoped child RLM
                                      (only declared targets visible)
                                                   │
                                                   ▼
records + citations ──► render report_text: str ──► FINAL_VAR("report_text")
```

The parent may retain records and child answers in REPL variables, but it does
not print bodies or paste source into history.

---

## 4. Child target contract

Repository target:

```python
{"path": "src/model.py", "start": 120, "end": 190}
```

Corpus target:

```python
{"id": "paper-a", "start": 400, "end": 1800}
```

Targets are validated and normalized before the child starts. Empty, unknown,
outside-root, malformed, or inverted targets fail early. In a scoped child,
all domain operations return only permitted source; an attempted escape is an
explicit error rather than a silently broadened query.

---

## 5. Final-answer contract

Good:

```python
records = [{"claim": "…", "citations": ["src/a.py:10-20"]}]
report_text = "- … [src/a.py:10-20]"
FINAL_VAR("report_text")
```

Rejected, recoverably:

```python
FINAL_VAR("records")
FINAL({"claims": records})
answer["ready"] = True; answer["value"] = records
```

The recovery message tells the model to render the records into a string. This
prevents accidental Python `repr` output but does not impose one answer format:
Markdown, prose, a table, and serialized JSON are all valid when supplied as a
string.

---

## 6. Trace signals

Each exploration callback records compact scope metadata only:

| Field | Meaning |
|---|---|
| `scoped` | Whether the child received an enforced target view |
| `target_count` | Number of normalized targets |
| `target_manifest_digest` | Digest of the normalized target manifest |

Metadata capture does not record target paths or source content. Untargeted
child calls remain measurable so the migration can be evaluated from traces.

---

## 7. What does not change

- Every LM call remains below 100,000 tokens and within the instruction ceiling.
- Deterministic `ast`, regex, and counting work stays preferable to model calls.
- `repo.ask` / `corpus.ask` retain existing leaf-versus-child sizing behavior.
- Docker remains the only product REPL; source mounts remain read-only.
- This is research/Q&A infrastructure, not an editing agent or general shell.

---

## 8. Build order and verification

| Phase | Deliverable | Proof |
|---|---|---|
| 1 | String-only final contract | Namespace/runtime recovery tests; all existing string finals pass. |
| 2 | Staged strategy prompts + opt-in evaluation | Prompt ceiling tests plus before/after trace metrics on a multi-file case. |
| 3 | Scoped exploration boundary | Domain, IPC/Docker, trace, and broad-glob escape tests. |

For the Transformers regression, success means: no monolithic recovery churn,
no global child scan, no child cell timeout, a concise rendered answer, and
citations supporting its claims.

---

## 9. Review checklist

- [ ] Inventory and semantic interpretation are intentionally separate stages.
- [ ] A child with targets cannot read or search outside them.
- [ ] Untargeted child behavior remains observable during migration.
- [ ] A final answer is always deliberate text, never implicit object coercion.
- [ ] The change preserves source isolation and prompt/instruction ceilings.
- [ ] Evaluation measures the routing/cost trade-off without requiring a judge
  for every user run.
