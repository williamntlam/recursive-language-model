from __future__ import annotations

from evals.context_needle_judge import ladder_cases, load_case, validate_judgment


def test_context_needle_ladder_increases_to_half_million_tokens():
    token_counts = [int(load_case(path)["target_tokens"]) for path in ladder_cases()]

    assert token_counts == sorted(token_counts)
    assert token_counts[-1] == 500_000
    assert len(token_counts) >= 4


def test_context_needle_pass_is_gated_by_answer_and_evidence_scores():
    judgment = validate_judgment(
        {
            "scores": {"answer_correctness": 5, "evidence": 1, "instruction_following": 2},
            "total": 0,
            "pass": True,
            "rationale": "missing marker",
            "missing_or_unverified": ["marker"],
        }
    )

    assert judgment["total"] == 8
    assert judgment["pass"] is False
