# Explain RLM's safety contracts

Read the source snapshot in `/workspace/source`. Do not modify it. Write your
answer to `/workspace/answer.md`.

The answer must be a concise explanation for a maintainer that covers all of
the following:

1. Why bound source context must not be appended to parent conversation
   history, and how older history is kept compact.
2. The maximum prompt-token and instruction limits, including whether exactly
   100,000 prompt tokens may be sent.
3. The source locations that establish each claim.

Use citations in the form `relative/path.py:line` or
`relative/path.py:start-end`. Do not use outside knowledge or make changes to
the source snapshot. `answer.md` is the only required output.
