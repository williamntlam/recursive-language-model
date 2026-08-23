# Runtime architecture

Read this only for cross-cutting runtime work.

- `rlm.cli` and `rlm.api` construct `RLM`; `rlm.core.runtime.Runtime` owns the
  iteration loop, prompt sends, subcalls, and trajectory events.
- `rlm/environments/` supplies `DockerEnv` in production and `FakeEnv` in
  tests. Both implement `execute(code) -> Observation`.
- `rlm/domains/` binds `repo` or `corpus` objects inside the REPL rather than
  serializing source data into a prompt.
- `llm_query` is a leaf call for a tight, unclear slice. `rlm_query` creates a
  child runtime only for material that cannot fit in a leaf.
- Child runtimes inherit the remaining budget and, for repo/corpus tasks, the
  same workspace. They do not receive a parent-side file dump.

Read `docs/architecture.md` or `docs/runtime.md` only if the task requires a
specific lifecycle, history, or budget rule not evident in the adjacent code.
