"""Official OpenAI SDK. The only v0 backend."""

from __future__ import annotations

import os

from openai import OpenAI

from rlm.core.types import LMResponse, Message
from rlm.envfile import load_dotenv
from rlm.errors import StartupError


def _uses_responses_api(model: str) -> bool:
    lowered = model.lower()
    return lowered.startswith("gpt-5") or lowered.startswith("o1") or lowered.startswith("o3")


class OpenAIClient:
    def __init__(self) -> None:
        load_dotenv()
        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise StartupError(
                "OPENAI_API_KEY is not set. Export it or put it in a gitignored .env file. "
                "It is never accepted as a CLI flag."
            )
        kwargs: dict[str, str] = {"api_key": key}
        org = os.environ.get("OPENAI_ORG_ID")
        project = os.environ.get("OPENAI_PROJECT")
        if org:
            kwargs["organization"] = org
        if project:
            kwargs["project"] = project
        self._client = OpenAI(**kwargs)

    def complete(self, messages: list[Message], *, model: str, **kwargs) -> LMResponse:
        if _uses_responses_api(model):
            return self._complete_responses(messages, model=model)
        return self._complete_chat(messages, model=model)

    def _complete_chat(self, messages: list[Message], *, model: str) -> LMResponse:
        resp = self._client.chat.completions.create(
            model=model,
            messages=[{"role": m.role, "content": m.content} for m in messages],
        )
        text = (resp.choices[0].message.content or "") if resp.choices else ""
        usage = resp.usage
        return LMResponse(
            text=text,
            prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
            model=model,
        )

    def _complete_responses(self, messages: list[Message], *, model: str) -> LMResponse:
        payload = [{"role": m.role, "content": m.content} for m in messages]
        resp = self._client.responses.create(model=model, input=payload)
        text = getattr(resp, "output_text", None) or ""
        if not text:
            chunks: list[str] = []
            for item in getattr(resp, "output", None) or []:
                for content in getattr(item, "content", None) or []:
                    value = getattr(content, "text", None)
                    if value:
                        chunks.append(value)
            text = "".join(chunks)
        usage = getattr(resp, "usage", None)
        prompt_tokens = int(
            getattr(usage, "input_tokens", 0) or getattr(usage, "prompt_tokens", 0) or 0
        )
        completion_tokens = int(
            getattr(usage, "output_tokens", 0) or getattr(usage, "completion_tokens", 0) or 0
        )
        return LMResponse(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            model=model,
        )
