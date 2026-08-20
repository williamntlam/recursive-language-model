"""Environment protocol: execute(code) -> Observation."""

from __future__ import annotations

from typing import Protocol

from rlm.core.types import Observation


class Environment(Protocol):
    def execute(self, code: str) -> Observation: ...

    def close(self) -> None: ...
