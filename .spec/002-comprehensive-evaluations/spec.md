# 002 — Comprehensive Evaluation Program

**Status:** Draft  
**Date:** 2026-08-22  
**Owner:** William Lam  
**Depends on:** 001 runtime, trajectory logging, and the existing opt-in `evals/` harnesses

---

## 1. Purpose

Define an incremental evaluation program for Recursive Language Model (RLM)
workflows. The program must make it possible to catch clear regressions,
compare runtime or prompt versions on the same work, and accumulate difficult
examples without requiring a complete benchmark suite before the product is
used.

This is a plan for evaluation assets and harnesses, not a request to turn RLM
into a general-purpose coding agent. Evaluations must preserve RLM's central
contract: source data is bound in the constrained REPL and is not copied into a
parent or judge-model prompt.

## 2. Starting point and scope

The repository already has two useful initial evaluations:

| Asset | What it establishes | What it does not establish |
| --- | --- | --- |
| `context_needle_judge.py` (8k–500k tokens) | A large generated string can be bound in the REPL and a unique literal can be extracted with evidence. | Dense reasoning, robust decomposition, or that the agent actually searched rather than returned a known fact. |
| `transformers_causal_lm_judge.py` | A source-grounded, multi-file repository question can be judged using bounded cited snippets. | Broad repository coverage, deterministic correctness, or stable quality across models and revisions. |

The needle ladder remains a fast long-context retrieval smoke test. It is not a
release claim that RLM solves real long-context work.

Out of scope for this specification:

- paid model calls in ordinary pytest or default CI;
- sending a full repository, corpus, or generated long context to a judge;
- treating a single judge score as definitive truth;
- a perfect benchmark suite before collecting developer and dogfooding traces.

## 3. Principles and non-negotiable invariants

1. **Start small, then preserve learning.** Add a representative seed set now;
   promote failures and difficult traces into versioned cases over time.
2. **Use deterministic checks when facts are deterministic.** Exact extraction,
   counts, labels, citations, prompt ceilings, and path validity must be checked
   in Python where possible. Use an LLM judge only for bounded qualitative
   criteria.
3. **Keep evaluation sources bounded.** The candidate RLM may inspect the full
   bound source. A judge receives only the answer, case facts, and a small,
   validated evidence bundle needed to assess cited claims.
4. **Test the product behavior, not a benchmark-specific recipe.** Default
   prompts must not be amended with instructions designed to solve a particular
   case.
5. **Make experiments comparable.** A result identifies case version, source
   revision or generator seed, runtime/config version, models, actual token
   counts, usage, latency, trajectory-derived metrics, and judgment.
6. **Keep live work opt-in.** Unit tests validate case construction and
   deterministic graders; candidate and judge calls remain explicit commands.
7. **Treat traces and candidate text as untrusted.** They are data for graders,
   never instructions for an evaluator model.
8. **Tag cases by behavior, not provenance.** An adapted external benchmark is
   useful only insofar as it measures a product behavior such as retrieval or
   multi-step tool use. Its source is metadata, not its category.
9. **Explain why each case exists.** Every case has a short capability
   description documenting the behavior it measures, its oracle/evidence
   strategy, and the regression or production-like failure that motivated it.

## 4. Evaluation data model

Each case is a versioned declarative file under `evals/cases/`. A case records:

- stable `id`, `version`, `family`, and difficulty;
- the query and required answer format;
- source fixture reference, source revision, or deterministic generator and
  seed;
- deterministic expected facts, where applicable;
- expected citation/evidence requirements;
- criteria reference and pass gates;
- optional budget expectations (maximum calls, tokens, cost, or wall time),
  initially reported before being enforced.

Case families should be organized by the product capability being tested:

| Family | Initial examples | Primary measurement |
| --- | --- | --- |
| Synthetic retrieval | unique marker, multiple markers, near-match distractors, position variation | exact answer and evidence |
| String aggregation | counts, grouped facts, comparisons across far-apart spans | deterministic result and evidence |
| Repository research | symbol census, call-path tracing, inherited implementation, cross-file exceptions | deterministic facts plus cited source evidence |
| Corpus research | compare claims across documents, identify disagreement, answer with document citations | citation validity and criteria-based grounding |
| Safety and boundary regression | history/source leakage, invalid citations, oversized child prompt attempts, path escape | deterministic invariant |
| Recovery / multi-turn simulation | ambiguous request, failed lookup, follow-up correction, budget pressure | state progression, final outcome, and policy criteria |

