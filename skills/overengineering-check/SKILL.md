---
name: overengineering-check
description: Review an RLM change or design for unjustified complexity, speculative abstraction, and premature extensibility without penalizing necessary safeguards.
---

# Overengineering check

Use this skill when asked to review a proposed design, diff, or implementation
for unnecessary complexity. It is a review aid: report evidence-backed concerns
and alternatives; do not block a change or simplify it without authorization.

Read the stated requirements, the changed code, and the focused tests or nearby
call sites needed to understand the change. Do not infer requirements from a
preferred architecture.

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
confidence.

Do not treat brevity as a goal. Complexity is normally justified when it protects
correctness, security, isolation, source-groundedness, bounded prompts,
diagnostics, or tests; when it implements a stated requirement; or when it
maintains an established boundary. In this project, preserve the read-only
runtime, host-container credential boundary, and prompt/history contracts.

If no concern meets that threshold, say so plainly and note any complexity that
appears justified. Separate speculative observations from actionable findings.
