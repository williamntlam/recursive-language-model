from pathlib import Path
from typing import NamedTuple

from rlm.api import RLM, fake_env_factory
from rlm.backends.base import FakeClient

FIXTURE_REPO = Path(__file__).resolve().parent / "fixtures" / "small_repo"
FIXTURE_CORPUS = Path(__file__).resolve().parent / "fixtures" / "tiny_corpus"


class RLMHarness(NamedTuple):
    """Named fake-runtime inputs and observable client output for one test."""

    rlm: RLM
    client: FakeClient


def repl(code: str) -> str:
    return f"```repl\n{code}\n```"


def make_rlm(tmp_path: Path, script: list[str], **kwargs) -> RLMHarness:
    """Build an RLM with explicit scripted model input and captured client output."""
    client = FakeClient(script)
    rlm = RLM(
        _client=client,
        _env_factory=fake_env_factory,
        log_dir=str(tmp_path / "logs"),
        **kwargs,
    )
    return RLMHarness(rlm, client)


def hist_text(client: FakeClient) -> str:
    return "\n".join(m.content for call in client.calls for m in call)
