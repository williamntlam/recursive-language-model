"""Hard ceilings: every LM send is < 100k tokens and ≤ 150 instructions."""

from __future__ import annotations

import re
from functools import lru_cache

import tiktoken

from rlm.config import HARD_MAX_INSTRUCTIONS, HARD_PROMPT_TOKEN_EXCLUSIVE
from rlm.core.types import Message, PromptPayload
from rlm.errors import InstructionBudgetError, PromptBudgetError

_LIST_ITEM = re.compile(r"^(?:[-*+]|\d+[.)])\s+\S", re.MULTILINE)
_FENCE = re.compile(r"```.*?```", re.DOTALL)


@lru_cache(maxsize=1)
def _encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(messages: list[Message]) -> int:
    enc = _encoding()
    n = 0
    for msg in messages:
        n += len(enc.encode(msg.role))
        n += len(enc.encode(msg.content or ""))
        n += 3
    return n


def count_text_tokens(text: str) -> int:
    return len(_encoding().encode(text or ""))


def strip_fences(text: str) -> str:
    return _FENCE.sub("", text or "")


def iter_list_items(text: str) -> list[str]:
    body = strip_fences(text)
    items: list[str] = []
    for line in body.splitlines():
        stripped = line.strip()
        if _LIST_ITEM.match(stripped):
            items.append(stripped)
    return items


def count_instructions(payload: PromptPayload) -> int:
    """Count discrete directives. Data, stdout, and model code are not instructions."""
    n = 0
    n += len(iter_list_items(payload.system_prompt))
    n += len(iter_list_items(payload.developer_prompt))
    seen: set[str] = set()
    for name in payload.exposed_methods:
        if name not in seen:
            seen.add(name)
            n += 1
    if payload.user_query.strip():
        n += 1
    n += len(payload.extra_rules)
    return n


def assert_sendable(
    messages: list[Message],
    payload: PromptPayload,
    *,
    max_prompt_tokens: int,
    max_instructions: int,
    as_parent: bool,
) -> tuple[int, int]:
    """Return (prompt_tokens, instruction_count). Raise if the call must not be sent."""
    n_tok = count_tokens(messages)
    n_inst = count_instructions(payload)
    if n_inst > min(max_instructions, HARD_MAX_INSTRUCTIONS):
        err = InstructionBudgetError(
            f"Composed instruction count is {n_inst}; max is "
            f"{min(max_instructions, HARD_MAX_INSTRUCTIONS)}. "
            "Do not drop rules to fit; delete or merge them."
        )
        if as_parent:
            raise err
        raise err
    if n_tok >= HARD_PROMPT_TOKEN_EXCLUSIVE or n_tok > max_prompt_tokens:
        msg = (
            f"Error: prompt is {n_tok} tokens; max is {max_prompt_tokens}. "
            "Slice the argument."
        )
        if as_parent:
            raise PromptBudgetError(
                f"Parent prompt would be {n_tok} tokens (max {max_prompt_tokens}). "
                "Not sending. Observation truncation exists so this should be rare; "
                "lower max_observation_chars rather than summarizing the corpus."
            )
        raise PromptBudgetError(msg)
    return n_tok, n_inst
