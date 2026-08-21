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


def test_parser_falls_back_to_python_fence():
    text = """Looking around.

```python
hits = repo.grep("generate")
FINAL("ok")
```
"""
    code = extract_repl_code(text)
    assert code is not None
    assert "repo.grep" in code


def test_parser_accepts_unclosed_repl_fence():
    text = "```repl\npaths = repo.grep(r'def generate')\nprint(paths[:10])\n"
    code = extract_repl_code(text)
    assert code is not None
    assert "repo.grep" in code


def test_parser_accepts_bare_repl_after_prose():
    text = (
        "I'll fan out per file. I won't print file bodies.\n"
        "\n"
        "First, find candidate files.\n"
        "\n"
        "repl\n"
        "model_files = [f['path'] for f in repo.files()]\n"
        "print(len(model_files))\n"
    )
    code = extract_repl_code(text)
    assert code is not None
    assert "model_files" in code
    assert "I'll fan out" not in code


def test_parser_unglues_trailing_repl_and_keeps_both_cells():
    text = (
        "I'll start by listing files.\n"
        "\n"
        "repl\n"
        "model_files = repo.glob('**/*.py')\n"
        'print(len(model_files), "model .py files (total candidates)")repl\n'
        "hits = repo.grep(r'class', glob='**/*.py')\n"
        "print(len(hits))\n"
    )
    code = extract_repl_code(text)
    assert code is not None
    assert "model_files" in code
    assert "hits = repo.grep" in code
    assert not any(line.strip() == "repl" for line in code.splitlines())
    assert '")repl' not in code


def test_parser_accepts_bare_repl_header():
    text = (
        "repl\n"
        "# Explore the repository to locate generate() and logits warping usage\n"
        'paths = repo.grep(r"def generate\\(")\n'
        "len(paths), paths[:10]"
    )
    code = extract_repl_code(text)
    assert code is not None
    assert "repo.grep" in code
    assert not code.lstrip().startswith("repl")


def test_parser_strips_stray_repl_headings_inside_cell():
    text = """```repl
hits = repo.grep(r"def generate")
print(len(hits))
repl
lambda_hits = repo.grep(r"lambda")
print(len(lambda_hits))
```
"""
    code = extract_repl_code(text)
    assert code is not None
    assert "repo.grep" in code
    assert not any(line.strip() == "repl" for line in code.splitlines())
    assert "lambda_hits" in code


def test_parser_skips_json_fence():
    assert extract_repl_code('```json\n{"a": 1}\n```') is None


def test_repl_error_hint_for_str_format():
    from rlm.core.history import repl_error_hint

    hint = repl_error_hint(
        'q = ("{\\n  \\"classes\\": []}").format(path=p)\n',
        'KeyError: \'\\n  "classes"\'',
    )
    assert hint is not None
    assert "f-string" in hint
    assert repl_error_hint("x = 1", None) is None


def test_parser_returns_none_without_repl_fence():
    assert extract_repl_code("just prose and `code`") is None


def test_trailing_expression_is_displayed(tmp_path):
    rlm, client = make_rlm(
        tmp_path,
        [
            repl("hits = list(range(5))\nlen(hits), hits[:2]\n"),
            repl("FINAL('ok')\n"),
        ],
    )
    out = rlm.completion("go", "context-" + "n" * 300)
    assert out.response == "ok"
    second = "\n".join(m.content for m in client.calls[1])
    assert "(5, [0, 1])" in second or "5" in second and "[0, 1]" in second


def test_long_string_expr_is_not_dumped_into_hist(tmp_path):
    rlm, client = make_rlm(
        tmp_path,
        [
            repl("blob = 'NEEDLESECRET' + 'Z' * 5000\nblob\n"),
            repl("FINAL('ok')\n"),
        ],
    )
    out = rlm.completion("go", "context-" + "n" * 300)
    assert out.response == "ok"
    second = "\n".join(m.content for m in client.calls[1])
    assert "Z" * 800 not in second
    assert "n_chars=" in second or "not shown" in second


def test_parent_hist_keeps_code_not_prose(tmp_path):
    rlm, client = make_rlm(
        tmp_path,
        [
            "PROSE_SHOULD_NOT_STAY in the parent window.\n```repl\nprint(1)\n```\n",
            repl("FINAL('x')\n"),
        ],
    )
    out = rlm.completion("go", "context-" + "n" * 300)
    assert out.response == "x"
    second = "\n".join(m.content for m in client.calls[1])
    assert "PROSE_SHOULD_NOT_STAY" not in second
    assert "print(1)" in second


def test_old_observations_are_compacted(tmp_path):
    script = [repl(f"print('DUMP{i}-' + 'W' * 80)\n") for i in range(8)]
    script.append(repl("FINAL('done')\n"))
    rlm, client = make_rlm(tmp_path, script, max_observation_chars=400)
    out = rlm.completion("go", "context-" + "n" * 300)
    assert out.response == "done"
    last = "\n".join(m.content for m in client.calls[-1])
    assert "DUMP0-" not in last
    assert "compacted" in last
    assert "DUMP7-" in last
