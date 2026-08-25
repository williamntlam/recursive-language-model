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
from rlm.core.history import (
    assistant_cell_message,
    compact_parent_hist,
    format_observation,
    observation_nudge,
    repl_error_hint,
    sha256_text,
)
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
CELL_LOG_MAX_CHARS = 100_000


class RuntimeHandler(SubcallHandler):
    def __init__(self, runtime: Runtime) -> None:
        self.runtime = runtime
        self._cell_span_id: str | None = None

    def set_callback_context(self, cell_span_id: str | None) -> None:
        self._cell_span_id = cell_span_id

    def llm_query(self, prompt: str, model: str | None = None) -> str:
        return self.runtime.callback("llm_query", prompt, model, self._cell_span_id)

    def llm_query_batched(self, prompts: list[str], model: str | None = None) -> list[str]:
        return self.runtime.callback_batch("llm_query_batched", prompts, model, self._cell_span_id)

    def rlm_query(self, prompt: str, model: str | None = None) -> str:
        return self.runtime.callback("rlm_query", prompt, model, self._cell_span_id)

    def rlm_query_batched(self, prompts: list[str], model: str | None = None) -> list[str]:
        return self.runtime.callback_batch("rlm_query_batched", prompts, model, self._cell_span_id)


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
        trace_parent_span_id: str | None = None,
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
        self.mode = "string"
        self._workspace: Path | None = None
        self._bindings: dict[str, Any] = {}
        self._metadata = ""
        self.trace_parent_span_id = trace_parent_span_id
        self.run_span_id: str | None = None
        self.run_started: float | None = None

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
        # The logger creates the root span before environment construction. Nested
        # RLMs receive a run span under the invoking callback.
        if self.depth == 0:
            self.run_span_id = self.logger.root_span_id
            self.run_started = self.logger.root_started
        else:
            self.run_started = time.perf_counter()
            self.run_span_id = self.logger.trace.start(
                "rlm.run",
                "run",
                parent_span_id=self.trace_parent_span_id,
                depth=self.depth,
            )
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
        self.mode = mode
        self._workspace = workspace
        self._bindings = bindings
        self._metadata = metadata
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
        abort: BaseException | None = None
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
                model_started = time.perf_counter()
                model_span = self.logger.trace.start(
                    "root.complete",
                    "model",
                    parent_span_id=self.run_span_id,
                    depth=self.depth,
                    model=self.config.root_model,
                    input_tokens=n_tok,
                    instruction_count=n_inst,
                )
                try:
                    lm = self.client.complete(hist, model=self.config.root_model)
                except Exception as e:
                    self.logger.trace.end(
                        model_span,
                        "root.complete",
                        "model",
                        depth=self.depth,
                        status="error",
                        started=model_started,
                        error_type=type(e).__name__,
                    )
                    raise
                cost = self.budget.record(lm)
                self.budget.iterations += 1
                root_request = "\n".join(m.content for m in hist)
                self.logger.trace.end(
                    model_span,
                    "root.complete",
                    "model",
                    depth=self.depth,
                    status="ok",
                    started=model_started,
                    input_tokens=n_tok,
                    output_tokens=lm.completion_tokens,
                    cost_usd=cost,
                    request_digest=sha256_text(root_request),
                    response_digest=sha256_text(lm.text or ""),
                    response_n_chars=len(lm.text or ""),
                    prompt_artifact=self.logger.capture_content("root_request", root_request),
                    output_artifact=self.logger.capture_content("root_output", lm.text or ""),
                )
                self.logger.event(
                    kind="root_lm",
                    iteration=i,
                    depth=self.depth,
                    model=self.config.root_model,
                    prompt_tokens=n_tok,
                    instruction_count=n_inst,
                    completion_tokens=lm.completion_tokens,
                    latency_s=time.perf_counter() - model_started,
                    cost_usd=cost,
                    text_n_chars=len(lm.text or ""),
                )
                code = extract_repl_code(lm.text)
                if code is None:
                    hist.append(Message("assistant", lm.text))
                    consec_err += 1
                    note = (
                        "No executable code fence found. Write Python inside a "
                        "fenced ```repl (or ```python) block. Do not answer in prose; "
                        "keep findings in variables and finish with FINAL / FINAL_VAR. "
                        "To read a file, grep/ast it here, or repo.ask a tight span."
                    )
                    hist.append(Message("user", note))
                    preview = (lm.text or "")[:4000]
                    self.logger.trace.event(
                        "parse",
                        "runtime",
                        parent_span_id=self.run_span_id,
                        depth=self.depth,
                        status="error",
                    )
                    self.logger.event(
                        kind="parse_error",
                        iteration=i,
                        depth=self.depth,
                        text_n_chars=len(lm.text or ""),
                        text_preview=preview,
                    )
                    if self.config.verbose:
                        shown = preview or "(empty model output)"
                        print(f"parse_error: {shown}", file=sys.stderr)
                    if consec_err >= self.config.max_consecutive_errors:
                        raise ReplErrorsExhausted("Consecutive REPL parse errors exhausted.")
                    compact_parent_hist(hist)
                    continue
                hist.append(assistant_cell_message(code))
                if last_code is not None and code.strip() == last_code.strip():
                    identical += 1
                    if identical >= 2:
                        raise ReplErrorsExhausted("Repeated identical code; aborting stall.")
                else:
                    identical = 0
                last_code = code
                if self.config.verbose:
                    print(code, file=sys.stderr)
                cell_started = time.perf_counter()
                cell_span = self.logger.trace.start(
                    "repl.cell",
                    "repl",
                    parent_span_id=self.run_span_id,
                    depth=self.depth,
                    code_digest=sha256_text(code),
                    code_n_chars=len(code),
                    iteration=i,
                )
                try:
                    self.handler.set_callback_context(cell_span)
                    obs = env.execute(code, trace_cell_id=cell_span)
                except Exception as e:
                    self.logger.trace.end(
                        cell_span,
                        "repl.cell",
                        "repl",
                        depth=self.depth,
                        status="error",
                        started=cell_started,
                        error_type=type(e).__name__,
                    )
                    raise
                self._record_tool_events(obs.tool_events, cell_span)
                self.logger.trace.end(
                    cell_span,
                    "repl.cell",
                    "repl",
                    depth=self.depth,
                    status="error" if obs.error else "ok",
                    started=cell_started,
                    stdout_n_chars=obs.total_stdout_len,
                    stderr_n_chars=obs.total_stderr_len,
                    output_digest=obs.sha256,
                    final_present=obs.final is not None,
                    error_type="ReplError" if obs.error else None,
                )
                formatted = format_observation(obs, self.config.max_observation_chars)
                hint = repl_error_hint(code, obs.error)
                if hint:
                    formatted = formatted.rstrip() + "\n" + hint + "\n"
                probe = list(hist) + [Message("user", formatted)]
                nudge = observation_nudge(count_tokens(probe))
                if nudge:
                    formatted = formatted + "\n\n" + nudge
                stderr_text = (obs.stderr or "")[:4000]
                if hint:
                    stderr_text = (stderr_text.rstrip() + "\n" + hint)[:4000]
                self.logger.event(
                    kind="repl",
                    iteration=i,
                    depth=self.depth,
                    code=code[:CELL_LOG_MAX_CHARS],
                    stdout=formatted[:4000],
                    stderr=stderr_text,
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
                compact_parent_hist(hist)
            else:
                raise BudgetExhaustedError(
                    f"max_iterations ({self.config.max_iterations}) exhausted without FINAL_VAR."
                )
        except BaseException as e:
            abort = e
            self.logger.abort_trace(e, depth=self.depth)
            raise
        finally:
            env.close()
            if cleanup_workspace and workspace is not None:
                import shutil

                shutil.rmtree(workspace, ignore_errors=True)
            if abort is not None:
                try:
                    self.logger.record_stderr(
                        f"{type(abort).__name__}: {abort}",
                        kind="abort",
                        depth=self.depth,
                    )
                except OSError:
                    pass
            if self.depth == 0:
                try:
                    self.logger.write_html()
                except OSError:
                    pass

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
        elif self.run_span_id and self.run_started is not None:
            self.logger.trace.end(
                self.run_span_id,
                "rlm.run",
                "run",
                depth=self.depth,
                status="ok",
                started=self.run_started,
            )
        return Completion(response=answer, usage=usage, trajectory=self.logger.dir)

    def callback(
        self,
        name: str,
        prompt: str,
        model: str | None = None,
        cell_span_id: str | None = None,
    ) -> str:
        parent = cell_span_id or self.run_span_id
        started = time.perf_counter()
        span = self.logger.trace.start(
            name,
            "callback",
            parent_span_id=parent,
            depth=self.depth,
            requested_model=model,
            prompt_n_chars=len(prompt),
            prompt_digest=sha256_text(prompt),
        )
        try:
            value = (
                self.leaf_complete(prompt, model=model, parent_span_id=span)
                if name == "llm_query"
                else self.child_rlm(prompt, model=model, parent_span_id=span)
            )
        except Exception as e:
            self.logger.trace.end(
                span,
                name,
                "callback",
                depth=self.depth,
                status="error",
                started=started,
                error_type=type(e).__name__,
            )
            raise
        self.logger.trace.end(
            span,
            name,
            "callback",
            depth=self.depth,
            status="error" if value.startswith("Error:") else "ok",
            started=started,
            result_n_chars=len(value),
            result_digest=sha256_text(value),
        )
        return value

    def _record_tool_events(self, events: list[dict[str, Any]], cell_span_id: str) -> None:
        """Translate the bounded REPL-side buffer into host-ordered tool spans."""
        pending: dict[str, tuple[str, float]] = {}
        for item in events:
            name = str(item.get("name") or "tool")
            if item.get("event") == "start":
                pending[name] = (
                    self.logger.trace.start(
                        name,
                        "tool",
                        parent_span_id=cell_span_id,
                        depth=self.depth,
                        arg_count=item.get("arg_count"),
                    ),
                    time.perf_counter(),
                )
            elif item.get("event") == "end":
                existing = pending.pop(name, None)
                if existing is None:
                    span = self.logger.trace.start(
                        name, "tool", parent_span_id=cell_span_id, depth=self.depth
                    )
                    started = time.perf_counter()
                else:
                    span, started = existing
                duration_ms = item.get("duration_ms")
                if isinstance(duration_ms, (int, float)) and duration_ms >= 0:
                    started = time.perf_counter() - (duration_ms / 1000)
                self.logger.trace.end(
                    span,
                    name,
                    "tool",
                    depth=self.depth,
                    status=str(item.get("status") or "error"),
                    started=started,
                    result_count=item.get("result_count"),
                    error_type=item.get("error_type"),
                )

    def callback_batch(
        self,
        name: str,
        prompts: list[str],
        model: str | None = None,
        cell_span_id: str | None = None,
    ) -> list[str]:
        started = time.perf_counter()
        callback = self.logger.trace.start(
            name,
            "callback",
            parent_span_id=cell_span_id or self.run_span_id,
            depth=self.depth,
            requested_model=model,
            prompt_count=len(prompts),
        )
        batch = self.logger.trace.start(
            name, "batch", parent_span_id=callback, depth=self.depth, slot_count=len(prompts)
        )
        fn = self.leaf_complete if name == "llm_query_batched" else self.child_rlm
        results = self.batched(fn, prompts, model, parent_span_id=batch)
        self.logger.trace.end(
            batch,
            name,
            "batch",
            depth=self.depth,
            status="ok",
            started=started,
            slot_count=len(results),
            error_slots=sum(x.startswith("Error:") for x in results),
        )
        self.logger.trace.end(
            callback,
            name,
            "callback",
            depth=self.depth,
            status="ok",
            started=started,
            result_count=len(results),
        )
        return results

    def leaf_complete(
        self, prompt: str, model: str | None = None, *, parent_span_id: str | None = None
    ) -> str:
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
        span = self.logger.trace.start(
            "leaf.complete",
            "model",
            parent_span_id=parent_span_id or self.run_span_id,
            depth=self.depth,
            model=model,
            input_tokens=n_tok,
            instruction_count=n_inst,
            request_digest=sha256_text(prompt),
            request_n_chars=len(prompt),
        )
        try:
            resp = self.client.complete(messages, model=model)
        except Exception as e:
            self.logger.trace.end(
                span,
                "leaf.complete",
                "model",
                depth=self.depth,
                status="error",
                started=t0,
                error_type=type(e).__name__,
            )
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
        self.logger.trace.end(
            span,
            "leaf.complete",
            "model",
            depth=self.depth,
            status="ok",
            started=t0,
            input_tokens=n_tok,
            output_tokens=resp.completion_tokens,
            cost_usd=cost,
            response_digest=sha256_text(resp.text or ""),
            response_n_chars=len(resp.text or ""),
            prompt_artifact=self.logger.capture_content("leaf_request", prompt),
            output_artifact=self.logger.capture_content("leaf_output", resp.text or ""),
        )
        return resp.text

    def child_rlm(
        self, prompt: str, model: str | None = None, *, parent_span_id: str | None = None
    ) -> str:
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
        from dataclasses import replace

        child_config = replace(
            self.config,
            max_budget_usd=child_budget.max_usd,
            max_timeout_s=child_budget.max_timeout_s,
            extra_instructions=self.config.extra_instructions,
            verbose=self.config.verbose,
        )
        query, metadata, bindings, workspace, mode, cleanup, domain = self._child_launch(prompt)
        child = Runtime(
            child_config,
            self.client,
            self.env_factory,
            self.logger,
            depth=child_depth,
            budget=child_budget,
            domain=domain,
            trace_parent_span_id=parent_span_id or self.run_span_id,
        )
        try:
            result = child.run(
                query=query,
                metadata=metadata,
                bindings=bindings,
                workspace=workspace,
                mode=mode,
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

    def _child_launch(
        self, prompt: str
    ) -> tuple[str, str, dict[str, Any], Path, str, bool, str | None]:
        """Repo/corpus children inherit the workspace; string children bind `context`."""
        mode = self.mode or "string"
        if mode == "repo" and self._workspace is not None:
            repo = self._clone_repo()
            bindings: dict[str, Any] = {
                "query": prompt,
                "repo": repo,
                "manifest": self._bindings.get("manifest") or "",
            }
            metadata = (self._metadata or "") + (
                "\nYou are a nested RLM with the same repository. "
                "Do only the subtask. Grep/ast here; llm_query tight slices; "
                "recurse only if still too large. FINAL a short cited answer.\n"
            )
            return prompt, metadata, bindings, self._workspace, "repo", False, "repo"
        if mode == "research" and self._workspace is not None:
            corpus = self._clone_corpus()
            bindings = {
                "query": prompt,
                "corpus": corpus,
                "catalog": self._bindings.get("catalog"),
            }
            metadata = (self._metadata or "") + (
                "\nYou are a nested RLM with the same corpus. "
                "Do only the subtask. Search/slice here; llm_query tight spans; "
                "recurse only if still too large. FINAL a short cited answer.\n"
            )
            return prompt, metadata, bindings, self._workspace, "research", False, "research"
        workspace, cleanup = workspace_for_string(prompt)
        bindings = {"query": CHILD_QUERY, "context": prompt}
        return CHILD_QUERY, string_metadata(prompt), bindings, workspace, "string", cleanup, None

    def _clone_repo(self) -> Any:
        repo = self._bindings.get("repo")
        if repo is None:
            from rlm.domains.repo import Repo

            return Repo(self._workspace)
        return type(repo)(repo.root, ignore=getattr(repo, "ignore", ()))

    def _clone_corpus(self) -> Any:
        corpus = self._bindings.get("corpus")
        if corpus is None:
            from rlm.domains.corpus import load_corpus

            return load_corpus(self._workspace)
        from rlm.domains.corpus import Corpus

        return Corpus(list(corpus.docs))

    def batched(
        self, fn, prompts: list[str], model: str | None, *, parent_span_id: str | None = None
    ) -> list[str]:
        results: list[str | None] = [None] * len(prompts)
        workers = min(self.config.max_concurrent_subcalls, max(1, len(prompts)))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {
                pool.submit(fn, p, model, parent_span_id=parent_span_id): i
                for i, p in enumerate(prompts)
            }
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
