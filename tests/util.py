from pathlib import Path

from rlm.api import RLM, fake_env_factory
from rlm.backends.base import FakeClient

FIXTURE_REPO = Path(__file__).resolve().parent / "fixtures" / "small_repo"
FIXTURE_CORPUS = Path(__file__).resolve().parent / "fixtures" / "tiny_corpus"


def repl(code: str) -> str:
    return f"```repl\n{code}\n```"


def make_rlm(tmp_path: Path, script: list[str], **kwargs) -> tuple[RLM, FakeClient]:
    client = FakeClient(script)
    rlm = RLM(
        _client=client,
        _env_factory=fake_env_factory,
        log_dir=str(tmp_path / "logs"),
        **kwargs,
    )
    return rlm, client


def hist_text(client: FakeClient) -> str:
    return "\n".join(m.content for call in client.calls for m in call)
