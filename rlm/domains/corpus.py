"""Research corpus: markdown/text/html/PDF-as-text, bound as `corpus`."""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path

SKIP_DIR_NAMES = frozenset({".git", ".rlm", "__pycache__", ".venv", "venv"})
TEXT_EXTS = {".md", ".txt", ".rst"}
HTML_EXTS = {".html", ".htm"}
PDF_EXTS = {".pdf"}


@dataclass
class Document:
    id: str
    path: str
    title: str | None
    text: str
    n_chars: int


@dataclass(frozen=True)
class SearchHit:
    doc_id: str
    line_no: int
    snippet: str


class _HTMLText(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self._skip = False

    def handle_starttag(self, tag, attrs):  # noqa: ARG002
        if tag in {"script", "style", "noscript"}:
            self._skip = True

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"}:
            self._skip = False
        if tag in {"p", "div", "br", "li", "h1", "h2", "h3", "h4", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip:
            self.parts.append(data)

    def text(self) -> str:
        return re.sub(r"\n{3,}", "\n\n", "".join(self.parts)).strip()


def html_to_text(raw: str) -> str:
    parser = _HTMLText()
    parser.feed(raw)
    return parser.text()


def extract_pdf(path: Path) -> str | None:
    try:
        from pypdf import PdfReader
    except ImportError:
        return None
    reader = PdfReader(str(path))
    parts: list[str] = []
    for page in reader.pages:
        parts.append(page.extract_text() or "")
    return "\n".join(parts)


def _title_from(path: Path, text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            return stripped[2:].strip()
        if stripped:
            return stripped[:120]
    return path.stem


def ingest_path(root: Path) -> list[Document]:
    docs: list[Document] = []
    files: list[Path] = []
    if root.is_file():
        files = [root]
        root = root.parent
    else:
        for dirpath, dirnames, filenames in __import__("os").walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIR_NAMES]
            for name in filenames:
                files.append(Path(dirpath) / name)
    n = 0
    for file in sorted(files):
        ext = file.suffix.lower()
        text: str | None = None
        if ext in TEXT_EXTS:
            text = file.read_text(encoding="utf-8", errors="replace")
        elif ext in HTML_EXTS:
            text = html_to_text(file.read_text(encoding="utf-8", errors="replace"))
        elif ext in PDF_EXTS:
            sidecar = file.with_name(file.name + ".rlm.txt")
            if sidecar.is_file():
                text = sidecar.read_text(encoding="utf-8", errors="replace")
            else:
                extracted = extract_pdf(file)
                if extracted is None:
                    continue
                try:
                    sidecar.write_text(extracted, encoding="utf-8")
                except OSError:
                    pass
                text = extracted
        else:
            continue
        n += 1
        doc_id = f"doc-{n:04d}"
        if root in file.parents or file.parent == root:
            rel = str(file.relative_to(root))
        else:
            rel = str(file)
        docs.append(
            Document(
                id=doc_id,
                path=rel,
                title=_title_from(file, text),
                text=text,
                n_chars=len(text),
            )
        )
    return docs


class Corpus:
    def __init__(self, docs: list[Document]) -> None:
        self.docs = docs
        self._by_id = {d.id: d for d in docs}

    def search(self, pattern: str) -> list[SearchHit]:
        rx = re.compile(pattern)
        hits: list[SearchHit] = []
        for doc in self.docs:
            for i, line in enumerate(doc.text.splitlines(), start=1):
                if rx.search(line):
                    hits.append(SearchHit(doc_id=doc.id, line_no=i, snippet=line[:400]))
        return hits

    def get(self, id: str) -> Document:  # noqa: A002
        if id not in self._by_id:
            raise KeyError(id)
        return self._by_id[id]

    def slice(self, id: str, start: int, end: int) -> str:  # noqa: A002
        return self.get(id).text[start:end]


def catalog_rows(corpus: Corpus) -> list[dict]:
    return [
        {"id": d.id, "title": d.title, "path": d.path, "n_chars": d.n_chars}
        for d in corpus.docs
    ]


def corpus_manifest(corpus: Corpus, preview: int = 12) -> str:
    rows = catalog_rows(corpus)
    lines = [
        f"Corpus: {len(rows)} documents.",
        "Bound as `corpus` and `catalog` (list of id/title/path/n_chars).",
        "Use corpus.search, corpus.get, corpus.slice. Do not print full documents.",
        "Catalog preview:",
    ]
    for row in rows[:preview]:
        lines.append(
            f"  {row['id']}: {row['title']!r}  path={row['path']}  n_chars={row['n_chars']}"
        )
    if len(rows) > preview:
        lines.append(f"  ... ({len(rows) - preview} more; inspect catalog)")
    return "\n".join(lines) + "\n"


def load_corpus(path: str | Path | Sequence[str | Path]) -> Corpus:
    if isinstance(path, (str, Path)):
        root = Path(path)
        if not root.exists():
            raise FileNotFoundError(root)
        return Corpus(ingest_path(root))
    docs: list[Document] = []
    for item in path:
        docs.extend(ingest_path(Path(item)))
    # re-id sequentially
    for i, doc in enumerate(docs, start=1):
        doc.id = f"doc-{i:04d}"
    return Corpus(docs)
