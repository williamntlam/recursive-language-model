"""Repository bound as a structured REPL object. No bash."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

from rlm.core.history import ASK_LEAF_CHARS, measure_text, plan_reads, route_read_subcall
from rlm.core.types import RecordAccess

DEFAULT_IGNORE_DIR_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".idea",
        ".vscode",
        ".venv",
        "venv",
        "node_modules",
        "__pycache__",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        ".tox",
        ".eggs",
        "dist",
        "build",
        "target",
        "vendor",
        ".next",
        "coverage",
        ".rlm",
        ".egg-info",
    }
)

DEFAULT_IGNORE_FILES = frozenset(
    {
        "package-lock.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "Cargo.lock",
        "poetry.lock",
        "uv.lock",
        "Gemfile.lock",
        "composer.lock",
    }
)

DEFAULT_IGNORE_SUFFIXES = frozenset(
    {
        ".pyc",
        ".pyo",
        ".so",
        ".dylib",
        ".dll",
        ".whl",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".pdf",
        ".zip",
        ".tar",
        ".gz",
        ".bz2",
        ".xz",
        ".7z",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".class",
        ".o",
        ".a",
    }
)

TEXT_SUFFIXES = frozenset(
    {
        ".py",
        ".pyi",
        ".md",
        ".txt",
        ".rst",
        ".toml",
        ".yaml",
        ".yml",
        ".json",
        ".jsonc",
        ".toml",
        ".ini",
        ".cfg",
        ".c",
        ".h",
        ".cc",
        ".cpp",
        ".hpp",
        ".rs",
        ".go",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".java",
        ".kt",
        ".swift",
        ".rb",
        ".php",
        ".css",
        ".html",
        ".htm",
        ".xml",
        ".sql",
        ".sh",
        ".bash",
        ".zsh",
        ".ps1",
        ".r",
        ".jl",
        ".lua",
        ".vue",
        ".svelte",
        ".gradle",
        ".cmake",
        ".makefile",
        ".dockerfile",
        ".gitignore",
        ".env.example",
    }
)


@dataclass(frozen=True)
class FileMeta(RecordAccess):
    path: str
    n_bytes: int
    n_lines: int
    sha: str


@dataclass(frozen=True)
class GrepHit(RecordAccess):
    path: str
    line_no: int
    line: str

    def __repr__(self) -> str:
        return f"GrepHit(path={self.path!r}, line_no={self.line_no}, line={self.line!r})"


def _is_ignored_dir(name: str, extra: Sequence[str]) -> bool:
    if name in DEFAULT_IGNORE_DIR_NAMES:
        return True
    return any(fnmatch(name, pat) for pat in extra)


def _is_ignored_file(name: str, extra: Sequence[str]) -> bool:
    if name in DEFAULT_IGNORE_FILES:
        return True
    suffix = Path(name).suffix.lower()
    if suffix in DEFAULT_IGNORE_SUFFIXES:
        return True
    return any(fnmatch(name, pat) for pat in extra)


def _looks_text(path: Path) -> bool:
    suffix = path.suffix.lower()
    if suffix in TEXT_SUFFIXES or path.name.lower() in {
        "makefile",
        "dockerfile",
        "license",
        "readme",
    }:
        return True
    if suffix in DEFAULT_IGNORE_SUFFIXES:
        return False
    try:
        sample = path.read_bytes()[:8000]
    except OSError:
        return False
    if b"\x00" in sample:
        return False
    try:
        sample.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False


def git_head(root: Path) -> str:
    head = root / ".git" / "HEAD"
    if not head.is_file():
        return "none"
    try:
        raw = head.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"
    if raw.startswith("ref:"):
        ref = raw.split(":", 1)[1].strip()
        ref_path = root / ".git" / ref
        if ref_path.is_file():
            try:
                return ref_path.read_text(encoding="utf-8").strip()[:12]
            except OSError:
                return ref
        return ref
    return raw[:12]


def _looks_int(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, str):
        stripped = value.strip()
        return bool(stripped) and stripped.lstrip("+-").isdigit()
    return False


def _coerce_int(value: int | str, name: str) -> int:
    if not _looks_int(value):
        raise TypeError(f"{name} must be an int, got {value!r}")
    return int(value)


class Repo:
    def __init__(
        self,
        root: str | Path,
        ignore: Sequence[str] | None = None,
        *,
        targets: list[dict] | None = None,
    ) -> None:
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise FileNotFoundError(f"repo path does not exist: {self.root}")
        self.ignore = tuple(ignore or ())
        self._query_fn = None
        self._rlm_fn = None
        self.targets = self.normalize_targets(targets) if targets is not None else None

    def normalize_targets(self, targets: list[dict] | None) -> list[dict]:
        """Validate a child target manifest without returning source content."""
        if not isinstance(targets, list):
            raise ValueError("repo.explore targets must be a non-empty list of target records.")
        normalized: list[dict] = []
        for item in targets:
            if not isinstance(item, dict) or set(item) - {"path", "start", "end"}:
                raise ValueError("Each repository target must contain path, start, and end only.")
            path = item.get("path")
            if not isinstance(path, str) or not path.strip():
                raise ValueError("Each repository target requires a non-empty path.")
            target = self._safe(path)
            if not target.is_file():
                raise ValueError(f"Repository target is not a file: {path!r}.")
            start, end = item.get("start"), item.get("end")
            if start is not None and (
                isinstance(start, bool) or not isinstance(start, int) or start < 1
            ):
                raise ValueError("Repository target start must be a positive line number or None.")
            if end is not None and (isinstance(end, bool) or not isinstance(end, int) or end < 1):
                raise ValueError("Repository target end must be a positive line number or None.")
            if start is not None and end is not None and start > end:
                raise ValueError("Repository target start must not exceed end.")
            normalized.append({"path": self._rel(target), "start": start, "end": end})
        return sorted(normalized, key=lambda x: (x["path"], x["start"] or 0, x["end"] or 0))

    def _scope_ranges(self, path: str) -> list[tuple[int | None, int | None]] | None:
        if self.targets is None:
            return None
        ranges = [(x["start"], x["end"]) for x in self.targets if x["path"] == path]
        if not ranges:
            raise ValueError(f"{path!r} is outside the declared repository target scope.")
        return ranges

    def _check_scope(self, path: str, start: int | None = None, end: int | None = None) -> None:
        ranges = self._scope_ranges(path)
        if ranges is None:
            return
        line_count = len(
            self._safe(path).read_text(encoding="utf-8", errors="replace").splitlines()
        )
        requested_start = 1 if start is None else start
        requested_end = line_count if end is None else end
        if not any(
            (lo is None or requested_start >= lo) and (hi is None or requested_end <= hi)
            for lo, hi in ranges
        ):
            raise ValueError(
                f"Requested span for {path!r} escapes the declared repository target scope."
            )

    def _check_glob_scope(self, pattern: str) -> None:
        if self.targets is None:
            return
        scoped_paths = {item["path"] for item in self.targets}
        for file in self._walk_files():
            rel = self._rel(file)
            if (fnmatch(rel, pattern) or fnmatch(file.name, pattern)) and rel not in scoped_paths:
                raise ValueError("Requested glob escapes the declared repository target scope.")

    def _rel(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    def _safe(self, path: str) -> Path:
        p = Path(path)
        resolved = (self.root / p).resolve() if not p.is_absolute() else p.resolve()
        resolved.relative_to(self.root)
        return resolved

    def _walk_files(self):
        for dirpath, dirnames, filenames in os_walk_filtered(self.root, self.ignore):
            base = Path(dirpath)
            for name in filenames:
                if _is_ignored_file(name, self.ignore):
                    continue
                yield base / name

    def tree(
        self,
        path: str | int | None = None,
        max_depth: int | str = 3,
        ignore: Sequence[str] | None = None,
    ) -> str:
        extra = tuple(ignore) if ignore is not None else self.ignore
        if self.targets is not None:
            sub = None if path is None or _looks_int(path) else str(path).rstrip("/")
            paths = [
                x["path"]
                for x in self.targets
                if not sub or x["path"] == sub or x["path"].startswith(sub + "/")
            ]
            if not paths:
                raise ValueError("Requested tree is outside the declared repository target scope.")
            return "\n".join(sorted(set(paths)))
        sub: str | None = None
        if path is None:
            depth_limit = _coerce_int(max_depth, "max_depth")
        elif _looks_int(path):
            depth_limit = _coerce_int(path, "max_depth")
        else:
            sub = str(path)
            depth_limit = _coerce_int(max_depth, "max_depth")
        start = self._safe(sub) if sub else self.root
        if not start.is_dir():
            raise NotADirectoryError(
                f"repo.tree() expected a directory, got {self._rel(start)!r}. "
                "Use repo.read(path) or repo.glob(pattern) for files."
            )
        lines: list[str] = []

        def rec(current: Path, depth: int, prefix: str) -> None:
            if depth > depth_limit:
                return
            try:
                entries = sorted(current.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            except OSError:
                return
            visible = []
            for ent in entries:
                if ent.is_dir() and _is_ignored_dir(ent.name, extra):
                    continue
                if ent.is_file() and _is_ignored_file(ent.name, extra):
                    continue
                visible.append(ent)
            for i, ent in enumerate(visible):
                last = i == len(visible) - 1
                branch = "└── " if last else "├── "
                label = ent.name + ("/" if ent.is_dir() else "")
                lines.append(prefix + branch + label)
                if ent.is_dir() and depth < depth_limit:
                    rec(ent, depth + 1, prefix + ("    " if last else "│   "))

        lines.append((start.name if sub else self.root.name) + "/")
        rec(start, 1, "")
        return "\n".join(lines)

    def glob(self, pattern: str) -> list[str]:
        self._check_glob_scope(pattern)
        out: list[str] = []
        for file in self._walk_files():
            rel = self._rel(file)
            if self.targets is not None and not any(x["path"] == rel for x in self.targets):
                continue
            if fnmatch(rel, pattern) or fnmatch(file.name, pattern):
                out.append(rel)
        return sorted(out)

    def file_text(self, path: str) -> str:
        target = self._safe(path)
        rel = self._rel(target)
        self._check_scope(rel)
        return target.read_text(encoding="utf-8", errors="replace")

    def read(
        self,
        path: str,
        start: int | str | None = None,
        end: int | str | None = None,
    ) -> str:
        target = self._safe(path)
        rel = self._rel(target)
        requested_start = None if start is None else _coerce_int(start, "start")
        requested_end = None if end is None else _coerce_int(end, "end")
        self._check_scope(rel, requested_start, requested_end)
        text = target.read_text(encoding="utf-8", errors="replace")
        if start is None and end is None:
            return text
        lines = text.splitlines(keepends=True)
        s = (1 if requested_start is None else requested_start) - 1
        e = len(lines) if requested_end is None else requested_end
        s = max(0, s)
        e = min(len(lines), e)
        return "".join(lines[s:e])

    def ask(
        self,
        path: str,
        question: str,
        start: int | str | None = None,
        end: int | str | None = None,
    ) -> str:
        """Read a slice; leaf if small, otherwise a child RLM that inherits this repo."""
        text = self.read(path, start, end)
        if start is None and end is None:
            loc = path
        else:
            loc = f"{path}:{start or 1}-{end or 'end'}"
        target = {
            "path": self._rel(self._safe(path)),
            "start": None if start is None else _coerce_int(start, "start"),
            "end": None if end is None else _coerce_int(end, "end"),
        }
        return route_read_subcall(
            question, loc, text, self._query_fn, self._rlm_fn, targets=[target]
        )

    def measure(
        self,
        path: str,
        start: int | str | None = None,
        end: int | str | None = None,
    ) -> dict:
        """n_chars / n_tokens / route for a span. Does not return the body."""
        text = self.read(path, start, end)
        line_offset = 0 if start is None else max(0, _coerce_int(start, "start") - 1)
        row = measure_text(text, leaf_chars=ASK_LEAF_CHARS, line_offset=line_offset)
        row["path"] = path
        if start is not None:
            row["start"] = _coerce_int(start, "start")
        if end is not None:
            row["end"] = _coerce_int(end, "end")
        return row

    def plan(self, spans: list | dict | str) -> dict:
        """n_fit / n_child / n_chunks for path spans. Reads files; drops bodies."""
        seq: list
        if isinstance(spans, list):
            seq = spans
        else:
            seq = [spans]
        rows: list[dict] = []
        for item in seq:
            if isinstance(item, str):
                rows.append(self.measure(item))
                continue
            if not isinstance(item, dict):
                continue
            path = item.get("path") or item.get("file")
            if not path:
                continue
            row = self.measure(path, item.get("start"), item.get("end"))
            for key in ("name", "qualname", "kind"):
                if key in item:
                    row[key] = item[key]
            rows.append(row)
        return plan_reads(rows)

    def explore(self, question: str, targets: list[dict] | None = None) -> str:
        """Spawn a child RLM with the same repo. Use only if ast/ask is not enough."""
        fn = self._rlm_fn
        if fn is None:
            raise RuntimeError("repo.explore requires rlm_query. Call rlm_query(question) instead.")
        normalized = None if targets is None else self.normalize_targets(targets)
        return str(fn(question, targets=normalized))

    def grep(self, pattern: str, glob: str | None = None) -> list[GrepHit]:
        if glob is not None:
            self._check_glob_scope(glob)
        rx = re.compile(pattern)
        hits: list[GrepHit] = []
        for file in self._walk_files():
            if not _looks_text(file):
                continue
            rel = self._rel(file)
            if self.targets is not None and not any(x["path"] == rel for x in self.targets):
                continue
            if glob and not (fnmatch(rel, glob) or fnmatch(file.name, glob)):
                continue
            try:
                text = file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), start=1):
                if self.targets is not None:
                    ranges = self._scope_ranges(rel) or []
                    if not any(
                        (lo is None or i >= lo) and (hi is None or i <= hi) for lo, hi in ranges
                    ):
                        continue
                if rx.search(line):
                    hits.append(GrepHit(path=rel, line_no=i, line=line[:400]))
        return hits

    def files(self) -> list[FileMeta]:
        out: list[FileMeta] = []
        for file in self._walk_files():
            if not _looks_text(file):
                continue
            if self.targets is not None and not any(
                x["path"] == self._rel(file) for x in self.targets
            ):
                continue
            try:
                data = file.read_bytes()
            except OSError:
                continue
            text = data.decode("utf-8", errors="replace")
            out.append(
                FileMeta(
                    path=self._rel(file),
                    n_bytes=len(data),
                    n_lines=text.count("\n") + (0 if text.endswith("\n") or not text else 1),
                    sha=hashlib.sha256(data).hexdigest()[:16],
                )
            )
        return out


def os_walk_filtered(root: Path, extra: Sequence[str]):
    import os

    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if not _is_ignored_dir(d, extra)]
        yield dirpath, dirnames, filenames


def repo_manifest(repo: Repo) -> str:
    files = repo.files()
    total = sum(f.n_bytes for f in files)
    top = repo.tree(max_depth=1)
    head = git_head(repo.root)
    return (
        f"Repository: {repo.root}\n"
        f"Files: {len(files):,}  |  Text-ish bytes: {total}  |  Git HEAD: {head}\n"
        f"Top-level:\n{top}\n"
        "Use repo.tree(), repo.grep(), repo.file_text + ast, repo.measure, repo.plan, repo.ask.\n"
        "Do not print entire files. Classify with code here; llm_query tight slices; "
        "child RLM only if plan_reads / repo.plan says route is child.\n"
    )


def load_repo(
    path: str | Path, ignore: Sequence[str] | None = None, *, targets: list[dict] | None = None
) -> Repo:
    return Repo(path, ignore=ignore, targets=targets)
