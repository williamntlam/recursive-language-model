from rlm.core.history import compact_repr
from rlm.repl_ns import SubcallHandler, create_namespace, run_cell, snapshot_reserved


class Quiet(SubcallHandler):
    def llm_query(self, prompt, model=None):
        return f"LEAF:{prompt[:60]}"

    def llm_query_batched(self, prompts, model=None):
        return ["LEAF"] * len(prompts)

    def rlm_query(self, prompt, model=None):
        return "CHILD"

    def rlm_query_batched(self, prompts, model=None):
        return ["CHILD"] * len(prompts)


def _ns(**bindings):
    ns = create_namespace(bindings, Quiet(), max_stdout_chars=200)
    return ns, snapshot_reserved(ns)


def test_trailing_tuple_expression_is_shown():
    ns, snap = _ns()
    obs = run_cell(ns, "hits = list(range(5))\nlen(hits), hits[:2]\n", snap)
    assert obs.error is None
    assert "(5, [0, 1])" in obs.stdout


def test_assignment_only_has_no_value_dump():
    ns, snap = _ns()
    obs = run_cell(ns, "x = list(range(100))\n", snap)
    assert obs.error is None
    assert "99" not in (obs.stdout or "")


def test_long_string_expr_is_metadata_not_body():
    ns, snap = _ns()
    obs = run_cell(ns, "blob = 'SECRET' + 'Z' * 3000\nblob\n", snap)
    assert obs.error is None
    assert "Z" * 800 not in obs.stdout
    assert "n_chars=" in obs.stdout


def test_print_is_truncated():
    ns, snap = _ns()
    obs = run_cell(ns, "print('Y' * 5000)\n", snap, max_send_chars=8000)
    assert obs.error is None
    assert len(obs.stdout) < 600
    assert "print truncated" in obs.stdout


def test_final_as_last_expr_does_not_dump_answer():
    ns, snap = _ns()
    answer = "A" * 2000
    obs = run_cell(ns, f"FINAL({'A' * 2000!r})\n", snap)
    assert obs.final == answer
    assert answer not in (obs.stdout or "")


def test_compact_repr_lists_preview_only():
    text = compact_repr(list(range(50)), max_chars=400)
    assert "0" in text
    assert "49" not in text
    assert "more" in text
