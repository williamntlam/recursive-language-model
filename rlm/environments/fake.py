"""In-memory REPL for unit tests. Not a CLI environment."""

from __future__ import annotations

from typing import Any

from rlm.core.types import Observation
from rlm.repl_ns import SubcallHandler, create_namespace, run_cell, snapshot_reserved


class FakeEnv:
    def __init__(
        self,
        bindings: dict[str, Any],
        handler: SubcallHandler,
        *,
        max_stdout_chars: int = 4000,
        cell_timeout_s: float | None = None,
    ) -> None:
        self.ns = create_namespace(bindings, handler, max_stdout_chars=max_stdout_chars)
        self._reserved = snapshot_reserved(self.ns)
        self._cell_timeout_s = cell_timeout_s
        self._max_stdout_chars = max_stdout_chars

    def execute(self, code: str) -> Observation:
        return run_cell(
            self.ns,
            code,
            self._reserved,
            timeout_s=self._cell_timeout_s,
            max_send_chars=max(self._max_stdout_chars * 2, 8000),
            use_alarm=False,
        )

    def close(self) -> None:
        return None
