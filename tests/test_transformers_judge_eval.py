from __future__ import annotations

from evals.transformers_causal_lm_judge import cited_snippets, validate_judgment


def test_cited_snippets_reads_only_valid_bounded_repo_paths(tmp_path):
    source = tmp_path / "src/pkg/model.py"
    source.parent.mkdir(parents=True)
    source.write_text("one\ntwo\nthree\n", encoding="utf-8")

    snippets = cited_snippets(
        "src/pkg/model.py:2-3 is relevant; ../outside.py:1 must be ignored.", tmp_path
    )

    assert len(snippets) == 1
    assert snippets[0].citation == "src/pkg/model.py:2-3"
    assert snippets[0].text == "2: two\n3: three"


def test_validate_judgment_enforces_evidence_and_criterion_thresholds():
    judgment = validate_judgment(
        {
            "scores": {
                "scope_and_coverage": 3,
                "source_grounded_evidence": 2,
                "technical_classification": 2,
                "useful_synthesis": 1,
            },
            "total": 0,
            "pass": False,
            "rationale": "grounded",
            "missing_or_unverified": [],
        },
        [],
    )

    assert judgment["total"] == 8
    assert judgment["pass"] is False
