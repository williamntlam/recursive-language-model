"""Repository workflow integration contracts."""

from rlm.domains.repo import load_repo
from tests.util import FIXTURE_REPO, make_rlm, repl

MARKER = "AUTOCAST_CPU_BF16_IMPL_MARKER"


def test_repo_ignore_skips_node_modules():
    repo = load_repo(FIXTURE_REPO)
    paths = [f.path for f in repo.files()]
    assert not any("node_modules" in p for p in paths)
    assert any(p.endswith("secret.py") for p in paths)


def test_tree_accepts_subdirectory_and_string_depth():
    repo = load_repo(FIXTURE_REPO)
    assert "src" in repo.tree(2)
    assert "src" in repo.tree(max_depth="2")
    scoped = repo.tree("src")
    assert "deep" in scoped or "secret" in scoped
    assert "node_modules" not in scoped
    line = repo.read("src/deep/secret.py", "1", "5")
    assert "AUTOCAST_CPU_BF16_IMPL_MARKER" in line


def test_grep_hit_is_subscriptable():
    repo = load_repo(FIXTURE_REPO)
    hit = repo.grep(MARKER)[0]
    assert hit["path"] == hit.path
    assert hit["line_no"] == hit.line_no
    assert hit[0] == hit.path
    path, line_no, line = hit
    assert path == hit.path
    assert line_no == hit.line_no
    assert MARKER in line


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


def test_repo_ask_sends_slice_to_leaf(tmp_path):
    rlm, client = make_rlm(
        tmp_path,
        [
            repl(
                "out = repo.ask('src/deep/secret.py', "
                "'Quote the marker on one line.', 1, 20)\n"
                "FINAL(out)\n"
            ),
            "leaf-saw-the-file",
        ],
    )
    out = rlm.ask_repo(FIXTURE_REPO, "Where is the marker?")
    assert out.response == "leaf-saw-the-file"
    assert out.usage.subcalls >= 1
    assert "gpt-5-mini" in client.models
    leaf = client.calls[1]
    joined = "\n".join(m.content for m in leaf)
    assert MARKER in joined
    root_second_turn_if_any = client.calls[0]
    root_text = "\n".join(m.content for m in root_second_turn_if_any)
    assert MARKER not in root_text


def test_repo_explore_spawns_child_that_can_grep(tmp_path):
    rlm, client = make_rlm(
        tmp_path,
        [
            repl(
                "ans = repo.explore("
                "'Grep AUTOCAST_CPU_BF16_IMPL_MARKER and FINAL path:line')\n"
                "FINAL(ans)\n"
            ),
            repl(
                "hits = repo.grep('AUTOCAST_CPU_BF16_IMPL_MARKER')\n"
                "FINAL(hits[0].path + ':' + str(hits[0].line_no))\n"
            ),
        ],
    )
    out = rlm.ask_repo(FIXTURE_REPO, "Where is the marker?")
    assert "secret.py" in out.response
    assert out.usage.subcalls >= 1
    assert client.models[0] == "gpt-5"
    assert client.models[1] == "gpt-5"
    parent = "\n".join(m.content for m in client.calls[0])
    assert MARKER not in parent
    events = (out.trajectory / "events.jsonl").read_text(encoding="utf-8")
    assert '"kind": "rlm_query"' in events or '"kind":"rlm_query"' in events


def test_large_ask_routes_to_rlm_query_not_leaf():
    repo = load_repo(FIXTURE_REPO)
    seen = {"llm": 0, "rlm": 0}

    def llm(prompt):
        seen["llm"] += 1
        return "leaf"

    def rlm(prompt, *, targets=None):
        seen["rlm"] += 1
        assert "x" * 50 not in prompt
        assert targets == [{"path": "src/utils.py", "start": None, "end": None}]
        return "from-child"

    repo._query_fn = llm
    repo._rlm_fn = rlm
    repo.read = lambda path, start=None, end=None: "x" * 50_000  # noqa: ARG005
    out = repo.ask("src/utils.py", "summarize")
    assert out == "from-child"
    assert seen["rlm"] == 1
    assert seen["llm"] == 0


def test_medium_ask_routes_to_leaf_not_rlm_query():
    repo = load_repo(FIXTURE_REPO)
    seen = {"llm": 0, "rlm": 0}

    def llm(prompt):
        seen["llm"] += 1
        return "leaf"

    def rlm(prompt, *, targets=None):
        seen["rlm"] += 1
        return "from-child"

    repo._query_fn = llm
    repo._rlm_fn = rlm
    repo.read = lambda path, start=None, end=None: "x" * 5000  # noqa: ARG005
    out = repo.ask("src/utils.py", "summarize")
    assert out == "leaf"
    assert seen["llm"] == 1
    assert seen["rlm"] == 0


def test_scoped_repo_restricts_reads_and_searches():
    repo = load_repo(
        FIXTURE_REPO,
        # Scope only the marker line; broad queries must not expose utils.py.
        targets=[{"path": "src/deep/secret.py", "start": 1, "end": 20}],
    )
    assert [f.path for f in repo.files()] == ["src/deep/secret.py"]
    assert repo.glob("src/deep/secret.py") == ["src/deep/secret.py"]
    assert repo.grep(MARKER)[0].path == "src/deep/secret.py"
    assert MARKER in repo.read("src/deep/secret.py", 1, 20)
    for fn in (
        lambda: repo.read("src/utils.py"),
        lambda: repo.measure("src/utils.py"),
        lambda: repo.file_text("src/utils.py"),
        lambda: repo.glob("**/*.py"),
    ):
        import pytest

        with pytest.raises(ValueError, match="target scope"):
            fn()


def test_scoped_repo_child_cannot_escape_and_records_path_free_metadata(tmp_path):
    rlm, _ = make_rlm(
        tmp_path,
        [
            repl(
                "targets = [{'path': 'src/deep/secret.py', 'start': 1, 'end': 20}]\n"
                "ans = repo.explore('find marker', targets=targets)\n"
                "FINAL(ans)\n"
            ),
            repl(
                "try:\n"
                "    repo.grep('def', glob='**/*.py')\n"
                "except ValueError as exc:\n"
                "    blocked = str(exc)\n"
                "hits = repo.grep('AUTOCAST_CPU_BF16_IMPL_MARKER')\n"
                "FINAL(hits[0].path)\n"
            ),
        ],
    )
    out = rlm.ask_repo(FIXTURE_REPO, "Where is the marker?")
    assert out.response == "src/deep/secret.py"
    trace = (out.trajectory / "trace.jsonl").read_text(encoding="utf-8")
    assert '"scoped":true' in trace or '"scoped": true' in trace
    assert "src/deep/secret.py" not in trace
