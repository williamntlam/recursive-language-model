import json
from pathlib import Path

import pytest

from rlm.api import RLM
from rlm.backends.base import FakeClient
from rlm.cli import main
from rlm.core.types import Usage
from rlm.logging.html import resolve_run_dir
from rlm.logging.trajectory import TrajectoryLogger
from tests.util import make_rlm, repl


def _run_dir(tmp_path: Path) -> Path:
    logger = TrajectoryLogger(
        tmp_path / "logs",
        query="where is the needle",
        extra_meta={
            "query_sha256": "abcd",
            "root_model": "gpt-5",
            "leaf_model": "gpt-5-mini",
            "max_prompt_tokens": 99999,
            "max_instructions": 150,
            "max_depth": 16,
            "domain": "repo",
        },
    )
    logger.event(
        kind="root_lm",
        iteration=0,
        depth=0,
        model="gpt-5",
        prompt_tokens=800,
        instruction_count=40,
        completion_tokens=20,
        latency_s=0.4,
        cost_usd=0.001,
    )
    logger.event(
        kind="repl",
        iteration=0,
        depth=0,
        code="hits = repo.grep('needle')\nprint(hits[:3])",
        stdout="[GrepHit(...)]",
    )
    logger.event(
        kind="llm_query",
        depth=0,
        model="gpt-5-mini",
        prompt_tokens=200,
        instruction_count=40,
        completion_tokens=30,
        latency_s=0.2,
        cost_usd=0.0004,
    )
    logger.event(kind="rlm_query", depth=0, child_depth=1, answer_n_chars=12)
    logger.event(
        kind="root_lm",
        iteration=0,
        depth=1,
        model="gpt-5",
        prompt_tokens=400,
        instruction_count=40,
    )
    logger.finish("The needle is in src/deep/secret.py:4.", Usage(800, 50, 0.002, 2, 3))
    return logger.dir


def test_finish_writes_report_html(tmp_path):
    run = _run_dir(tmp_path)
    html_path = run / "report.html"
    assert html_path.is_file()
    html = html_path.read_text(encoding="utf-8")
    assert "The needle is in src/deep/secret.py:4." in html
    assert "Prompt tokens" in html
    assert "Total tokens" in html
    assert "Cost (USD)" in html
    assert "LM calls" in html
    assert ">850<" in html  # usage.json 800+50
    assert ">820<" in html  # first root_lm 800+20
    assert ">230<" in html  # llm_query 200+30
    assert "$0.0020" in html  # run total from usage.json
    assert "$0.0010" in html  # first root_lm
    assert "$0.0004" in html  # llm_query
    assert "Sum of 3 calls" in html
    assert "llm_query" in html
    assert "Parent prompt tokens" in html
    assert "Instruction count is constant" in html
    assert "complete" in html


def test_html_escapes_script(tmp_path):
    logger = TrajectoryLogger(tmp_path / "logs", query="q", extra_meta={"domain": "string"})
    logger.event(
        kind="repl",
        depth=0,
        iteration=0,
        code="<script>alert(1)</script>",
        stdout="<b>raw</b>",
    )
    logger.finish("ok <script>", Usage())
    html = (logger.dir / "report.html").read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "&lt;b&gt;raw&lt;/b&gt;" in html


def test_incomplete_run_still_writes_html(tmp_path):
    logger = TrajectoryLogger(tmp_path / "logs", query="q", extra_meta={})
    logger.event(kind="parse_error", iteration=0, depth=0)
    path = logger.write_html()
    html = path.read_text(encoding="utf-8")
    assert "incomplete" in html
    assert "parse error" in html


def test_resolve_latest_child(tmp_path):
    parent = tmp_path / "logs"
    older = parent / "a"
    newer = parent / "z"
    older.mkdir(parents=True)
    newer.mkdir()
    (older / "events.jsonl").write_text("{}\n", encoding="utf-8")
    (newer / "events.jsonl").write_text("{}\n", encoding="utf-8")
    assert resolve_run_dir(parent) == newer.resolve()
    assert resolve_run_dir(newer / "events.jsonl") == newer.resolve()


def test_cli_report(tmp_path, capsys):
    run = _run_dir(tmp_path)
    code = main(["report", str(run)])
    assert code == 0
    out = capsys.readouterr().out.strip()
    assert out.endswith("report.html")
    assert Path(out).is_file()


def test_cli_report_missing(tmp_path):
    assert main(["report", str(tmp_path / "nope")]) == 4


def test_completion_writes_report(tmp_path):
    rlm, _ = make_rlm(tmp_path, [repl("FINAL('hi')\n")])
    out = rlm.completion("q", "context-" + "n" * 300)
    assert out.response == "hi"
    assert out.trajectory is not None
    html = (out.trajectory / "report.html").read_text(encoding="utf-8")
    assert "hi" in html
    assert "REPL cell" in html
    assert not (out.trajectory / "error.txt").exists()


def test_repl_stderr_writes_error_txt(tmp_path):
    rlm, _ = make_rlm(
        tmp_path,
        [repl("print('ok')\n1/0\n"), repl("FINAL('recovered')\n")],
        max_consecutive_errors=5,
    )
    out = rlm.completion("q", "context-" + "n" * 300)
    assert out.response == "recovered"
    err_path = out.trajectory / "error.txt"
    assert err_path.is_file()
    text = err_path.read_text(encoding="utf-8")
    assert "ZeroDivisionError" in text
    assert "1/0" in text
    assert "=== repl" in text


def test_repl_errors_are_indexed_across_runs_without_code(tmp_path):
    rlm, _ = make_rlm(
        tmp_path,
        [repl("secret_literal = 'do not copy this'\n1/0\n"), repl("FINAL('recovered')\n")],
        max_consecutive_errors=5,
    )
    out = rlm.completion("q", "context")
    index = tmp_path / "repl_errors.jsonl"
    rows = [json.loads(line) for line in index.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    row = rows[0]
    assert row["stage"] == "cell"
    assert row["trajectory"] == str(out.trajectory)
    assert row["error_type"] == "ReplCellError"
    assert row["code_n_chars"] > 0
    assert "code_sha256" in row
    assert "secret_literal" not in json.dumps(row)


def test_repl_startup_errors_are_indexed(tmp_path):
    def unavailable_env(**kwargs):  # noqa: ARG001
        raise RuntimeError("REPL image is unavailable")

    rlm = RLM(
        _client=FakeClient([]),
        _env_factory=unavailable_env,
        log_dir=str(tmp_path / "logs"),
    )
    with pytest.raises(RuntimeError, match="image is unavailable"):
        rlm.completion("q", "context")

    rows = [
        json.loads(line)
        for line in (tmp_path / "repl_errors.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert len(rows) == 1
    assert rows[0]["stage"] == "startup"
    assert rows[0]["error_type"] == "RuntimeError"


def test_parse_error_writes_error_txt(tmp_path):
    logger = TrajectoryLogger(tmp_path / "logs", query="q", extra_meta={})
    logger.event(kind="parse_error", iteration=0, depth=0, text_preview="I refuse.")
    path = logger.write_html()
    html = path.read_text(encoding="utf-8")
    assert "incomplete" in html
    assert "parse error" in html
    err = (logger.dir / "error.txt").read_text(encoding="utf-8")
    assert "parse_error" in err
    assert "I refuse." in err
