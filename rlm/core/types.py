"""Shared types for completions, messages, and REPL observations."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Message:
    role: str
    content: str


@dataclass
class Usage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float | None = None
    iterations: int = 0
    subcalls: int = 0


@dataclass
class Completion:
    response: str
    usage: Usage
    trajectory: Path | None = None


@dataclass
class LMResponse:
    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    model: str = ""


@dataclass
class Observation:
    stdout: str
    stderr: str
    total_stdout_len: int
    total_stderr_len: int
    sha256: str
    final: str | None = None
    error: str | None = None


@dataclass
class PromptPayload:
    system_prompt: str
    exposed_methods: list[str] = field(default_factory=list)
    user_query: str = ""
    extra_rules: list[str] = field(default_factory=list)
    developer_prompt: str = ""
