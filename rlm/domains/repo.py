"""Repository bound as a structured REPL object. No bash."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Sequence
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

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
class FileMeta:
    path: str
    n_bytes: int
    n_lines: int
    sha: str


@dataclass(frozen=True)
class GrepHit:
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


class Repo:
    def __init__(self, root: str | Path, ignore: Sequence[str] | None = None) -> None:
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise FileNotFoundError(f"repo path does not exist: {self.root}")
        self.ignore = tuple(ignore or ())

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

    def tree(self, max_depth: int = 3, ignore: Sequence[str] | None = None) -> str:
        extra = tuple(ignore) if ignore is not None else self.ignore
        lines: list[str] = []

        def rec(current: Path, depth: int, prefix: str) -> None:
            if depth > max_depth:
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
                if ent.is_dir() and depth < max_depth:
                    rec(ent, depth + 1, prefix + ("    " if last else "│   "))

        lines.append(self.root.name + "/")
        rec(self.root, 1, "")
        return "\n".join(lines)

    def glob(self, pattern: str) -> list[str]:
        out: list[str] = []
        for file in self._walk_files():
            rel = self._rel(file)
            if fnmatch(rel, pattern) or fnmatch(file.name, pattern):
                out.append(rel)
        return sorted(out)

    def file_text(self, path: str) -> str:
        target = self._safe(path)
        return target.read_text(encoding="utf-8", errors="replace")

    def read(self, path: str, start: int | None = None, end: int | None = None) -> str:
        text = self.file_text(path)
        if start is None and end is None:
            return text
        lines = text.splitlines(keepends=True)
        s = (1 if start is None else start) - 1
        e = len(lines) if end is None else end
        s = max(0, s)
        e = min(len(lines), e)
        return "".join(lines[s:e])

    def grep(self, pattern: str, glob: str | None = None) -> list[GrepHit]:
        rx = re.compile(pattern)
        hits: list[GrepHit] = []
        for file in self._walk_files():
            if not _looks_text(file):
                continue
            rel = self._rel(file)
            if glob and not (fnmatch(rel, glob) or fnmatch(file.name, glob)):
                continue
            try:
                text = file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for i, line in enumerate(text.splitlines(), start=1):
                if rx.search(line):
                    hits.append(GrepHit(path=rel, line_no=i, line=line[:400]))
        return hits

    def files(self) -> list[FileMeta]:
        out: list[FileMeta] = []
        for file in self._walk_files():
            if not _looks_text(file):
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
        "Use repo.tree(), repo.grep(), repo.read(), repo.file_text(path).\n"
        "Do not print entire files. Assign them to variables and llm_query slices.\n"
    )


def load_repo(path: str | Path, ignore: Sequence[str] | None = None) -> Repo:
    return Repo(path, ignore=ignore)
