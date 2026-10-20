"""Vectorless, reasoning-based navigation over policy documents.

Hybrid search (``index.py``) finds *chunks* that look like the question. Some
questions need the *structure* instead: "what does the escalation SOP cover?",
"walk me through the supplier contract", or a follow-up that needs the whole
section a chunk came from. Following the PageIndex idea, we expose each
document as a tree – document -> sections – with a short extractive summary
per node, and let the model navigate it like a table of contents:

    browse_docs()                         -> outline of every document
    browse_docs(node_id="supplier_contracts")            -> that document's sections
    browse_docs(node_id="supplier_contracts#Penalties")  -> full section text

The tree is built from markdown layout only (no LLM, no embeddings), so it is
deterministic and free. Section text goes through the same injection
sanitiser as the hybrid index: a poisoned section is returned with the
injected sentences removed and ``untrusted: true``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from kairos.rag.index import CORPUS_DIR, Chunk, _sanitize


@dataclass
class Node:
    id: str
    title: str
    summary: str
    text: str = ""
    untrusted: bool = False
    children: list[Node] = field(default_factory=list)


def _summary(text: str, words: int = 24) -> str:
    first = re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)[0]
    w = first.split()
    return " ".join(w[:words]) + (" ..." if len(w) > words else "")


def parse(source: str, markdown: str) -> Node:
    title = source
    preamble: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    for line in markdown.splitlines():
        if line.startswith("# "):
            title = line[2:].strip()
        elif line.startswith("## "):
            sections.append((line[3:].strip(), []))
        elif line.strip():
            (sections[-1][1] if sections else preamble).append(line.strip())
    root = Node(source, title, _summary(" ".join(preamble) or (" ".join(sections[0][1]) if sections else "")))
    for heading, lines in sections:
        clean = _sanitize(Chunk(f"{source}#{heading}", source, heading, " ".join(lines)))
        root.children.append(Node(f"{source}#{heading}", heading, _summary(clean.text), clean.text, clean.untrusted))
    root.untrusted = any(c.untrusted for c in root.children)
    return root


class DocTree:
    def __init__(self, roots: list[Node]) -> None:
        self.roots = roots
        self._by_id = {n.id.lower(): n for r in roots for n in (r, *r.children)}

    @classmethod
    def from_dir(cls, path: Path = CORPUS_DIR) -> DocTree:
        return cls([parse(f.stem, f.read_text()) for f in sorted(path.glob("*.md"))])

    def browse(self, node_id: str | None = None) -> dict[str, Any]:
        if not node_id:
            return {"documents": [{"node_id": r.id, "title": r.title, "summary": r.summary,
                                   "untrusted": r.untrusted, "sections": [c.title for c in r.children]}
                                  for r in self.roots]}
        node = self._by_id.get(node_id.strip().lower())
        if node is None:
            raise LookupError(f"unknown node_id {node_id}; call browse_docs with no node_id for the outline")
        if node.children:
            return {"node_id": node.id, "title": node.title, "summary": node.summary, "untrusted": node.untrusted,
                    "sections": [{"node_id": c.id, "title": c.title, "summary": c.summary,
                                  "untrusted": c.untrusted} for c in node.children]}
        return {"node_id": node.id, "title": node.title, "text": node.text, "untrusted": node.untrusted,
                "cite_as": node.id}
