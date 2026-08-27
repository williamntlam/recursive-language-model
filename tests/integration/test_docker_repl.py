"""Docker REPL integration contracts, with isolated IPC unit checks."""

from __future__ import annotations

import inspect
import json
import time

import pytest

from rlm.api import RLM
from rlm.backends.base import FakeClient
from rlm.errors import StartupError
from tests.util import repl


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


def test_callback_server_does_not_shadow_thread_handle():
    """Python 3.13 Thread.__init__ sets self._handle to a _ThreadHandle."""
    from rlm.environments.docker import CallbackServer

    names = {name for name, _ in inspect.getmembers(CallbackServer, predicate=inspect.isfunction)}
    assert "_handle" not in names
    assert "_serve_request" in names


def test_host_exec_timeout_blocks_when_session_is_unlimited():
    from rlm.environments.docker import host_exec_timeout

    assert host_exec_timeout(None) is None
    assert host_exec_timeout(0) is None
    assert host_exec_timeout(60.0) == 65.0


def test_serve_request_swallows_broken_pipe(tmp_path):
    from rlm.environments.docker import CallbackServer
    from rlm.repl_ns import SubcallHandler

    class H(SubcallHandler):
        def llm_query(self, prompt, model=None):
            return "leaf"

        def llm_query_batched(self, prompts, model=None):
            return ["leaf"] * len(prompts)

        def rlm_query(self, prompt, model=None):
            return "child"

        def rlm_query_batched(self, prompts, model=None):
            return ["child"] * len(prompts)

    class BrokenPipeStream:
        def __init__(self):
            payload = json.dumps({"type": "llm_query", "prompt": "hi"}).encode()
            self._input = bytearray(len(payload).to_bytes(4, "big") + payload)
            self.closed = False

        def recv(self, n):
            chunk = bytes(self._input[:n])
            del self._input[:n]
            return chunk

        def sendall(self, data):  # noqa: ARG002
            raise BrokenPipeError()

        def close(self):
            self.closed = True

    stream = BrokenPipeStream()
    CallbackServer(tmp_path / "lm.sock", H())._serve_request(stream)
    assert stream.closed


@pytest.mark.docker
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


@pytest.mark.docker
@requires_docker
def test_container_init_preserves_repo_target_scope(tmp_path):
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

    workspace = tmp_path / "repo"
    workspace.mkdir()
    (workspace / "allowed.py").write_text("ALLOWED = 1\n", encoding="utf-8")
    (workspace / "outside.py").write_text("OUTSIDE = 1\n", encoding="utf-8")
    env = DockerEnv(
        handler=Quiet(),
        workspace=workspace,
        mode="repo",
        query="q",
        targets=[{"path": "allowed.py", "start": None, "end": None}],
    )
    try:
        visible = env.execute("print([row.path for row in repo.files()])")
        assert visible.error is None
        assert visible.stdout.strip() == "['allowed.py']"
        blocked = env.execute("repo.read('outside.py')")
        assert blocked.error is not None
        assert "outside the declared repository target scope" in blocked.stderr
    finally:
        env.close()


@pytest.mark.docker
@requires_docker
def test_rlm_query_can_outlive_cell_cpu_timeout(tmp_path):
    """Nested host callbacks must not be killed by the cell CPU SIGALRM."""
    from rlm.environments.docker import DockerEnv
    from rlm.repl_ns import SubcallHandler

    class Slow(SubcallHandler):
        def llm_query(self, prompt, model=None):
            return "leaf"

        def llm_query_batched(self, prompts, model=None):
            return ["leaf"] * len(prompts)

        def rlm_query(self, prompt, model=None):
            time.sleep(2.5)
            return "slow-child"

        def rlm_query_batched(self, prompts, model=None):
            return ["child"] * len(prompts)

    ws = tmp_path / "ws"
    ws.mkdir()
    env = DockerEnv(
        handler=Slow(),
        workspace=ws,
        mode="string",
        query="q",
        cell_timeout_s=1.0,
        exec_wait_s=None,
    )
    try:
        obs = env.execute("print(rlm_query('x'))")
        assert obs.error is None, obs.stderr
        assert "slow-child" in obs.stdout
    finally:
        env.close()


@pytest.mark.docker
@requires_docker
def test_docker_completion_with_fake_client(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-should-not-enter-container")
    rlm = RLM(
        _client=FakeClient([repl("prefix = context[:12]\nFINAL_VAR('prefix')\n")]),
        log_dir=str(tmp_path / "logs"),
    )
    context = "HELLO_DOCKER " + ("z" * 500)
    out = rlm.completion("prefix?", context)
    assert out.response == context[:12]
    # full context must not be in events
    events = (out.trajectory / "events.jsonl").read_text(encoding="utf-8")
    assert context not in events
