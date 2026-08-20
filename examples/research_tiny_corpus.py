"""Run a tiny multi-document question (needs Docker + OPENAI_API_KEY)."""

from pathlib import Path

from rlm import RLM

CORPUS = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "tiny_corpus"

if __name__ == "__main__":
    out = RLM(verbose=True).research(
        CORPUS,
        query="Where do these documents disagree about recursive inference vs compaction?",
    )
    print(out.response)
    print(out.usage)
