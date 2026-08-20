"""Iteration loop, history policy, recursion, prompt guard."""

from __future__ import annotations

import hashlib
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from rlm.config import Config
from rlm.core.budgets import Budget
from rlm.core.history import format_observation, sha256_text
from rlm.core.parse import extract_repl_code
from rlm.core.prompt_guard import assert_sendable, count_instructions, count_tokens
from rlm.core.types import Completion, Message, PromptPayload, Usage
from rlm.errors import (
    BudgetExhaustedError,
    InstructionBudgetError,
    PromptBudgetError,
    ReplErrorsExhausted,
)
from rlm.logging.trajectory import TrajectoryLogger
from rlm.prompts import compose_system_prompt, exposed_methods_for, leaf_system_prompt
from rlm.repl_ns import SubcallHandler

CHILD_QUERY = (
    "Execute the task described in the `context` variable. "
    "Use the REPL. Finish with FINAL_VAR or FINAL."
)


class RuntimeHandler(SubcallHandler):
    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime

    def llm_query(self, prompt: str, model: str | None = None) -> str:
        return self.runtime.leaf_complete(prompt, model=model)

    def llm_query_batched(self, prompts: list[str], model: str | None = None) -> list[str]:
        return self.runtime.batched(self.llm_query, prompts, model)

    def rlm_query(self, prompt: str, model: str | None = None) -> str:
        return self.runtime.child_rlm(prompt, model=model)

    def rlm_query_batched(self, prompts: list[str], model: str | None = None) -> list[str]:
        return self.runtime.batched(self.rlm_query, prompts, model)