Initial behavior tags are `retrieval`, `aggregation`, `source_grounding`,
`tool_use`, `efficiency`, `conversation`, `recovery`, and `safety_boundary`.
A case may have more than one tag. Runs must be selectable by one or more tags
so experiments answer focused questions instead of reducing all behavior to one
aggregate score.

Runtime/unit/integration tests remain separate from capability evaluations.
Tests such as Docker setup, prompt passthrough, namespace binding, history
redaction, and IPC routing are essential release checks, but they measure
system plumbing rather than model quality and must not inflate a model's
capability score.

## 5. Metrics and grading

### 5.1 Deterministic outcome metrics

Use direct checks for tasks with a known answer:

- exact fields or values extracted;
- counts, classifications, and expected set membership;
- source citation path/span validity;
- generated context size, marker count, and marker placement;
- no full bound context in history, logs, parent prompts, or judge prompts;
- prompt-token and instruction ceilings for parent and child calls.

An answer that fails a mandatory deterministic fact fails the case even if a
judge finds its prose persuasive.

### 5.2 Criteria-based metrics

For tasks with multiple valid answers, use a versioned rubric with explicit
scores and gates. Typical criteria are:

- groundedness: material claims are supported by valid source evidence;
- coverage: required entities, alternatives, or exceptions are addressed;
- technical correctness: claims agree with supplied evidence/reference facts;
- instruction following: requested format, uncertainty, and scope are honored;
- usefulness: the answer is concise and decision-relevant;
- efficiency: the result remains within a reported or enforced budget.

The harness, not the judge, recomputes totals and applies gates. Calibrate
rubrics against a small set of human-reviewed answers before using them as a
release gate. Where cost permits, record agreement between independent judge
samples rather than relying on one sample.

### 5.3 Trajectory metrics

Record and initially report, rather than prematurely threshold:

- number of root turns, REPL cells, leaf calls, and recursive child calls;
- input/output tokens and cost by model and call type;
- wall time and failure/retry counts;
- maximum prompt tokens and instruction counts;
- sizes/routes of measured spans; and
- evidence of source inspection sufficient for the task (for example, a
  relevant REPL search followed by a bounded read).

Trajectory fields help distinguish a correct answer produced efficiently from
a lucky, costly, or policy-violating one. They must not require exposing source
contents in logs.

### 5.4 Ideal trajectories and normalized efficiency

For simple, well-scoped cases, define an `ideal_trajectory` in the case: the
smallest reasonable sequence of RLM/root turns, REPL cells, source operations,
and subcalls that reaches a correct result. It is a comparison baseline, not a
required literal sequence—RLM may use a different equally valid Python method.
For open-ended work, begin with the best reviewed successful trajectory and
revise it when better evidence appears.

Provided an ideal baseline exists, report:

| Metric | Calculation | Direction |
| --- | --- | --- |
| Correctness | deterministic pass and/or gated rubric pass | higher is better |
| Step ratio | observed root/agent steps ÷ ideal steps | lower is better |
| Tool/subcall ratio | observed subcalls and material REPL operations ÷ ideal operations | lower is better |
| Latency ratio | observed elapsed time ÷ ideal/reference elapsed time | lower is better |
| Solve rate | ideal steps ÷ observed elapsed time, or `0` when incorrect | higher is better |

Cost and token ratios may be added when the ideal trajectory contains a stable
model configuration. These ratios are diagnostic at first. Do not punish a
correct alternative merely because the ideal baseline was poorly specified.

## 6. Initial implementation sequence

### Phase A — Harden the existing baseline

1. Add deterministic pytest coverage for every synthetic generator: actual
   token count meets target, expected marker occurs exactly once, and marker
   placement is within a documented tolerance of `needle_position`.
2. Add cases with multiple required facts, near-match markers, and varied
   positions/seeds. Preserve the present single-needle cases as smoke tests.
3. Record the generator version/seed and source revision in every result.
4. Extend result JSON with a stable experiment/config identifier and available
   trajectory summary fields.
