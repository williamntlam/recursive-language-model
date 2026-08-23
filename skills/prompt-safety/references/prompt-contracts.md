# Prompt and history contracts

- Every parent or subcall send is guarded. A send at 100,000 tokens or more is
  illegal; configured `max_prompt_tokens` cannot exceed 99,999.
- The composed instruction count cannot exceed 150. Do not increase either
  hard ceiling to accommodate a new prompt.
- Parent history retains executed REPL cells and truncated observations, then
  compacts older pairs. File bodies, corpus data, and full child transcripts do
  not belong in parent history.
- Route a fit, unclear slice to a leaf; use a child only for an oversized span
  that cannot be handled as chunks. The usual leaf threshold is 24,000 chars.
- `FakeClient` rejects an oversized payload, making guard regressions visible
  in tests.

For precise mechanics, read `docs/runtime.md` only when changing that behavior.
