import pytest

from rlm.core.budgets import Budget
from tests.util import make_rlm, repl


def test_reserved_names_restored_after_clobber(tmp_path):
    rlm, _ = make_rlm(
        tmp_path,
        [
            repl("llm_query = 1\nprint(type(llm_query))\n"),
            repl("out = llm_query('hello')\nFINAL(out)\n"),
            "leaf-says-hi",
        ],
    )
    out = rlm.completion("use llm_query", "context-" + "n" * 300)
    assert out.response == "leaf-says-hi"


def test_batch_alignment_middle_failure(tmp_path):
    rlm, _ = make_rlm(
        tmp_path,
        [
            repl(
                "out = llm_query_batched(['p0', 'p1', 'FAIL_PLEASE', 'p3', 'p4'])\n"
                "FINAL(repr(out))\n"
            ),
            "x",
            "x",
            "x",
            "x",
        ],
    )
    out = rlm.completion("batch", "context-" + "n" * 300)
    # FINAL stored repr of a 5-element list
    assert out.response.startswith("[")
    assert out.response.endswith("]")
    # 5 slots: four successes and one Error
    assert out.response.count("Error:") == 1
    assert out.response.count("'x'") == 4


def test_budget_inheritance_remaining_not_original():
    b = Budget.from_config(max_usd=2.0, max_timeout_s=100)
    b.spent_usd = 0.5
    child = b.inherit()
    assert child.max_usd == pytest.approx(1.5)
    assert child.max_timeout_s is not None
    assert child.max_timeout_s < 100
    assert child.max_timeout_s > 90
    assert child.spent_usd == 0.0


def test_rlm_query_spawns_child_with_own_env(tmp_path):
    rlm, client = make_rlm(
        tmp_path,
        [
            repl("ans = rlm_query('Say hello via FINAL')\nFINAL(ans)\n"),
            repl("FINAL('from-child')\n"),
        ],
        max_depth=16,
    )
    out = rlm.completion("recurse", "parent-context-" + "n" * 300)
    assert out.response == "from-child"
    # parent root + child root
    assert len(client.calls) >= 2
    assert out.usage.subcalls >= 1
