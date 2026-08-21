from rlm.core.history import compact_repr
from rlm.repl_ns import (
    SubcallHandler,
    create_namespace,
    pause_alarm,
    run_cell,
    snapshot_reserved,
)


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


def test_pause_alarm_restores_remaining():
    import signal

    if not hasattr(signal, "setitimer"):
        return
    signal.setitimer(signal.ITIMER_REAL, 5)
    try:
        with pause_alarm():
            assert signal.getitimer(signal.ITIMER_REAL)[0] == 0
        left, _ = signal.getitimer(signal.ITIMER_REAL)
        assert 3.5 < left <= 5
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)


def test_ast_import_is_allowed():
    ns, snap = _ns()
    obs = run_cell(ns, "import ast\ntree = ast.parse('x = 1')\nlen(tree.body)\n", snap)
    assert obs.error is None
    assert "1" in (obs.stdout or "")


def test_rlm_query_rejects_lambda_instead_of_str():
    ns, snap = _ns()
    obs = run_cell(ns, "out = rlm_query(lambda p: p)\nprint(out)\n", snap)
    assert obs.error is None
    assert "Error:" in (obs.stdout or "")
    assert "str" in (obs.stdout or "")


def test_rlm_query_batched_rejects_lambdas():
    ns, snap = _ns()
    obs = run_cell(
        ns,
        "out = rlm_query_batched([lambda p: p, lambda p: p])\nprint(out)\n",
        snap,
    )
    assert obs.error is None
    assert "Error:" in (obs.stdout or "")


def test_final_var_accepts_bare_name_after_assign():
    ns, snap = _ns()
    obs = run_cell(ns, "result = 'ok'\nFINAL_VAR(result)\n", snap)
    assert obs.error is None
    assert obs.final == "ok"


def test_final_var_missing_name_lists_bindings():
    ns, snap = _ns()
    run_cell(ns, "paths = ['a.py']\n", snap)
    obs = run_cell(ns, "FINAL_VAR(COUNTS)\n", snap)
    assert obs.final is None
    assert obs.error
    err = (obs.stderr or "") + (obs.error or "")
    assert "COUNTS" in err
    assert "paths" in err
    assert "repl_ns.py" not in err
    assert "invent" in err.lower() or "SHOW_VARS" in err