class Runtime:
    def __init__(
        self,
        config: Config,
        client,
        env_factory: Callable[..., Any],
        logger: TrajectoryLogger,
        *,
        depth: int = 0,
        budget: Budget | None = None,
        domain: str | None = None,
    ) -> None:
        self.config = config
        self.client = client
        self.env_factory = env_factory
        self.logger = logger
        self.depth = depth
        self.domain = domain
        self.budget = budget or Budget.from_config(config.max_budget_usd, config.max_timeout_s)
        self.handler = RuntimeHandler(self)
        self._budget_lock = threading.Lock()

    def compose_payload(self, query: str) -> PromptPayload:
        extras = list(self.config.extra_instructions or [])
        return PromptPayload(
            system_prompt=compose_system_prompt(self.domain),
            exposed_methods=exposed_methods_for(self.domain),
            user_query=query,
            extra_rules=extras,
        )

    def check_instruction_budget(self, payload: PromptPayload) -> int:
        n = count_instructions(payload)
        if n > self.config.max_instructions:
            raise InstructionBudgetError(
                f"Composed instruction count is {n}; max is {self.config.max_instructions}."
            )
        return n

    def run(
        self,
        *,
        query: str,
        metadata: str,
        bindings: dict[str, Any],
        workspace: Path | None,
        mode: str,
        cleanup_workspace: bool = False,
    ) -> Completion:
        payload = self.compose_payload(query)
        self.check_instruction_budget(payload)
        hist = [
            Message("system", payload.system_prompt),
            Message("user", metadata + "\n\nUser query:\n" + query),
        ]
        static_tokens = count_tokens(hist)
        if static_tokens >= 100_000:
            raise PromptBudgetError(
                "Static system+domain prompt is >= 100k tokens; refuse to start."
            )
        env = self.env_factory(
            bindings=bindings,
            handler=self.handler,
            mode=mode,
            workspace=workspace,
            config=self.config,
        )
        last_code: str | None = None
        identical = 0
        consec_err = 0
        answer: str | None = None
        try:
            for i in range(self.config.max_iterations):
                self.budget.check()
                n_tok, n_inst = assert_sendable(
                    hist,
                    payload,
                    max_prompt_tokens=self.config.max_prompt_tokens,
                    max_instructions=self.config.max_instructions,
                    as_parent=True,
                )
                if self.config.verbose:
                    print(
                        f"--- iteration {i} depth={self.depth} tokens={n_tok} inst={n_inst} ---",
                        file=sys.stderr,
                    )
                t0 = time.perf_counter()
                lm = self.client.complete(hist, model=self.config.root_model)
                cost = self.budget.record(lm)
                self.budget.iterations += 1
                self.logger.event(
                    kind="root_lm",
                    iteration=i,
                    depth=self.depth,
                    model=self.config.root_model,
                    prompt_tokens=n_tok,
                    instruction_count=n_inst,
                    completion_tokens=lm.completion_tokens,
                    latency_s=time.perf_counter() - t0,
                    cost_usd=cost,
                )
                code = extract_repl_code(lm.text)
                hist.append(Message("assistant", lm.text))
                if code is None:
                    consec_err += 1
                    note = (
                        "No ```repl``` block found. Write Python inside a fenced ```repl block."
                    )
                    hist.append(Message("user", note))
                    self.logger.event(kind="parse_error", iteration=i, depth=self.depth)
                    if consec_err >= self.config.max_consecutive_errors:
                        raise ReplErrorsExhausted("Consecutive REPL parse errors exhausted.")
                    continue
                if last_code is not None and code.strip() == last_code.strip():
                    identical += 1
                    if identical >= 2:
                        raise ReplErrorsExhausted("Repeated identical code; aborting stall.")
                else:
                    identical = 0
                last_code = code
                if self.config.verbose:
                    print(code, file=sys.stderr)
                obs = env.execute(code)
                formatted = format_observation(obs, self.config.max_observation_chars)
                self.logger.event(
                    kind="repl",
                    iteration=i,
                    depth=self.depth,
                    code=code[:4000],
                    stdout=formatted[:4000],
                    error=obs.error,
                    prompt_tokens=n_tok,
                    instruction_count=n_inst,
                )
                if self.config.verbose:
                    print(formatted, file=sys.stderr)
                if obs.error:
                    consec_err += 1
                    if consec_err >= self.config.max_consecutive_errors:
                        raise ReplErrorsExhausted("Consecutive REPL errors exhausted.")
                else:
                    consec_err = 0
                if obs.final is not None:
                    answer = obs.final
                    break
                hist.append(Message("user", formatted))
            else:
                raise BudgetExhaustedError(
                    f"max_iterations ({self.config.max_iterations}) exhausted without FINAL_VAR."
                )
        finally:
            env.close()
            if cleanup_workspace and workspace is not None:
                import shutil

                shutil.rmtree(workspace, ignore_errors=True)

        usage = Usage(
            prompt_tokens=self.budget.prompt_tokens,
            completion_tokens=self.budget.completion_tokens,
            cost_usd=self.budget.spent_usd,
            iterations=self.budget.iterations,
            subcalls=self.budget.subcalls,
        )
        assert answer is not None
        if self.depth == 0:
            self.logger.finish(answer, usage)
        return Completion(response=answer, usage=usage, trajectory=self.logger.dir)

    def leaf_complete(self, prompt: str, model: str | None = None) -> str:
        try:
            self.budget.check()
        except BudgetExhaustedError as e:
            return f"Error: {e}"
        model = model or self.config.leaf_model
        messages = [
            Message("system", leaf_system_prompt()),
            Message("user", prompt),
        ]
        payload = PromptPayload(
            system_prompt=leaf_system_prompt(),
            user_query="leaf-task",
        )
        try:
            n_tok, n_inst = assert_sendable(
                messages,
                payload,
                max_prompt_tokens=self.config.max_prompt_tokens,
                max_instructions=self.config.max_instructions,
                as_parent=False,
            )
        except (PromptBudgetError, InstructionBudgetError) as e:
            text = str(e)
            return text if text.startswith("Error:") else f"Error: {text}"
        t0 = time.perf_counter()
        try:
            resp = self.client.complete(messages, model=model)
        except Exception as e:
            return f"Error: {e}"
        with self._budget_lock:
            cost = self.budget.record(resp)
            self.budget.subcalls += 1
        self.logger.event(
            kind="llm_query",
            depth=self.depth,
            model=model,
            prompt_tokens=n_tok,
            instruction_count=n_inst,
            completion_tokens=resp.completion_tokens,
            latency_s=time.perf_counter() - t0,
            cost_usd=cost,
        )
        return resp.text

    def child_rlm(self, prompt: str, model: str | None = None) -> str:
        try:
            self.budget.check()
        except BudgetExhaustedError as e:
            return f"Error: {e}"
        child_depth = self.depth + 1
        if child_depth > self.config.max_depth:
            n = count_tokens([Message("user", prompt)])
            if n >= 100_000 or n > self.config.max_prompt_tokens:
                return (
                    f"Error: depth cap; slice smaller at this level "
                    f"(prompt is {n} tokens; max is {self.config.max_prompt_tokens})."
                )
            return self.leaf_complete(prompt, model=model)
        child_budget = self.budget.inherit()
        child_config = self.config
        from dataclasses import replace

        child_config = replace(
            self.config,
            max_budget_usd=child_budget.max_usd,
            max_timeout_s=child_budget.max_timeout_s,
            extra_instructions=self.config.extra_instructions,
            verbose=self.config.verbose,
        )
        child = Runtime(
            child_config,
            self.client,
            self.env_factory,
            self.logger,
            depth=child_depth,
            budget=child_budget,
            domain=None,
        )
        meta = string_metadata(prompt)
        bindings = {"query": CHILD_QUERY, "context": prompt}
        workspace, cleanup = workspace_for_string(prompt)
        try:
            result = child.run(
                query=CHILD_QUERY,
                metadata=meta,
                bindings=bindings,
                workspace=workspace,
                mode="string",
                cleanup_workspace=cleanup,
            )
        except Exception as e:
            return f"Error: {e}"
        with self._budget_lock:
            self.budget.spent_usd += child.budget.spent_usd
            self.budget.prompt_tokens += child.budget.prompt_tokens
            self.budget.completion_tokens += child.budget.completion_tokens
            self.budget.subcalls += 1 + child.budget.subcalls
            self.budget.iterations += child.budget.iterations
        self.logger.event(
            kind="rlm_query",
            depth=self.depth,
            child_depth=child_depth,
            answer_n_chars=len(result.response),
        )
        return result.response

    def batched(self, fn, prompts: list[str], model: str | None) -> list[str]:
        results: list[str | None] = [None] * len(prompts)
        workers = min(self.config.max_concurrent_subcalls, max(1, len(prompts)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(fn, p, model): i for i, p in enumerate(prompts)}
            for fut in as_completed(futs):
                i = futs[fut]
                try:
                    results[i] = fut.result()
                except Exception as e:
                    results[i] = f"Error: {e}"
        return [r if r is not None else "Error: missing result" for r in results]


def string_metadata(context: str, prefix_chars: int = 200) -> str:
    digest = sha256_text(context)
    prefix = context[:prefix_chars]
    return (
        f"Context bound as `context` ({len(context)} chars, sha256={digest[:16]}).\n"
        f"Short prefix: {prefix!r}\n"
        "Access via slices, regex, and llm_query. Do not print the full context.\n"
    )


def workspace_for_string(context: str) -> tuple[Path, bool]:
    d = Path(tempfile.mkdtemp(prefix="rlm-ctx-"))
    (d / "context.txt").write_text(context, encoding="utf-8")
    return d, True


def query_sha(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8")).hexdigest()
