"""Deterministic, source-free candidate manifests for planned research."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from fnmatch import fnmatch
from typing import Any

from rlm.core.history import ASK_LEAF_CHARS
from rlm.domains.corpus import Corpus
from rlm.domains.repo import Repo, _looks_text

SCOPE_SCHEMA_VERSION = 1
DEFAULT_MAX_RECORDS = 256
DEFAULT_MAX_PATHS = 512
DEFAULT_MAX_AST_NODES = 1_024
DEFAULT_MAX_METADATA_BYTES = 256_000


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _digest(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ScopeRecord:
    id: str
    target: dict[str, Any]
    n_chars: int
    route: str
    signals: tuple[str, ...] = ()
    kind: str | None = None
    qualname: str | None = None

    def public_dict(self) -> dict[str, Any]:
        # target identifiers are intentionally present in the in-memory manifest:
        # they are what lets the runtime resolve a plan without planner-supplied paths.
        return {k: v for k, v in asdict(self).items() if v is not None and v != ()}


@dataclass(frozen=True)
class ScopeManifest:
    version: int
    domain: str
    query_digest: str
    records: tuple[ScopeRecord, ...]
    counts: dict[str, int]
    truncated: dict[str, bool]
    caps: dict[str, int]
    digest: str

    def canonical_json(self) -> str:
        return _canonical(self.to_dict(include_digest=False))

    def to_dict(self, *, include_digest: bool = True) -> dict[str, Any]:
        result = {
            "version": self.version,
            "domain": self.domain,
            "query_digest": self.query_digest,
            "records": [record.public_dict() for record in self.records],
            "counts": self.counts,
            "truncated": self.truncated,
            "caps": self.caps,
        }
        if include_digest:
            result["digest"] = self.digest
        return result

    def planner_dict(self) -> dict[str, Any]:
        """The compact, source-free view supplied to a planner."""
        return self.to_dict()


def _manifest(
    domain: str,
    query: str,
    records: list[ScopeRecord],
    *,
    paths: int,
    ast_nodes: int,
    truncated: dict[str, bool],
    caps: dict[str, int],
) -> ScopeManifest:
    # Cap metadata after record construction, so a caller gets a valid prefix.
    kept: list[ScopeRecord] = []
    for record in records:
        candidate = kept + [record]
        trial = {"records": [r.public_dict() for r in candidate]}
        if len(_canonical(trial).encode()) > caps["metadata_bytes"]:
            truncated["metadata_bytes"] = True
            break
        kept.append(record)
    body = {
        "version": SCOPE_SCHEMA_VERSION,
        "domain": domain,
        "query_digest": _digest(query),
        "records": [r.public_dict() for r in kept],
        "counts": {"records": len(kept), "paths": paths, "ast_nodes": ast_nodes},
        "truncated": truncated,
        "caps": caps,
    }
    return ScopeManifest(
        version=SCOPE_SCHEMA_VERSION,
        domain=domain,
        query_digest=_digest(query),
        records=tuple(kept),
        counts=body["counts"],
        truncated=truncated,
        caps=caps,
        digest=_digest(body),
    )


def build_repo_scope(
    repo: Repo,
    query: str,
    *,
    path_prefixes: Iterable[str] = (),
    glob_patterns: Iterable[str] = (),
    name_patterns: Iterable[str] = (),
    class_name_patterns: Iterable[str] = (),
    function_name_patterns: Iterable[str] = (),
    ast_predicates: Iterable[str] = (),
    max_records: int = DEFAULT_MAX_RECORDS,
    max_paths: int = DEFAULT_MAX_PATHS,
    max_ast_nodes: int = DEFAULT_MAX_AST_NODES,
    max_metadata_bytes: int = DEFAULT_MAX_METADATA_BYTES,
) -> ScopeManifest:
    """Build stable declaration/file targets without copying any file text out."""
    caps = {
        "records": max_records,
        "paths": max_paths,
        "ast_nodes": max_ast_nodes,
        "metadata_bytes": max_metadata_bytes,
    }
    prefixes, globs, names, class_names, function_names, predicates = (
        tuple(path_prefixes),
        tuple(glob_patterns),
        tuple(name_patterns),
        tuple(class_name_patterns),
        tuple(function_name_patterns),
        tuple(ast_predicates),
    )
    records: list[ScopeRecord] = []
    paths = ast_nodes = 0
    truncated = {"records": False, "paths": False, "ast_nodes": False, "metadata_bytes": False}
    for file in sorted(repo._walk_files(), key=repo._rel):  # noqa: SLF001 - domain inventory
        if paths >= max_paths:
            truncated["paths"] = True
            break
        if not _looks_text(file):
            continue
        path = repo._rel(file)  # noqa: SLF001
        if prefixes and not any(
            path.startswith(p.rstrip("/") + "/") or path == p.rstrip("/") for p in prefixes
        ):
            continue
        if globs and not any(
            fnmatch(path, pattern) or fnmatch(file.name, pattern) for pattern in globs
        ):
            continue
        paths += 1
        try:
            text = file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        declarations: list[tuple[str, str, int, int]] = []
        if file.suffix.lower() in {".py", ".pyi"}:
            try:
                tree = ast.parse(text)

                def visit(node: ast.AST, parents: tuple[str, ...] = ()) -> None:
                    nonlocal ast_nodes
                    if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
                        if ast_nodes >= max_ast_nodes:
                            truncated["ast_nodes"] = True
                            return
                        ast_nodes += 1
                        kind = type(node).__name__
                        qualname = ".".join((*parents, node.name))
                        declarations.append(
                            (kind, qualname, node.lineno, getattr(node, "end_lineno", node.lineno))
                        )
                        parents = (*parents, node.name)
                    for child in ast.iter_child_nodes(node):
                        visit(child, parents)

                visit(tree)
            except SyntaxError:
                pass
        for kind, qualname, start, end in declarations:
            short_name = qualname.rsplit(".", 1)[-1]
            is_class = kind == "ClassDef"
            type_patterns = class_names if is_class else function_names
            if (
                is_class and not class_names and function_names and not names and not predicates
            ) or (
                not is_class and class_names and not function_names and not names and not predicates
            ):
                continue
            if (names or type_patterns or predicates) and not any(
                re.search(pattern, qualname) for pattern in (*names, *type_patterns, *predicates)
            ):
                continue
            n_chars = sum(len(line) + 1 for line in text.splitlines()[start - 1 : end])
            signals = tuple(sorted({f"name:{short_name}", f"kind:{kind}"}))
            records.append(
                ScopeRecord(
                    f"r-{len(records) + 1:04d}",
                    {"path": path, "start": start, "end": end},
                    n_chars,
                    "fit" if n_chars <= ASK_LEAF_CHARS else "child",
                    signals,
                    kind,
                    qualname,
                )
            )
            if len(records) >= max_records:
                truncated["records"] = True
                break
        if len(records) >= max_records:
            break
        # Files are valid targets too when no declaration filter is requested.
        if not (names or class_names or function_names or predicates) and not declarations:
            if len(records) >= max_records:
                truncated["records"] = True
                break
            records.append(
                ScopeRecord(
                    f"r-{len(records) + 1:04d}",
                    {"path": path, "start": None, "end": None},
                    len(text),
                    "fit" if len(text) <= ASK_LEAF_CHARS else "child",
                    ("file",),
                    "file",
                    path,
                )
            )
    return _manifest(
        "repo", query, records, paths=paths, ast_nodes=ast_nodes, truncated=truncated, caps=caps
    )


def build_corpus_scope(
    corpus: Corpus,
    query: str,
    *,
    patterns: Iterable[str] = (),
    max_records: int = DEFAULT_MAX_RECORDS,
    max_paths: int = DEFAULT_MAX_PATHS,
    max_metadata_bytes: int = DEFAULT_MAX_METADATA_BYTES,
) -> ScopeManifest:
    caps = {
        "records": max_records,
        "paths": max_paths,
        "ast_nodes": 0,
        "metadata_bytes": max_metadata_bytes,
    }
    records: list[ScopeRecord] = []
    truncated = {"records": False, "paths": False, "ast_nodes": False, "metadata_bytes": False}
    regexes = [re.compile(pattern) for pattern in patterns]
    for index, doc in enumerate(corpus.docs):
        if index >= max_paths:
            truncated["paths"] = True
            break
        spans = [(m.start(), m.end()) for rx in regexes for m in rx.finditer(doc.text)] or [
            (0, len(doc.text))
        ]
        for start, end in spans:
            if len(records) >= max_records:
                truncated["records"] = True
                break
            n_chars = end - start
            records.append(
                ScopeRecord(
                    f"c-{len(records) + 1:04d}",
                    {"id": doc.id, "start": start, "end": end},
                    n_chars,
                    "fit" if n_chars <= ASK_LEAF_CHARS else "child",
                    ("regex" if regexes else "catalog",),
                    "document",
                    doc.id,
                )
            )
        if truncated["records"]:
            break
    return _manifest(
        "research",
        query,
        records,
        paths=min(len(corpus.docs), max_paths),
        ast_nodes=0,
        truncated=truncated,
        caps=caps,
    )
