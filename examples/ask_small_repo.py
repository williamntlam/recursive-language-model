"""Run a small-repo question through the library (needs Docker + OPENAI_API_KEY)."""

from rlm import RLM

if __name__ == "__main__":
    out = RLM(verbose=True).ask_repo(".", query="What is this package for?")
    print(out.response)
    print(out.usage)
