"""Hard ceilings for every language-model send."""

from __future__ import annotations

from rlm.config import HARD_MAX_INSTRUCTIONS, HARD_PROMPT_TOKEN_EXCLUSIVE


def assert_sendable(prompt_tokens: int, instruction_count: int) -> None:
    """Reject a send that exceeds either source-grounded safety ceiling."""
    if instruction_count > HARD_MAX_INSTRUCTIONS:
        raise ValueError(f"instructions exceed {HARD_MAX_INSTRUCTIONS}")
    if prompt_tokens >= HARD_PROMPT_TOKEN_EXCLUSIVE:
        raise ValueError(
            f"prompt is {prompt_tokens} tokens; {HARD_PROMPT_TOKEN_EXCLUSIVE} or more is illegal"
        )
