"""CLI integration contracts."""

from rlm.cli import main
from tests.util import FIXTURE_REPO


def test_help_exits_zero():
    assert main(["--help"]) == 0


def test_dry_run_ask_no_docker(capsys):
    code = main(["ask", str(FIXTURE_REPO), "--dry-run", "--", "Where is autocast?"])
    assert code == 0
    out = capsys.readouterr().out
    assert "system prompt" in out.lower() or "You are a Recursive Language Model" in out
    assert "instruction_count=" in out
    assert "prompt_tokens=" in out
