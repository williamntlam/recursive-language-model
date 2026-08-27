"""Trajectory tracing integration contracts."""

import json

from rlm.cli import main
from rlm.logging.html import _legacy_fallback_tool_start
from rlm.logging.trace import read_trace, validate_trace
from tests.util import FIXTURE_REPO, make_rlm, repl


def test_metadata_trace_is_causal_and_excludes_bound_source(tmp_path):
    rlm, _ = make_rlm(
        tmp_path,
        [repl("hits = repo.grep('AUTOCAST_CPU_BF16_IMPL_MARKER')\nFINAL(hits[0].path)\n")],
    )
    out = rlm.ask_repo(FIXTURE_REPO, "where is it?")
    records = read_trace(out.trajectory / "trace.jsonl")
    assert not validate_trace(records)
    assert (out.trajectory / "trace-summary.json").is_file()
    raw = (out.trajectory / "trace.jsonl").read_text(encoding="utf-8")
    assert "AUTOCAST_CPU_BF16_IMPL_MARKER" not in raw
    assert any(r.get("name") == "repo.grep" for r in records)
    assert any(r.get("name") == "root.complete" for r in records)
    tool_starts = [r for r in records if r.get("event") == "span_start" and r.get("kind") == "tool"]
    tool_ends = [r for r in records if r.get("event") == "span_end" and r.get("kind") == "tool"]
    assert {r["span_id"] for r in tool_starts} == {r["span_id"] for r in tool_ends}


def test_content_trace_writes_capped_local_artifacts(tmp_path):
    rlm, _ = make_rlm(
        tmp_path, [repl("x = llm_query('say hi')\nFINAL(x)\n"), "hello"], trace_capture="content"
    )
    out = rlm.completion("q", "context-" + "x" * 300)
    manifest = json.loads((out.trajectory / "artifacts" / "manifest.json").read_text())
    assert manifest
    records = read_trace(out.trajectory / "trace.jsonl")
    assert any(r.get("prompt_artifact") for r in records)
    assert any(r.get("output_artifact") for r in records)


def test_callback_is_child_of_its_repl_cell(tmp_path):
    rlm, _ = make_rlm(
        tmp_path,
        [repl("x = llm_query('say hi')\nFINAL(x)\n"), "hello"],
    )
    out = rlm.completion("q", "context-" + "x" * 300)
    records = read_trace(out.trajectory / "trace.jsonl")
    starts = {r["span_id"]: r for r in records if r.get("event") == "span_start"}
    callback = next(r for r in starts.values() if r.get("name") == "llm_query")
    assert starts[callback["parent_span_id"]]["name"] == "repl.cell"


def test_report_renders_nested_tree_and_opt_in_content(tmp_path):
    rlm, _ = make_rlm(
        tmp_path,
        [repl("x = llm_query('say hi')\nFINAL(x)\n"), "hello"],
        trace_capture="content",
    )
    out = rlm.completion("q", "context-" + "x" * 300)
    html = (out.trajectory / "report.html").read_text(encoding="utf-8")
    assert "Call graph overview" in html
    assert "graph-edge" in html
    assert "Each branch is linked by" in html
    assert "trace-children" in html
    assert "Input / prompt" in html
    assert "Output / response" in html
    assert "say hi" in html


def test_report_hides_only_legacy_duplicate_tool_start():
    records = [
        {
            "event": "span_start",
            "kind": "tool",
            "name": "repo.read",
            "span_id": "real",
            "parent_span_id": "cell",
        },
        {
            "event": "span_start",
            "kind": "tool",
            "name": "repo.read",
            "span_id": "duplicate",
            "parent_span_id": "cell",
        },
        {"event": "span_end", "kind": "tool", "name": "repo.read", "span_id": "real"},
    ]
    assert _legacy_fallback_tool_start(records[1], records)
    assert not _legacy_fallback_tool_start(records[0], records)


def test_traces_command_indexes_completed_runs(tmp_path, capsys):
    rlm, _ = make_rlm(tmp_path, [repl("FINAL('ok')\n")])
    rlm.completion("q", "context-" + "x" * 300)
    assert main(["traces", str(tmp_path / "logs")]) == 0
    index = json.loads(capsys.readouterr().out)
    assert index[0]["valid"] is True
