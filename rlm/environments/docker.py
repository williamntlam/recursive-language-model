"""Product REPL: model code runs in a Docker container, never on the host."""

from __future__ import annotations

import os
import shutil
import socket
import tempfile
import threading
import time
from pathlib import Path

from rlm.core.types import Observation
from rlm.errors import StartupError
from rlm.ipc import read_msg, write_msg
from rlm.repl_ns import SubcallHandler

IMAGE_TAG = "rlm-repl:0.1.4"


def docker_client():
    try:
        import docker
    except ImportError as e:
        raise StartupError("The docker Python package is required.") from e
    try:
        client = docker.from_env()
        client.ping()
        return client
    except Exception as e:
        raise StartupError(
            "Docker is not running. Start Docker Desktop or the Docker engine and retry. "
            "The RLM REPL never executes model code on the host."
        ) from e


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def ensure_image(client) -> None:
    try:
        client.images.get(IMAGE_TAG)
        return
    except Exception:
        pass
    root = repo_root()
    dockerfile = root / "docker" / "Dockerfile"
    if not dockerfile.is_file():
        raise StartupError(f"Dockerfile not found at {dockerfile}")
    client.images.build(
        path=str(root),
        dockerfile="docker/Dockerfile",
        tag=IMAGE_TAG,
        rm=True,
    )


class CallbackServer(threading.Thread):
    def __init__(self, sock_path: Path, handler: SubcallHandler) -> None:
        super().__init__(daemon=True, name="rlm-lm-callback")
        self.sock_path = sock_path
        self.handler = handler
        self._stop = threading.Event()
        self._server: socket.socket | None = None

    def run(self) -> None:
        if self.sock_path.exists():
            self.sock_path.unlink()
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server = srv
        srv.bind(str(self.sock_path))
        os.chmod(self.sock_path, 0o777)
        srv.listen(16)
        srv.settimeout(0.4)
        while not self._stop.is_set():
            try:
                conn, _ = srv.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            # Do not name this `_handle`: on Python 3.13 Thread instances store
            # the OS handle in `_handle`, so `target=self._handle` would pass
            # a `_ThreadHandle` instead of the request method.
            threading.Thread(
                target=self._serve_request, args=(conn,), daemon=True
            ).start()

    def _serve_request(self, conn: socket.socket) -> None:
        try:
            req = read_msg(conn)
            typ = req.get("type")
            try:
                if typ == "llm_query":
                    value = self.handler.llm_query(req.get("prompt", ""), model=req.get("model"))
                elif typ == "llm_query_batched":
                    value = self.handler.llm_query_batched(
                        req.get("prompts") or [], model=req.get("model")
                    )
                elif typ == "rlm_query":
                    value = self.handler.rlm_query(req.get("prompt", ""), model=req.get("model"))
                elif typ == "rlm_query_batched":
                    value = self.handler.rlm_query_batched(
                        req.get("prompts") or [], model=req.get("model")
                    )
                else:
                    raise ValueError(f"unknown callback type {typ!r}")
                write_msg(conn, {"type": "ok", "value": value})
            except Exception as e:
                write_msg(conn, {"type": "error", "message": str(e)})
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def stop(self) -> None:
        self._stop.set()
        if self._server is not None:
            try:
                self._server.close()
            except OSError:
                pass
        if self.sock_path.exists():
            try:
                self.sock_path.unlink()
            except OSError:
                pass


def _wait_for_socket(path: Path, timeout: float, logs_fn) -> socket.socket:
    deadline = time.time() + timeout
    last_err: Exception | None = None
    while time.time() < deadline:
        if path.exists():
            try:
                sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                sock.settimeout(5)
                sock.connect(str(path))
                return sock
            except OSError as e:
                last_err = e
                time.sleep(0.05)
                continue
        time.sleep(0.05)
    extra = ""
    try:
        extra = logs_fn() or ""
    except Exception:
        extra = ""
    raise StartupError(
        f"REPL socket {path} did not appear. Last error: {last_err}. Logs:\n{extra}"
    )


class DockerEnv:
    def __init__(
        self,
        *,
        handler: SubcallHandler,
        workspace: Path,
        mode: str,
        query: str,
        max_stdout_chars: int = 4000,
        cell_timeout_s: float | None = 60.0,
        mem_limit: str = "2g",
    ) -> None:
        self.handler = handler
        self.workspace = Path(workspace).resolve()
        self.mode = mode
        self.query = query
        self.max_stdout_chars = max_stdout_chars
        self.cell_timeout_s = cell_timeout_s
        self._client = docker_client()
        ensure_image(self._client)
        self.ipc_dir = Path(tempfile.mkdtemp(prefix="rlm-ipc-"))
        os.chmod(self.ipc_dir, 0o777)
        self.lm_sock = self.ipc_dir / "lm.sock"
        self.repl_sock_path = self.ipc_dir / "repl.sock"
        self._callback = CallbackServer(self.lm_sock, handler)
        self._callback.start()
        # Give the callback a moment to bind before the container starts.
        deadline = time.time() + 5
        while time.time() < deadline and not self.lm_sock.exists():
            time.sleep(0.02)
        self.container = None
        self._conn: socket.socket | None = None
        try:
            self.container = self._client.containers.run(
                IMAGE_TAG,
                detach=True,
                network_mode="none",
                mem_limit=mem_limit,
                nano_cpus=1_000_000_000,
                pids_limit=256,
                read_only=True,
                tmpfs={"/tmp": "size=64m", "/repl": "size=64m"},
                volumes={
                    str(self.workspace): {"bind": "/workspace", "mode": "ro"},
                    str(self.ipc_dir): {"bind": "/ipc", "mode": "rw"},
                },
                user="1000:1000",
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                environment={},
                working_dir="/repl",
            )
            self._conn = _wait_for_socket(
                self.repl_sock_path,
                timeout=30,
                logs_fn=lambda: self.container.logs().decode("utf-8", errors="replace")
                if self.container
                else "",
            )
            write_msg(
                self._conn,
                {
                    "type": "init",
                    "query": query,
                    "mode": mode,
                    "max_stdout_chars": max_stdout_chars,
                    "cell_timeout_s": cell_timeout_s or 60.0,
                },
            )
            ack = read_msg(self._conn)
            if ack.get("type") != "ok":
                raise StartupError(f"REPL init failed: {ack}")
        except Exception:
            self.close()
            raise

    def execute(self, code: str) -> Observation:
        assert self._conn is not None
        timeout = (self.cell_timeout_s or 60.0) + 5.0
        self._conn.settimeout(timeout)
        write_msg(self._conn, {"type": "exec", "code": code})
        msg = read_msg(self._conn)
        return Observation(
            stdout=msg.get("stdout") or "",
            stderr=msg.get("stderr") or "",
            total_stdout_len=int(msg.get("total_stdout_len") or 0),
            total_stderr_len=int(msg.get("total_stderr_len") or 0),
            sha256=msg.get("sha256") or "",
            final=msg.get("final"),
            error=msg.get("error"),
        )

    def close(self) -> None:
        if self._conn is not None:
            try:
                write_msg(self._conn, {"type": "shutdown"})
            except OSError:
                pass
            try:
                self._conn.close()
            except OSError:
                pass
            self._conn = None
        self._callback.stop()
        if self.container is not None:
            try:
                self.container.stop(timeout=5)
            except Exception:
                pass
            try:
                self.container.remove(force=True)
            except Exception:
                pass
            self.container = None
        shutil.rmtree(self.ipc_dir, ignore_errors=True)