5. Add a capability description and behavior tags to each existing case;
   distinguish synthetic retrieval from aggregation or source-grounding work.

**Acceptance:** the 500k case remains generated locally, its full source is
never sent to parent/judge prompts, and deterministic construction failures are
caught without Docker or API calls.

### Phase B — Build a representative seed dataset

Add a small, hand-curated set of cases across all three domains: string,
repository, and research corpus. Prefer real developer questions and known
failures over broad but artificial coverage. Each case needs a source fixture
that is legal to distribute or a documented reproducible acquisition step.

Suggested first set:

- two string aggregation tasks requiring facts from distant spans;
- two repository cases involving cross-file aggregation and inheritance/call
  paths;
- two corpus cases requiring comparison and qualified disagreement;
- one boundary-regression case for each important safety invariant.

**Acceptance:** every case has a declared oracle or rubric, a bounded evidence
strategy, and deterministic local validation of the fixture/oracle.

### Phase C — Experiment harness and comparison report

Support running the same selected, pinned cases against named configurations:
root/leaf model, prompt version, runtime revision, and relevant routing or
budget settings. Store one append-only JSON result per run; create a summary
that compares pass rate, deterministic failure reasons, rubric scores,
cost/token usage, and latency by case family.

The harness must select cases by stable id and behavior tag. It should support
a narrow, targeted run (for example, `retrieval` plus `efficiency`) before a
full suite run. Each run should emit trace locations/identifiers so a reviewer
can inspect the actual source operations and failure mode rather than relying
only on summary scores.

Experiments must distinguish candidate generation from re-judging saved
answers so rubric changes can be tested without another RLM run.

**Acceptance:** a developer can compare two configurations on the same case
selection without overwriting prior results or confusing source revisions.

### Phase D — Multi-turn simulations

Introduce scripted scenario fixtures only for workflows that genuinely have
state across turns. A simulator supplies the next user/environment event from a
versioned script and checks required state transitions, tool outcomes, and the
final result. Initial scenarios should cover ambiguity that needs clarification,
an invalid or empty search result that requires recovery, and a follow-up that
changes the requested output.

Do not simulate autonomous code modification in this phase: this product's
scope remains read-only research and planning.

**Acceptance:** simulations are deterministic apart from explicitly isolated
model judgments; every scenario has a finite turn limit and a clear terminal
condition.

### Phase E — Continuous dataset improvement

Create a lightweight promotion process for developer, dogfooding, and later
production-like traces:

1. redact credentials and sensitive source content;
2. minimize the trace into a reproducible fixture or generator;
3. label the observed failure and desired behavior;
4. add an oracle/rubric and a regression case;
5. record the originating class of failure without storing private data.

Prioritize examples that reveal a regression, a misleading success, a costly
trajectory, or a missing clarification/recovery behavior. Periodically retire
redundant cases only when equivalent coverage is demonstrably retained.

## 7. Execution and release use

Evaluation commands remain opt-in. Normal PR validation runs deterministic
tests for case parsing, generators, graders, and safety invariants. A scheduled
or manually invoked live suite runs selected candidate configurations and
judges.

When a clean, reproducible environment and API budget are available, a small
tagged live smoke subset may run in scheduled CI. It must be isolated from the
ordinary unit/integration suite, record its model/configuration, and fail
clearly when Docker or credentials are absent rather than silently skipping a
claimed quality gate.

Initial release reporting should be informational: publish the selected case
set, pass/fail per case, failure category, cost, latency, and known coverage
gaps. Move a metric to a blocking gate only after its oracle/rubric is stable,
its variance is understood, and it has been calibrated against human review.

## 8. Known limitations

- Synthetic retrieval is necessary for exercising size and isolation but is not
  a proxy for dense reasoning.
- Bounded evidence judging can miss an uncited correct claim or an error beyond
  supplied snippets; deterministic reference artifacts reduce that risk.
- Results vary by model version and judge sampling, so comparisons require
  pinned configuration metadata and repeated runs where decisions are costly.
- A trajectory can show that source inspection occurred, but it cannot fully
  prove the model's internal reasoning.

## 9. Definition of done for this specification

This specification is complete when it serves as the accepted roadmap. The
implementation begins with Phase A only; later phases are deliberately gated by
evidence from the seed dataset and real failure traces rather than assumed
up-front requirements.
