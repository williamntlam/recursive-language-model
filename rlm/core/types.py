"""Shared types for completions, messages, and REPL observations."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from pathlib import Path


class RecordAccess:
    """Let models use hit.path, hit["path"], or hit[0] on REPL records."""

    def __getitem__(self, key: str | int):
        names = [f.name for f in fields(self)]
        if isinstance(key, int):
            return getattr(self, names[key])
        if isinstance(key, str):
            if key in names:
                return getattr(self, key)
            raise KeyError(key)
        raise TypeError(f"index must be str or int, got {type(key).__name__}")

    def __iter__(self):
        for f in fields(self):
            yield getattr(self, f.name)


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
    tool_events: list[dict] = field(default_factory=list)


@dataclass
class PromptPayload:
    system_prompt: str
    exposed_methods: list[str] = field(default_factory=list)
    user_query: str = ""
    extra_rules: list[str] = field(default_factory=list)
    developer_prompt: str = ""
