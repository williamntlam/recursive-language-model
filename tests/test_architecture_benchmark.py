import json

import pytest

from tests.architecture_benchmark import Case, citation_metrics, load_cases


def test_architecture_benchmark_cases_cover_every_size_band():
    cases = load_cases()
    assert {case.band for case in cases.values()} == {"small", "medium", "large"}
    assert all(case.evidence_tokens and case.query for case in cases.values())


def test_architecture_benchmark_case_schema_is_strict(tmp_path):
    path = tmp_path / "cases.json"
    path.write_text(json.dumps({"version": 1, "cases": [{"id": "x"}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="invalid schema"):
        load_cases(path)


def test_citation_metrics_count_only_in_target_line_ranges(tmp_path):
    (tmp_path / "ok.py").write_text("one\ntwo\n", encoding="utf-8")
    answer = "ok.py:2-2 works; ../outside.py:1-1 and ok.py:99 do not."
    assert citation_metrics(answer, tmp_path) == {"citations_total": 3, "citations_valid": 1}


def test_case_is_a_immutable_value_object():
    case = Case("x", "small", "<=25k", "question")
    with pytest.raises(AttributeError):
        case.id = "changed"
