from rlm.core.parse import extract_repl_code
from tests.util import hist_text, make_rlm, repl


def test_history_never_contains_bound_context(tmp_path):
    needle = "NEEDLE_TOKEN_XYZ_42"
    context = ("lorem ipsum " * 4000) + needle + (" dolor sit " * 4000)
    assert len(context) > 4000
    rlm, client = make_rlm(
        tmp_path,
        [
            repl(
                "idx = context.find('NEEDLE_TOKEN_XYZ_42')\n"
                "found = context[idx:idx+len('NEEDLE_TOKEN_XYZ_42')]\n"
                "FINAL_VAR('found')\n"
            )
        ],
    )
    out = rlm.completion("Find the needle.", context)
    assert out.response == needle
    joined = hist_text(client)
    assert context not in joined


def test_final_var_returns_full_variable_not_truncated_print(tmp_path):
    big = "Q" * 10_000
    rlm, _ = make_rlm(
        tmp_path,
        [repl('big = "Q" * 10000\nFINAL_VAR("big")\n')],
        max_observation_chars=200,
    )
    out = rlm.completion("return the big var", "context-payload-" + "z" * 500)
    assert out.response == big
    assert len(out.response) == 10_000


def test_parser_extracts_repl_and_ignores_prose():
    text = """
I will look at a slice first.

```python
print("not this")
```

```repl
idx = context.find("needle")
print(idx)
```

Done.
"""
    code = extract_repl_code(text)
    assert code is not None
    assert "needle" in code
    assert "not this" not in code


def test_parser_returns_none_without_repl_fence():
    assert extract_repl_code("just prose and `code`") is None
