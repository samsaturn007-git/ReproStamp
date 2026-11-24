"""Incremental source index for the fixed app template."""

import ast
import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from .app_source import EDITABLE_FILES
from .integrity import canonical_json, hash_json

WORDS = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
TS_SYMBOLS = re.compile(r"\b(?:function|const|type)\s+([A-Za-z][A-Za-z0-9_]*)")
STOP_WORDS = frozenset("and the with from for use add using show return only".split())


def terms(text: str) -> set[str]:
    return {word.casefold() for word in WORDS.findall(text)} - STOP_WORDS


@dataclass(frozen=True)
class SourceFile:
    path: str
    sha256: str
    symbols: tuple[str, ...]
    text: str

    @classmethod
    def parse(cls, path: str, digest: str, data: bytes) -> "SourceFile":
        text = data.decode("utf-8")
        if path.endswith(".py"):
            symbols = [node.name for node in ast.walk(ast.parse(text))
                       if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
        else:
            symbols = TS_SYMBOLS.findall(text)
        return cls(path, digest, tuple(sorted(set(symbols))), text)

    def rank(self, query: set[str], evidence: str, errors: set[str]) -> int:
        names = terms(self.path + " " + " ".join(self.symbols))
        content = terms(self.text)
        return (20 * (self.path in evidence) + 5 * len(errors & names)
                + 3 * len(query & names) + len((query | errors) & content))

    def excerpt(self, keywords: set[str]) -> str:
        lines = self.text.splitlines()
        candidates = sorted(range(len(lines)), key=lambda index: (-len(keywords & terms(lines[index])), index))
        selected: set[int] = set()
        for index in candidates[:6]:
            selected.update(range(max(0, index - 1), min(len(lines), index + 2)))
        return "\n".join(f"{index + 1}: {lines[index][:160]}" for index in sorted(selected))


class RepoMap:
    def __init__(self) -> None:
        self.entries: dict[str, SourceFile] = {}

    def refresh(self, root: Path) -> int:
        rebuilt = 0
        for path in EDITABLE_FILES:
            data = (root / path).read_bytes()
            digest = hashlib.sha256(data).hexdigest()
            existing = self.entries.get(path)
            if existing is None or existing.sha256 != digest:
                self.entries[path] = SourceFile.parse(path, digest, data)
                rebuilt += 1
        return rebuilt

    def context(self, description: str, search_terms: tuple[str, ...] = (), failure: str = "") -> tuple[dict, dict]:
        query = terms(description + " " + " ".join(search_terms))
        errors = terms(failure)
        ranked = sorted(self.entries.values(), key=lambda item: (-item.rank(query, failure, errors), item.path))
        selected = ranked[:2]
        context = {
            "requirements": description,
            "failure_evidence": failure,
            "source": [{"path": item.path, "symbols": list(item.symbols), "excerpt": item.excerpt(query | errors)}
                       for item in selected],
        }
        full_context = {**context, "source": [{"path": item.path, "symbols": list(item.symbols), "excerpt": item.text}
                                              for item in ranked]}
        metrics = {
            "source_sha256": hash_json({item.path: item.sha256 for item in ranked}),
            "ranked_paths": [item.path for item in ranked],
            "selected_paths": [item.path for item in selected],
            "full_context_bytes": len(canonical_json(full_context)),
            "selected_context_bytes": len(canonical_json(context)),
        }
        return context, metrics
