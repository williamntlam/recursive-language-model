---
name: overengineering-check
description: Review an RLM specification, design, or change for complexity without a clear justification, including speculative abstraction and premature extensibility.
---

# Overengineering check

Use this skill when asked to review a proposed specification, design, diff, or
implementation for unnecessary complexity. It is a review aid: report
evidence-backed concerns and alternatives; do not block a change or simplify it
without authorization.

The test is justification, not size or sophistication: a mechanism is
overengineering when its added cost has no clear, current reason. Do not label
complexity as overengineering when a stated requirement, demonstrated risk, or
established boundary justifies it.

For a specification, first separate explicit requirements, constraints, and
success criteria from proposed solution details. Challenge only the latter when
they are not justified by the former. Ask what concrete present scenario,
failure mode, scale, integration, or project boundary requires each proposed
mechanism. A possible future need alone is not a justification.

For a design or implementation, read the stated requirements, the changed code,
and the focused tests or nearby call sites needed to understand the change. Do
not infer requirements from a preferred architecture.

For each meaningful added layer or mechanism—such as an interface, generic
framework, configuration surface, dependency, cache, queue, retry policy, or
asynchronous boundary—ask:

1. Which current requirement or established project boundary does it serve?
2. Would a simpler implementation meet the known requirements?
3. What maintenance, debugging, operational, or cognitive cost does it add?

Report only concerns for which the simpler alternative plausibly preserves the
known requirements. For each finding, cite the relevant file and line, identify
the missing or weak justification, describe the simpler alternative, explain
what would be lost by simplifying, and assign `high`, `medium`, or `low`
confidence. When reviewing a standalone specification without file locations,
quote or name the relevant requirement or section instead.

Pay particular attention in specifications to optional subsystems presented as
requirements: multiple interchangeable backends, plugin or extension systems,
generalized configuration, distributed or asynchronous processing, caching,
versioning or migration machinery, and broad compatibility guarantees. Keep
one if the specification supplies a concrete current need; otherwise recommend
deferring it while preserving a straightforward path to add it later.

Do not treat brevity as a goal. Complexity is normally justified when it protects
correctness, security, isolation, source-groundedness, bounded prompts,
diagnostics, or tests; when it implements a stated requirement; or when it
maintains an established boundary. In this project, preserve the read-only
runtime, host-container credential boundary, and prompt/history contracts.

If no concern meets that threshold, say so plainly and note any complexity that
appears justified. Separate speculative observations from actionable findings.
