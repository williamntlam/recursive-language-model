"""CLI: rlm ask | rlm research | rlm complete | rlm report. No --env local. No --api-key."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rlm.api import RLM
from rlm.config import HARD_MAX_INSTRUCTIONS, HARD_MAX_PROMPT_TOKENS
from rlm.core.architecture import architecture_names
from rlm.core.planner import planner_instruction_count, planner_messages
from rlm.core.prompt_guard import count_tokens
from rlm.core.runtime import string_metadata
from rlm.domains.corpus import corpus_manifest, load_corpus
from rlm.domains.repo import load_repo, repo_manifest
from rlm.domains.scope import build_corpus_scope, build_repo_scope
from rlm.envfile import load_dotenv
from rlm.errors import (
    BudgetExhaustedError,
    ConfigError,
    InstructionBudgetError,
    PromptBudgetError,
    ReplErrorsExhausted,
    StartupError,
)
from rlm.logging.html import resolve_run_dir, write_report
from rlm.logging.trace import index_runs


def _build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root-model", dest="root_model")
    common.add_argument("--leaf-model", dest="leaf_model")
    common.add_argument("--max-depth", dest="max_depth", type=int)
    common.add_argument("--max-iterations", dest="max_iterations", type=int)
    common.add_argument("--max-prompt-tokens", dest="max_prompt_tokens", type=int)
    common.add_argument("--max-instructions", dest="max_instructions", type=int)
    common.add_argument("--max-budget", dest="max_budget_usd", type=float)
    common.add_argument("--timeout", dest="max_timeout_s", type=float)
    common.add_argument("--cell-timeout", dest="cell_timeout_s", type=float)
    common.add_argument("--log-dir", dest="log_dir")
    common.add_argument("--verbose", action="store_true", default=None)
    common.add_argument("--trace-capture", choices=("metadata", "content"))
    common.add_argument("--config", dest="config_path")
    common.add_argument("--dry-run", action="store_true")
    common.add_argument("--planner-enabled", action="store_true", default=None)
    common.add_argument("--architecture", choices=architecture_names())

    p = argparse.ArgumentParser(
        prog="rlm",
        description="Recursive Language Model: long context via a Docker REPL.",
        parents=[common],
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    ask = sub.add_parser("ask", help="Explore a local repository.", parents=[common])
    ask.add_argument("path")

    research = sub.add_parser("research", help="Synthesize a document corpus.", parents=[common])
    research.add_argument("path")

    complete = sub.add_parser("complete", help="Generic string context.", parents=[common])
    complete.add_argument("--context-file", required=True)

    report = sub.add_parser(
        "report",
        help="Write a static HTML view of a trajectory directory.",
    )
    report.add_argument(
        "path",
        nargs="?",
        default=".rlm/logs",
        help="Run directory, events.jsonl, or log parent (latest run). Default: .rlm/logs",
    )
    traces = sub.add_parser("traces", help="Print a compact local trace index.")
    traces.add_argument("path", nargs="?", default=".rlm/logs")

    return p


def _split_argv(argv: list[str]) -> tuple[list[str], str]:
    if "--" in argv:
        i = argv.index("--")
        return argv[:i], " ".join(argv[i + 1 :]).strip()
    return argv, ""


def _print_usage(out) -> None:
    u = out.usage
    cost = f"${u.cost_usd:.4f}" if u.cost_usd is not None else "$?"
    print(
        f"# tokens={u.prompt_tokens}+{u.completion_tokens} cost={cost} "
        f"iters={u.iterations} subcalls={u.subcalls} log={out.trajectory} "
        f"html={out.trajectory / 'report.html'}",
        file=sys.stderr,
    )


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    argv = list(sys.argv[1:] if argv is None else argv)
    head, query = _split_argv(argv)
    parser = _build_parser()
    try:
        args = parser.parse_args(head)
    except SystemExit as e:
        code = e.code if isinstance(e.code, int) else 4
        return code if code != 2 else 4  # argparse's 2 → our 4 (user error)

    if args.cmd == "report":
        try:
            html = write_report(resolve_run_dir(args.path))
            print(html)
            return 0
        except FileNotFoundError as e:
            print(e, file=sys.stderr)
            return 4
    if args.cmd == "traces":
        try:
            print(__import__("json").dumps(index_runs(args.path), indent=2, sort_keys=True))
            return 0
        except (FileNotFoundError, ValueError, __import__("json").JSONDecodeError) as e:
            print(e, file=sys.stderr)
            return 4

    if not query:
        print(
            'Pass the query after --  (example: rlm ask ./repo -- "your question")',
            file=sys.stderr,
        )
        return 4

    try:
        if args.max_prompt_tokens is not None and args.max_prompt_tokens > HARD_MAX_PROMPT_TOKENS:
            raise ConfigError(f"--max-prompt-tokens cannot exceed {HARD_MAX_PROMPT_TOKENS}")
        if args.max_instructions is not None and args.max_instructions > HARD_MAX_INSTRUCTIONS:
            raise ConfigError(f"--max-instructions cannot exceed {HARD_MAX_INSTRUCTIONS}")
        rlm = RLM(
            config_path=args.config_path,
            root_model=args.root_model,
            leaf_model=args.leaf_model,
            max_depth=args.max_depth,
            max_iterations=args.max_iterations,
            max_prompt_tokens=args.max_prompt_tokens,
            max_instructions=args.max_instructions,
            max_budget_usd=args.max_budget_usd,
            max_timeout_s=args.max_timeout_s,
            cell_timeout_s=args.cell_timeout_s,
            log_dir=args.log_dir,
            verbose=True if args.verbose else None,
            trace_capture=args.trace_capture,
            architecture=args.architecture,
            planner_enabled=args.planner_enabled,
        )
        if args.cmd == "ask":
            repo = load_repo(args.path)
            metadata = repo_manifest(repo)
            domain = "repo"
            if args.dry_run:
                output = rlm.dry_run(query, metadata, domain=domain)
                if rlm.config.planner_enabled:
                    scope = build_repo_scope(repo, query)
                    planner = planner_messages(query, scope, {})
                    output += (
                        "\nplanner_enabled=true "
                        f"schema_version={scope.version} "
                        f"manifest_records={len(scope.records)} truncated={scope.truncated} "
                        f"planner_prompt_tokens={count_tokens(planner)} "
                        f"planner_instruction_count={planner_instruction_count(planner)}\n"
                    )
                print(output)
                return 0
            out = rlm.ask_repo(args.path, query)
        elif args.cmd == "research":
            corpus = load_corpus(args.path)
            metadata = corpus_manifest(corpus)
            domain = "research"
            if args.dry_run:
                output = rlm.dry_run(query, metadata, domain=domain)
                if rlm.config.planner_enabled:
                    scope = build_corpus_scope(corpus, query)
                    planner = planner_messages(query, scope, {})
                    output += (
                        "\nplanner_enabled=true "
                        f"schema_version={scope.version} "
                        f"manifest_records={len(scope.records)} truncated={scope.truncated} "
                        f"planner_prompt_tokens={count_tokens(planner)} "
                        f"planner_instruction_count={planner_instruction_count(planner)}\n"
                    )
                print(output)
                return 0
            out = rlm.research(args.path, query)
        else:
            context = Path(args.context_file).read_text(encoding="utf-8")
            metadata = string_metadata(context)
            if args.dry_run:
                print(rlm.dry_run(query, metadata, domain=None))
                return 0
            out = rlm.completion(query, context)
        print(out.response)
        _print_usage(out)
        return 0
    except (PromptBudgetError, BudgetExhaustedError) as e:
        print(e, file=sys.stderr)
        return 2
    except ReplErrorsExhausted as e:
        print(e, file=sys.stderr)
        return 3
    except (ConfigError, InstructionBudgetError, StartupError, FileNotFoundError) as e:
        print(e, file=sys.stderr)
        return 4


if __name__ == "__main__":
    raise SystemExit(main())
