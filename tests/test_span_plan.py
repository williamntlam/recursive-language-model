from rlm.core.history import (
    ASK_LEAF_CHARS,
    estimate_tokens,
    measure_ast,
    measure_text,
    plan_reads,
)
from rlm.domains.repo import load_repo
from tests.util import FIXTURE_REPO


def test_small_span_fits_and_needs_zero_children():
    row = measure_text("def forward(self, x):\n    return x\n")
    assert row["route"] == "fit"
    assert row["n_tokens"] == estimate_tokens(row["n_chars"])
    plan = plan_reads([row, row, row])
    assert plan["n_fit"] == 3
    assert plan["n_child"] == 0


def test_oversized_span_is_one_child_with_line_chunks():
    text = ("x" * 80 + "\n") * 400  # ~32k chars
    assert len(text) > ASK_LEAF_CHARS
    row = measure_text(text)
    assert row["route"] == "child"
    assert row["n_chunks"] >= 2
    assert row["chunks"][0]["start"] == 1
    plan = plan_reads([row])
    assert plan["n_child"] == 1
    assert plan["n_chunks"] == row["n_chunks"]


def test_measure_ast_then_plan_only_counts_chosen_functions():
    src = (
        "class FooForCausalLM:\n"
        "    def forward(self, x):\n"
        "        return x\n"
        "    def extra(self):\n"
        "        return 1\n"
        "\n"
        "class Bar:\n"
        "    def forward(self, x):\n"
        "        return x + 1\n"
    )
    spans = measure_ast(src)
    names = {s["qualname"] for s in spans}
    assert "FooForCausalLM.forward" in names
    fwds = [s for s in spans if s["name"] == "forward"]
    plan = plan_reads(fwds)
    assert plan["n_fit"] == 2
    assert plan["n_child"] == 0


def test_huge_ast_function_requests_one_child():
    body = "        y = 1\n" * 3000
    src = f"class M:\n    def forward(self, x):\n{body}        return y\n"
    fwds = [s for s in measure_ast(src) if s["name"] == "forward"]
    assert fwds[0]["route"] == "child"
    assert plan_reads(fwds)["n_child"] == 1


def test_repo_measure_does_not_include_body():
    repo = load_repo(FIXTURE_REPO)
    row = repo.measure("src/deep/secret.py")
    assert row["route"] == "fit"
    assert "n_tokens" in row
    assert "AUTOCAST" not in str(row)
    plan = repo.plan(["src/deep/secret.py", "src/utils.py"])
    assert plan["n_child"] == 0
    assert plan["n_fit"] == 2
