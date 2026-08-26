import json

import pytest

from rlm.core.budgets import Budget
from rlm.errors import ReplErrorsExhausted
from tests.util import FIXTURE_REPO, make_rlm, repl


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


def test_rlm_query_in_repo_mode_child_sees_repo(tmp_path):
    rlm, _ = make_rlm(
        tmp_path,
        [
            repl(
                "ans = rlm_query('Grep AUTOCAST_CPU_BF16_IMPL_MARKER; FINAL the path')\n"
                "FINAL(ans)\n"
            ),
            repl("hits = repo.grep('AUTOCAST_CPU_BF16_IMPL_MARKER')\nFINAL(hits[0].path)\n"),
        ],
    )
    out = rlm.ask_repo(FIXTURE_REPO, "where?")
    assert "secret.py" in out.response
    assert out.usage.subcalls >= 1


def test_path_dict_rlm_query_automatically_scopes_repo_child(tmp_path):
    rlm, _ = make_rlm(
        tmp_path,
        [
            repl(
                "ans = rlm_query({'question': 'inspect the marker', "
                "'path': 'src/deep/secret.py', 'start': 1, 'end': 20})\n"
                "FINAL(ans)\n"
            ),
            repl(
                "try:\n"
                "    repo.read('src/utils.py')\n"
                "except ValueError:\n"
                "    pass\n"
                "FINAL(repo.grep('AUTOCAST_CPU_BF16_IMPL_MARKER')[0].path)\n"
            ),
        ],
    )
    out = rlm.ask_repo(FIXTURE_REPO, "where?")
    assert out.response == "src/deep/secret.py"
    trace = (out.trajectory / "trace.jsonl").read_text(encoding="utf-8")
    assert '"scoped": true' in trace or '"scoped":true' in trace


def test_python_fence_is_executed(tmp_path):
    rlm, _ = make_rlm(
        tmp_path,
        ["Here is code:\n```python\nFINAL('from-python-fence')\n```\n"],
    )
    out = rlm.completion("go", "context-" + "n" * 300)
    assert out.response == "from-python-fence"


def test_bare_repl_header_is_executed(tmp_path):
    rlm, _ = make_rlm(
        tmp_path,
        ["repl\n# Explore the repository\nFINAL('from-bare-repl')\n"],
    )
    out = rlm.completion("go", "context-" + "n" * 300)
    assert out.response == "from-bare-repl"


def test_parse_error_logs_model_preview(tmp_path):
    rlm, _ = make_rlm(
        tmp_path,
        [
            "I refuse to use a fence.",
            "```python\nFINAL('recovered')\n```",
        ],
        max_consecutive_errors=5,
    )
    out = rlm.completion("go", "context-" + "n" * 300)
    assert out.response == "recovered"
    events = (out.trajectory / "events.jsonl").read_text(encoding="utf-8")
    assert "parse_error" in events
    assert "I refuse to use a fence." in events
    err = (out.trajectory / "error.txt").read_text(encoding="utf-8")
    assert "parse_error" in err
    assert "I refuse to use a fence." in err


def test_non_string_final_is_a_repl_error_then_can_be_rendered(tmp_path):
    rlm, _ = make_rlm(
        tmp_path,
        [
            repl("records = [{'claim': 'grounded'}]\nFINAL_VAR(records)\n"),
            repl("report_text = '- grounded'\nFINAL_VAR(report_text)\n"),
        ],
        max_consecutive_errors=2,
    )
    out = rlm.completion("go", "context-" + "n" * 300)
    assert out.response == "- grounded"
    events = (out.trajectory / "events.jsonl").read_text(encoding="utf-8")
    assert "TypeError" in events


def test_repl_errors_exhausted_writes_error_txt(tmp_path):
    rlm, _ = make_rlm(
        tmp_path,
        [repl("1/0\n"), repl("1/0\n"), repl("1/0\n")],
        max_consecutive_errors=2,
    )
    with pytest.raises(ReplErrorsExhausted):
        rlm.completion("go", "context-" + "n" * 300)
    runs = list((tmp_path / "logs").iterdir())
    assert len(runs) == 1
    text = (runs[0] / "error.txt").read_text(encoding="utf-8")
    assert "ZeroDivisionError" in text
    assert "ReplErrorsExhausted" in text


def test_instruction_count_does_not_grow_with_observations(tmp_path):
    script = [repl(f"print({i})\n") for i in range(4)]
    script.append(repl("FINAL('ok')\n"))
    rlm, _ = make_rlm(tmp_path, script)
    out = rlm.completion("go", "context-" + "n" * 300)
    assert out.response == "ok"
    counts = []
    for line in (out.trajectory / "events.jsonl").read_text(encoding="utf-8").splitlines():
        ev = json.loads(line)
        if ev.get("kind") == "root_lm" and "instruction_count" in ev:
            counts.append(ev["instruction_count"])
    assert counts
    assert len(set(counts)) == 1
