from __future__ import annotations

from pydantic import BaseModel, Field
from rdflib import RDF, RDFS, Graph


class SchemaValidationResult(BaseModel):
    valid: bool
    errors: list[dict] = Field(default_factory=list)


def validate_schema_ttl(ttl_content: str) -> SchemaValidationResult:
    errors: list[dict] = []

    # Phase A — Syntax
    g = Graph()
    try:
        g.parse(data=ttl_content, format="turtle")
    except Exception as exc:
        errors.append({"type": "syntax_error", "message": str(exc)})
        return SchemaValidationResult(valid=False, errors=errors)

    # Phase B — Semantic
    declared_classes = {s for s, _, _ in g.triples((None, RDF.type, RDFS.Class))}

    for s, _, _ in g.triples((None, RDF.type, RDF.Property)):
        domain_node = g.value(s, RDFS.domain)
        range_node = g.value(s, RDFS.range)
        prop_name = str(s).split("/")[-1]

        if domain_node and domain_node not in declared_classes:
            errors.append(
                {
                    "type": "undefined_domain",
                    "property": prop_name,
                    "message": f"rdfs:domain {domain_node} is not a declared rdfs:Class",
                }
            )
        if range_node and range_node != RDFS.Literal and range_node not in declared_classes:
            range_local = str(range_node).split("/")[-1]
            errors.append(
                {
                    "type": "undefined_range",
                    "property": prop_name,
                    "message": f"rdfs:range {range_local} is not a declared rdfs:Class",
                }
            )

    for child, _, parent in g.triples((None, RDFS.subClassOf, None)):
        if parent not in declared_classes:
            child_local = str(child).split("/")[-1]
            parent_local = str(parent).split("/")[-1]
            errors.append(
                {
                    "type": "undefined_parent",
                    "concept": child_local,
                    "message": f"rdfs:subClassOf {parent_local} is not a declared rdfs:Class",
                }
            )

    return SchemaValidationResult(valid=len(errors) == 0, errors=errors)
