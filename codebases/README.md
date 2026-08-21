# Local codebases (gitignored)

Clone repositories here to try `rlm ask` as a **read-only census** over a brownfield tree. Git ignores everything in this folder except this README.

Checked-in fixtures for unit tests stay in `tests/fixtures/`. This directory is for **your** trees.

```bash
git clone --depth 1 https://github.com/huggingface/transformers.git codebases/transformers

uv run rlm ask codebases/transformers --dry-run -- "preview"
uv run rlm ask codebases/transformers --verbose -- \
  "Census *ForCausalLM forward() with ast in this REPL. llm_query only unclear bodies. Do not spawn one child per file."
```

Expect parent tokens in the low thousands and few or zero `rlm_query` subcalls. Asking for one child per file is a recursion stress test, not a quality requirement.

Document dumps for `rlm research` go in [`corpora/`](../corpora/README.md).

`repo.tree` / `repo.files` already skip `.git`, `node_modules`, virtualenvs, and lockfile blobs, so a normal clone is fine.
