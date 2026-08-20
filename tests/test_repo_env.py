from rlm.domains.repo import load_repo
from tests.util import FIXTURE_REPO, make_rlm, repl

MARKER = "AUTOCAST_CPU_BF16_IMPL_MARKER"


def test_repo_ignore_skips_node_modules():
    repo = load_repo(FIXTURE_REPO)
    paths = [f.path for f in repo.files()]
    assert not any("node_modules" in p for p in paths)
    assert any(p.endswith("secret.py") for p in paths)


def test_grep_and_read_not_in_initial_metadata(tmp_path):
    rlm, client = make_rlm(
        tmp_path,
        [
            repl(
                "hits = repo.grep('AUTOCAST_CPU_BF16_IMPL_MARKER')\n"
                "path = hits[0].path\n"
                "line = hits[0].line_no\n"
                "body = repo.read(path, line, line)\n"
                "FINAL(path + ':' + str(line))\n"
            )
        ],
    )
    out = rlm.ask_repo(FIXTURE_REPO, "Where is autocast on CPU bfloat16?")
    assert "secret.py" in out.response
    first = "\n".join(m.content for m in client.calls[0])
    assert MARKER not in first
    body = (FIXTURE_REPO / "src" / "deep" / "secret.py").read_text(encoding="utf-8")
    assert body not in first
    hits = load_repo(FIXTURE_REPO).grep(MARKER)
    assert hits
    assert hits[0].path.endswith("secret.py")
    assert "node_modules" not in hits[0].path
