from pathlib import Path

from rlm.prompts.catalog import CORPUS_METHODS, REPO_METHODS, ROOT_BUILTINS

PROMPTS_DIR = Path(__file__).resolve().parent


def load_prompt(name: str) -> str:
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip() + "\n"


def compose_system_prompt(domain: str | None) -> str:
    parts = [load_prompt("root.md")]
    if domain == "repo":
        parts.append(load_prompt("repo.md"))
    elif domain == "research":
        parts.append(load_prompt("research.md"))
    return "\n".join(parts).strip() + "\n"


def leaf_system_prompt() -> str:
    return load_prompt("leaf.md")


def exposed_methods_for(domain: str | None) -> list[str]:
    methods = list(ROOT_BUILTINS)
    if domain == "repo":
        methods.extend(REPO_METHODS)
    elif domain == "research":
        methods.extend(CORPUS_METHODS)
    return methods
