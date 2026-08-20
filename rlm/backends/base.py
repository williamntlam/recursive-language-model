"""LM client protocol. FakeClient lives here for tests."""

from __future__ import annotations

import threading
from typing import Protocol

from rlm.core.prompt_guard import count_tokens
from rlm.core.types import LMResponse, Message
from rlm.errors import PromptBudgetError

HARD = 100_000


class LMClient(Protocol):
    def complete(self, messages: list[Message], *, model: str, **kwargs) -> LMResponse: ...


class FakeClient:
    """Queued model outputs. Raises if an oversize payload reaches the client."""

    def __init__(self, script: list[str] | None = None) -> None:
        self.script = list(script or [])
        self.calls: list[list[Message]] = []
        self.models: list[str] = []
        self._lock = threading.Lock()

    def complete(self, messages: list[Message], *, model: str, **kwargs) -> LMResponse:
        n = count_tokens(messages)
        if n >= HARD:
            raise AssertionError(
                f"FakeClient received an illegal payload of {n} tokens (>= {HARD})"
            )
        joined = "\n".join(m.content for m in messages)
        with self._lock:
            if "FAIL_PLEASE" in joined:
                raise RuntimeError("leaf failed")
            self.calls.append(list(messages))
            self.models.append(model)
            if not self.script:
                raise RuntimeError("FakeClient script exhausted")
            text = self.script.pop(0)
        prompt_tokens = n
        completion_tokens = max(1, len(text) // 4)
        return LMResponse(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model=model,
        )


class RaisingClient:
    """Test helper: any complete() call is a failed guard."""

    def complete(self, messages: list[Message], *, model: str, **kwargs) -> LMResponse:
        n = count_tokens(messages)
        raise PromptBudgetError(f"complete() must not be called (payload {n} tokens)")
