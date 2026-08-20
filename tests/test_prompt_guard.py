import pytest
import tiktoken

from rlm.api import RLM, fake_env_factory
from rlm.backends.base import FakeClient
from rlm.backends.openai import OpenAIClient
from rlm.core.prompt_guard import count_instructions, count_tokens, iter_list_items
from rlm.core.types import PromptPayload
from rlm.errors import ConfigError, InstructionBudgetError, PromptBudgetError, StartupError
from rlm.prompts import compose_system_prompt, exposed_methods_for, load_prompt
from tests.util import make_rlm, repl


def test_ceilings_are_not_raisable():
    with pytest.raises(ConfigError, match="max_prompt_tokens"):
        RLM(max_prompt_tokens=100_000, _client=FakeClient(), _env_factory=fake_env_factory)
    with pytest.raises(ConfigError, match="max_instructions"):
        RLM(max_instructions=151, _client=FakeClient(), _env_factory=fake_env_factory)


def test_parent_oversize_hist_not_sent(tmp_path):
    rlm, client = make_rlm(
        tmp_path,
        [repl("FINAL('should-not-run')\n")],
        max_prompt_tokens=80,
    )
    with pytest.raises(PromptBudgetError):
        rlm.completion("q", "tiny")
    assert client.calls == []


def test_llm_query_100k_tokens_returns_error_and_does_not_send(tmp_path):
    enc = tiktoken.get_encoding("cl100k_base")
    unit = "xyzzy "
    reps = 1
    while len(enc.encode(unit * reps)) < 100_500:
        reps = reps * 2 if reps < 20_000 else reps + 20_000
    blob = unit * reps
    assert len(enc.encode(blob)) >= 100_000
    rlm, client = make_rlm(
        tmp_path,
        [repl("result = llm_query(context)\nFINAL(result)\n")],
    )
    out = rlm.completion("slice first", blob)
    assert out.response.startswith("Error:")
    assert "tokens" in out.response.lower() or "Slice" in out.response
    for msgs in client.calls:
        assert count_tokens(msgs) < 100_000


def test_instruction_ceiling_151_fails_before_send(tmp_path):
    extras = [f"Additional rule {i}: never do {i}." for i in range(140)]
    rlm, client = make_rlm(
        tmp_path,
        [repl("FINAL('nope')\n")],
        extra_instructions=extras,
    )
    with pytest.raises(InstructionBudgetError):
        rlm.completion("one-line query", "ctx")
    assert client.calls == []


def test_prompt_files_plus_builtins_under_150():
    query = "one-line user query"
    for domain in (None, "repo", "research"):
        payload = PromptPayload(
            system_prompt=compose_system_prompt(domain),
            exposed_methods=exposed_methods_for(domain),
            user_query=query,
        )
        n = count_instructions(payload)
        assert n <= 150, (domain, n)
        root_items = iter_list_items(load_prompt("root.md"))
        assert len(root_items) <= 40


def test_openai_client_requires_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(StartupError, match="OPENAI_API_KEY"):
        OpenAIClient()


def test_fake_client_does_not_need_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    client = FakeClient([repl("FINAL('ok')\n")])
    from rlm.core.types import Message as M

    resp = client.complete([M("user", "hi")], model="gpt-5-mini")
    assert resp.text.startswith("```repl")
