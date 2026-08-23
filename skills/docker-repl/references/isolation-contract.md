# Docker isolation contract

- The host owns OpenAI access and `OPENAI_API_KEY`. The container never gets
  that key or public network access.
- The workspace is mounted read-only at `/workspace`; the IPC directory is the
  only writable host mount and is used for the Unix-socket callback.
- The container uses a read-only filesystem with bounded tmpfs, drops
  capabilities, runs non-root, and has CPU, memory, PID, and cell-time limits.
- `llm_query` and `rlm_query` are injected into the persistent REPL namespace;
  they call the host over IPC rather than importing a host-side client.

Read `docs/architecture.md` for the end-to-end flow, or `docs/repl.md` only
when changing user-visible REPL APIs.
