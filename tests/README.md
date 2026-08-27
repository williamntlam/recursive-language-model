# Test conventions

Tests state one observable contract using Arrange → Act → Assert order. Keep
the sections visible through code and blank lines; comments are useful only
when a section would otherwise be unclear.

## Inputs and outputs

- Build inputs explicitly in the test: literals for unit tests, `tmp_path` for
  filesystem state, and checked-in fixtures for source data.
- Runtime tests use `make_rlm(tmp_path, script, **kwargs)`. Its `RLMHarness`
  exposes the runtime input as `.rlm` and captured model requests as `.client`;
  tuple unpacking remains supported for concise existing tests.
- Act through the public function, CLI, RLM API, or verifier entry point.
- Assert returned values, raised public errors, client requests, or durable
  artifacts. Do not assert private implementation details or model prose
  unless that text itself is a public contract.

## Scope

Use a behavior-oriented `test_<subject>_<outcome>` name and keep one primary
contract per test. Parameterize real input variations of that same contract;
use a separate test when the expected behavior changes.

Place tests by the boundary they exercise:

- `unit/`: focused deterministic behavior;
- `integration/`: workflows across RLM components, domains, CLI, logging, or
  Docker boundaries;
- `harbor/`: deterministic Harbor task and verifier checks; and
- `eval_support/`: deterministic support for opt-in evaluation tools.

The pytest markers select optional execution tiers; they do not replace this
placement convention.
