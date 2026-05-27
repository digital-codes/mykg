from __future__ import annotations

from mykg.logging import get

log = get("mykg.schema_flattener")


def flatten_schema(schema: dict) -> dict[str, list[str]]:
    by_type = {c["type"]: c for c in schema["concepts"]}
    result: dict[str, list[str]] = {}
    for concept_type in by_type:
        result[concept_type] = _flatten_one(concept_type, by_type)
    return result


def _flatten_one(concept_type: str, by_type: dict) -> list[str]:
    chain: list[list[str]] = []
    visited: set[str] = set()
    current = by_type.get(concept_type)
    while current:
        ctype = current["type"]
        if ctype in visited:
            log.warning("Cycle detected in is-a hierarchy at '%s' — stopping traversal", ctype)
            break
        visited.add(ctype)
        chain.append(current.get("attributes", []))
        parent = current.get("parent")
        current = by_type.get(parent) if parent else None
    return [attr for level in reversed(chain) for attr in level]
