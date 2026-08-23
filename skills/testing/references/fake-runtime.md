# Fake runtime tests

`tests/util.py` contains the usual helpers:

- `make_rlm(tmp_path, script, **kwargs)` creates an RLM with `FakeClient` and
  `FakeEnv` and writes logs beneath the test temporary directory.
- `repl(code)` emits the expected REPL fence.
- `FIXTURE_REPO` and `FIXTURE_CORPUS` point to small checked-in fixtures.

`FakeClient` consumes scripted outputs, raises for a payload of at least
100,000 tokens, and can produce a deterministic failure for `FAIL_PLEASE`.
Assert contracts such as path safety, bounded history, batch alignment, and
prompt ceilings rather than volatile transcript text.
