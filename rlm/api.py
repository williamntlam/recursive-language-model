"""Library facade: RLM.completion / ask_repo / research."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from rlm.backends.openai import OpenAIClient
from rlm.config import Config, load_config
from rlm.core.history import sha256_text
from rlm.core.prompt_guard import count_instructions, count_tokens
from rlm.core.runtime import Runtime, query_sha, string_metadata, workspace_for_string
from rlm.core.types import Completion, Message, PromptPayload
from rlm.domains.corpus import catalog_rows, corpus_manifest, load_corpus
from rlm.domains.repo import load_repo, repo_manifest
from rlm.errors import ConfigError, StartupError
from rlm.logging.trajectory import TrajectoryLogger
from rlm.prompts import compose_system_prompt, exposed_methods_for


def _fake_env_factory(*, bindings, handler, mode, workspace, config):  # noqa: ARG001
    from rlm.environments.fake import FakeEnv

    return FakeEnv(bindings, handler, max_stdout_chars=config.max_observation_chars)


def _docker_env_factory(*, bindings, handler, mode, workspace, config):
    from rlm.environments.docker import DockerEnv

    if workspace is None:
        raise StartupError("Docker REPL requires a workspace path.")
    return DockerEnv(
        handler=handler,
        workspace=workspace,
        mode=mode,
        query=str(bindings.get("query") or ""),
        max_stdout_chars=config.max_observation_chars,
        cell_timeout_s=config.cell_timeout_s,
        exec_wait_s=config.max_timeout_s,
    )


class RLM:
    def __init__(
        self,
        *,
        config: Config | None = None,
        root_model: str | None = None,
        leaf_model: str | None = None,
        environment: str | None = None,
        max_depth: int | None = None,
        max_iterations: int | None = None,
        max_prompt_tokens: int | None = None,
        max_instructions: int | None = None,
        max_observation_chars: int | None = None,
        max_budget_usd: float | None = None,
        max_timeout_s: float | None = None,
        cell_timeout_s: float | None = None,
        max_concurrent_subcalls: int | None = None,
        max_consecutive_errors: int | None = None,
        log_dir: str | None = None,
        verbose: bool | None = None,
        extra_instructions: list[str] | None = None,
        config_path: str | Path | None = None,
        _client: Any = None,
        _env_factory: Callable | None = None,
    ) -> None:
        self.config = config or load_config(
            config_path=config_path,
            root_model=root_model,
            leaf_model=leaf_model,
            environment=environment,
            max_depth=max_depth,
            max_iterations=max_iterations,
            max_prompt_tokens=max_prompt_tokens,
            max_instructions=max_instructions,
            max_observation_chars=max_observation_chars,
            max_budget_usd=max_budget_usd,
            max_timeout_s=max_timeout_s,
            cell_timeout_s=cell_timeout_s,
            max_concurrent_subcalls=max_concurrent_subcalls,
            max_consecutive_errors=max_consecutive_errors,
            log_dir=log_dir,
            verbose=verbose,
            extra_instructions=extra_instructions,
        )
        self._client = _client
        self._env_factory = _env_factory

    @classmethod
    def from_config(cls, path: str | Path, **kwargs: Any) -> RLM:
        return cls(config_path=path, **kwargs)

    def _client_or_openai(self):
        if self._client is not None:
            return self._client
        return OpenAIClient()

    def _factory(self):
        if self._env_factory is not None:
            return self._env_factory
        return _docker_env_factory

    def _logger(self, query: str, extra: dict) -> TrajectoryLogger:
        return TrajectoryLogger(
            self.config.log_dir,
            query=query,
            extra_meta={
                "query_sha256": query_sha(query),
                "root_model": self.config.root_model,
                "leaf_model": self.config.leaf_model,
                "max_prompt_tokens": self.config.max_prompt_tokens,
                "max_instructions": self.config.max_instructions,
                "max_depth": self.config.max_depth,
                **extra,
            },
        )

    def _runtime(self, logger: TrajectoryLogger, domain: str | None) -> Runtime:
        return Runtime(
            self.config,
            self._client_or_openai(),
            self._factory(),
            logger,
            depth=0,
            domain=domain,
        )

    def completion(self, query: str, context: str) -> Completion:
        logger = self._logger(
            query,
            {
                "context_n_chars": len(context),
                "context_sha256": sha256_text(context),
                "domain": "string",
            },
        )
        workspace, cleanup = workspace_for_string(context)
        bindings = {"query": query, "context": context}
        return self._runtime(logger, None).run(
            query=query,
            metadata=string_metadata(context),
            bindings=bindings,
            workspace=workspace,
            mode="string",
            cleanup_workspace=cleanup,
        )

    def ask_repo(self, path: str | Path, query: str) -> Completion:
        repo = load_repo(path)
        logger = self._logger(
            query,
            {"domain": "repo", "repo": str(repo.root)},
        )
        bindings = {"query": query, "repo": repo, "manifest": repo_manifest(repo)}
        return self._runtime(logger, "repo").run(
            query=query,
            metadata=repo_manifest(repo),
            bindings=bindings,
            workspace=repo.root,
            mode="repo",
            cleanup_workspace=False,
        )

    def research(self, path: str | Path, query: str) -> Completion:
        corpus = load_corpus(path)
        logger = self._logger(
            query,
            {"domain": "research", "n_docs": len(corpus.docs)},
        )
        catalog = catalog_rows(corpus)
        bindings = {
            "query": query,
            "corpus": corpus,
            "catalog": catalog,
        }
        workspace = Path(path).resolve()
        if workspace.is_file():
            workspace = workspace.parent
        return self._runtime(logger, "research").run(
            query=query,
            metadata=corpus_manifest(corpus),
            bindings=bindings,
            workspace=workspace,
            mode="research",
            cleanup_workspace=False,
        )

    def dry_run(self, query: str, metadata: str, domain: str | None = None) -> str:
        payload = PromptPayload(
            system_prompt=compose_system_prompt(domain),
            exposed_methods=exposed_methods_for(domain),
            user_query=query,
            extra_rules=list(self.config.extra_instructions or []),
        )
        n_inst = count_instructions(payload)
        if n_inst > self.config.max_instructions:
            raise ConfigError(
                f"Composed instruction count is {n_inst}; max is {self.config.max_instructions}."
            )
        hist = [
            Message("system", payload.system_prompt),
            Message("user", metadata + "\n\nUser query:\n" + query),
        ]
        n_tok = count_tokens(hist)
        lines = [
            "=== system prompt ===",
            payload.system_prompt,
            "=== metadata ===",
            metadata,
            f"prompt_tokens={n_tok} instruction_count={n_inst} "
            f"max_prompt_tokens={self.config.max_prompt_tokens} "
            f"max_instructions={self.config.max_instructions}",
        ]
        return "\n".join(lines)


# Re-export for tests that want the fake factory without Docker.
fake_env_factory = _fake_env_factory
