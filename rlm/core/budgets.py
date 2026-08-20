"""USD / wall-clock remaining-budget inheritance."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from rlm.core.types import LMResponse
from rlm.errors import BudgetExhaustedError

# Estimated USD per million tokens (input, output). Used when OpenAI does not report cost.
PRICES_PER_MILLION: dict[str, tuple[float, float]] = {
    "gpt-5": (1.25, 10.00),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5-nano": (0.05, 0.40),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
}


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    inp, out = PRICES_PER_MILLION.get(model, (1.00, 4.00))
    return (prompt_tokens / 1_000_000.0) * inp + (completion_tokens / 1_000_000.0) * out


@dataclass
class Budget:
    max_usd: float | None = None
    max_timeout_s: float | None = None
    deadline: float | None = None
    spent_usd: float = 0.0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    iterations: int = 0
    subcalls: int = 0
    started_at: float = field(default_factory=time.monotonic)

    @classmethod
    def from_config(cls, max_usd: float | None, max_timeout_s: float | None) -> Budget:
        deadline = None
        if max_timeout_s is not None:
            deadline = time.monotonic() + max_timeout_s
        return cls(max_usd=max_usd, max_timeout_s=max_timeout_s, deadline=deadline)

    def remaining_timeout(self) -> float | None:
        if self.deadline is None:
            return None
        return max(0.0, self.deadline - time.monotonic())

    def remaining_usd(self) -> float | None:
        if self.max_usd is None:
            return None
        return max(0.0, self.max_usd - self.spent_usd)

    def check(self) -> None:
        rem_t = self.remaining_timeout()
        if rem_t is not None and rem_t <= 0:
            raise BudgetExhaustedError("Wall-clock timeout exhausted.")
        rem_usd = self.remaining_usd()
        if rem_usd is not None and rem_usd <= 0:
            raise BudgetExhaustedError("USD budget exhausted.")

    def record(self, response: LMResponse) -> float:
        cost = estimate_cost_usd(
            response.model, response.prompt_tokens, response.completion_tokens
        )
        self.spent_usd += cost
        self.prompt_tokens += response.prompt_tokens
        self.completion_tokens += response.completion_tokens
        self.check()
        return cost

    def inherit(self) -> Budget:
        """Child gets remaining timeout / USD, not the original totals."""
        rem_t = self.remaining_timeout()
        rem_usd = self.remaining_usd()
        child = Budget.from_config(max_usd=rem_usd, max_timeout_s=rem_t)
        return child
