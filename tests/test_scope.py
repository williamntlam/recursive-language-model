import json

import pytest

from rlm.core.planner import PlanValidationError, parse_plan, planner_messages, resolve_targets
from rlm.domains.repo import load_repo
from rlm.domains.scope import build_repo_scope
from tests.util import FIXTURE_REPO, make_rlm, repl


def test_repo_scope_is_stable_source_free_and_filters_declarations(tmp_path):
    (tmp_path / "models.py").write_text(
        "class GoodForCausalLM:\n    def forward(self):\n        return 1\n\n"
        "class BadForPreTraining:\n    pass\n",
        encoding="utf-8",
    )
    repo = load_repo(tmp_path)
    first = build_repo_scope(repo, "compare", class_name_patterns=("ForCausalLM",))
    second = build_repo_scope(repo, "compare", class_name_patterns=("ForCausalLM",))
    assert first.canonical_json() == second.canonical_json()
    assert first.digest == second.digest
    assert [record.qualname for record in first.records] == ["GoodForCausalLM"]
    assert "return 1" not in first.canonical_json()


def test_plan_rejects_unknown_duplicate_and_fit_child(tmp_path):
    (tmp_path / "a.py").write_text("def small():\n    pass\n", encoding="utf-8")
    manifest = build_repo_scope(load_repo(tmp_path), "q")
    record = manifest.records[0]
    bad = {
        "version": 1,
        "selected": [{"record_id": record.id, "question": "q", "route": "child"}],
        "report_shape": "cited_markdown",
    }
    with pytest.raises(PlanValidationError):
        parse_plan(json.dumps(bad), manifest)
    good = {
        "version": 1,
        "selected": [{"record_id": record.id, "question": "q", "route": "leaf"}],
        "report_shape": "cited_markdown",
    }
    plan = parse_plan(json.dumps(good), manifest)
    assert resolve_targets(plan, manifest) == [record.target]
    messages = planner_messages("q", manifest, {})
    assert "pass" not in messages[1].content


def test_opt_in_planner_is_source_free_and_scopes_the_root(tmp_path):
    manifest = build_repo_scope(load_repo(FIXTURE_REPO), "where?")
    chosen = manifest.records[0]
    plan = {
        "version": 1,
        "selected": [
            {
                "record_id": chosen.id,
                "question": "inspect",
                "route": "leaf" if chosen.route == "fit" else "child",
            }
        ],
        "report_shape": "cited_markdown",
    }
    rlm, client = make_rlm(
        tmp_path,
        [json.dumps(plan), "leaf finding", repl("FINAL('planned')")],
        planner_enabled=True,
    )
    out = rlm.ask_repo(FIXTURE_REPO, "where?")
    assert out.response == "planned"
    planner_prompt = "\n".join(message.content for message in client.calls[0])
    assert "AUTOCAST_CPU_BF16_IMPL_MARKER" not in planner_prompt
    events = (out.trajectory / "events.jsonl").read_text(encoding="utf-8")
    assert "scope_manifest" in events and "planner" in events
    assert "plan_execution" in events


def test_named_planned_architecture_is_source_free(tmp_path):
    manifest = build_repo_scope(load_repo(FIXTURE_REPO), "where?")
    chosen = manifest.records[0]
    plan = {
        "version": 1,
        "selected": [
            {
                "record_id": chosen.id,
                "question": "inspect",
                "route": "leaf" if chosen.route == "fit" else "child",
            }
        ],
        "report_shape": "cited_markdown",
    }
    rlm, client = make_rlm(
        tmp_path,
        [json.dumps(plan), "leaf finding", repl("FINAL('planned')")],
        architecture="planned",
    )
    out = rlm.ask_repo(FIXTURE_REPO, "where?")
    assert out.response == "planned"
    assert "AUTOCAST_CPU_BF16_IMPL_MARKER" not in "\n".join(
        message.content for message in client.calls[0]
    )


def test_planned_oversized_record_uses_a_scoped_child(tmp_path):
    source = "class Large:\n" + "    value = 'x' * 10\n" * 2_500
    (tmp_path / "large.py").write_text(source, encoding="utf-8")
    manifest = build_repo_scope(load_repo(tmp_path), "inspect")
    chosen = next(record for record in manifest.records if record.route == "child")
    plan = {
        "version": 1,
        "selected": [{"record_id": chosen.id, "question": "inspect", "route": "child"}],
        "report_shape": "cited_markdown",
    }
    rlm, _ = make_rlm(
        tmp_path,
        [json.dumps(plan), repl("FINAL('child finding')"), repl("FINAL('rendered')")],
        planner_enabled=True,
    )
    out = rlm.ask_repo(tmp_path, "inspect")
    assert out.response == "rendered"
    events = (out.trajectory / "events.jsonl").read_text(encoding="utf-8")
    assert '"child_count": 1' in events
    assert '"kind": "rlm_query"' in events
    assert '"scoped": true' in events


def test_invalid_planner_fallback_remains_manifest_scoped(tmp_path):
    (tmp_path / "a.py").write_text(
        "header = 0\ndef only_span():\n    return 1\n", encoding="utf-8"
    )
    rlm, _ = make_rlm(
        tmp_path,
        ["{}", repl("try:\n    repo.read('a.py')\nexcept ValueError:\n    FINAL('scoped')")],
        planner_enabled=True,
    )
    out = rlm.ask_repo(tmp_path, "inspect")
    assert out.response == "scoped"
    events = (out.trajectory / "events.jsonl").read_text(encoding="utf-8")
    assert "planner_fallback_scope" in events
