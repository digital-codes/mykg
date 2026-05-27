from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from rdflib import Graph, Namespace

SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")


def _local(uri) -> str:
    return str(uri).split("/")[-1].split("#")[-1]


class SynonymIndex(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    term_count: int
    source_path: str = ""
    exact_matches: dict[str, list[str]] = Field(default_factory=dict)
    close_matches: dict[str, list[str]] = Field(default_factory=dict)
    # Advisory only — not used for collapsing in synonym_match; stored for audit/future use
    broader: dict[str, list[str]] = Field(default_factory=dict)
    narrower: dict[str, list[str]] = Field(default_factory=dict)

    def is_exact(self, a: str, b: str) -> bool:
        return b in self.exact_matches.get(a, []) or a in self.exact_matches.get(b, [])

    def is_close(self, a: str, b: str) -> bool:
        return b in self.close_matches.get(a, []) or a in self.close_matches.get(b, [])

    def has_exact_relations(self) -> bool:
        return bool(self.exact_matches)

    def has_close_relations(self) -> bool:
        return bool(self.close_matches)

    def has_broader_relations(self) -> bool:
        return bool(self.broader)

    def has_narrower_relations(self) -> bool:
        return bool(self.narrower)

    def _add(self, store: dict, a: str, b: str) -> None:
        store.setdefault(a, [])
        if b not in store[a]:
            store[a].append(b)
        store.setdefault(b, [])
        if a not in store[b]:
            store[b].append(a)

    def _add_directed(self, store: dict, a: str, b: str) -> None:
        """Add a directed (non-symmetric) relation from a to b."""
        store.setdefault(a, [])
        if b not in store[a]:
            store[a].append(b)


def parse_thesaurus(ttl_content: str, source: str = "") -> SynonymIndex:
    g = Graph()
    g.parse(data=ttl_content, format="turtle")

    idx = SynonymIndex(term_count=0, source_path=source)
    terms: set[str] = set()

    for s, p, o in g:
        a, b = _local(s), _local(o)
        terms.update([a, b])
        if p == SKOS.exactMatch:
            idx._add(idx.exact_matches, a, b)
        elif p == SKOS.closeMatch:
            idx._add(idx.close_matches, a, b)
        elif p == SKOS.broader:
            # Advisory only: a has broader concept b; mirror as narrower on b
            idx._add_directed(idx.broader, a, b)
            idx._add_directed(idx.narrower, b, a)
        elif p == SKOS.narrower:
            # Advisory only: a has narrower concept b; mirror as broader on b
            idx._add_directed(idx.narrower, a, b)
            idx._add_directed(idx.broader, b, a)

    idx.term_count = len(terms)
    return idx
