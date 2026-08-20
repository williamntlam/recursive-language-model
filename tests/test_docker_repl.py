"""Docker REPL tests. Skipped when the daemon is absent."""

from __future__ import annotations

import pytest

from rlm.api import RLM
from rlm.backends.base import FakeClient
from rlm.errors import StartupError
from tests.util import repl

pytestmark = pytest.mark.docker


def docker_available() -> bool:
    try:
        import docker

        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


requires_docker = pytest.mark.skipif(not docker_available(), reason="docker daemon not running")


def test_completion_without_daemon_fails_and_does_not_host_exec(monkeypatch, tmp_path):
    def boom():
        raise StartupError(
            "Docker is not running. Start Docker Desktop or the Docker engine and retry. "
            "The RLM REPL never executes model code on the host."
        )

    monkeypatch.setattr("rlm.environments.docker.docker_client", boom)
    executed = {"host": False}

    def fake_exec(code, ns, *a, **k):  # noqa: ARG001
        executed["host"] = True
        raise AssertionError("host exec must not run")

    monkeypatch.setattr("rlm.repl_ns.exec", fake_exec, raising=False)
    rlm = RLM(
        _client=FakeClient([repl("FINAL('x')")]),
        log_dir=str(tmp_path / "logs"),
    )
    with pytest.raises(StartupError, match="Docker"):
        rlm.completion("q", "hello-context")
    assert executed["host"] is False


@requires_docker
def test_container_has_no_key_no_internet_and_context_is_mounted(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-should-not-enter-container")
    from rlm.environments.docker import DockerEnv
    from rlm.repl_ns import SubcallHandler

    class Quiet(SubcallHandler):
        def llm_query(self, prompt, model=None):
            return "leaf"

        def llm_query_batched(self, prompts, model=None):
            return ["leaf"] * len(prompts)

        def rlm_query(self, prompt, model=None):
            return "child"

        def rlm_query_batched(self, prompts, model=None):
            return ["child"] * len(prompts)

    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "context.txt").write_text("MOUNTED_CONTEXT_PREFIX and more", encoding="utf-8")
    env = DockerEnv(
        handler=Quiet(),
        workspace=ws,
        mode="string",
        query="q",
        max_stdout_chars=500,
        cell_timeout_s=15,
    )
    try:
        key_check = env.container.exec_run(
            ["python", "-c", "import os; print(os.environ.get('OPENAI_API_KEY', ''))"]
        )
        assert key_check.output.decode().strip() in {"", "None"}

        net_check = env.container.exec_run(
            [
                "python",
                "-c",
                "import urllib.request; urllib.request.urlopen('https://example.com', timeout=3)",
            ]
        )
        assert net_check.exit_code != 0

        obs = env.execute("print(context[:20])")
        assert obs.error is None
        assert obs.stdout.strip() == "MOUNTED_CONTEXT_PREFIX and more"[:20]
    finally:
        env.close()


@requires_docker
def test_docker_completion_with_fake_client(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-should-not-enter-container")
    rlm = RLM(
        _client=FakeClient(
            [
                repl(
                    "prefix = context[:12]\n"
                    "FINAL_VAR('prefix')\n"
                )
            ]
        ),
        log_dir=str(tmp_path / "logs"),
    )
    context = "HELLO_DOCKER " + ("z" * 500)
    out = rlm.completion("prefix?", context)
    assert out.response == context[:12]
    # full context must not be in events
    events = (out.trajectory / "events.jsonl").read_text(encoding="utf-8")
    assert context not in events
