# Local codebases (gitignored)

Clone repositories here to try `rlm ask`. Git ignores everything in this folder except this README.

Checked-in fixtures for unit tests stay in `tests/fixtures/`. This directory is for **your** trees.

```bash
git clone --depth 1 https://github.com/pytorch/pytorch.git codebases/pytorch

uv run rlm ask codebases/pytorch --dry-run -- "Where is autocast implemented?"
uv run rlm ask codebases/pytorch -- "Where is autocast implemented?"
```

Document dumps for `rlm research` go in [`corpora/`](../corpora/README.md).

`repo.tree` / `repo.files` already skip `.git`, `node_modules`, virtualenvs, and lockfile blobs, so a normal clone is fine.
