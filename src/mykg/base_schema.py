from __future__ import annotations

from rdflib import RDF, RDFS, Graph


class BaseSchemaError(Exception):
    pass


def _local(uri) -> str:
    return str(uri).split("/")[-1].split("#")[-1]


def parse_base_schema(ttl_content: str) -> dict:
    g = Graph()
    try:
        g.parse(data=ttl_content, format="turtle")
    except Exception as exc:
        raise BaseSchemaError(f"Failed to parse base schema TTL: {exc}") from exc

    locked_classes: dict[str, dict] = {}
    locked_properties: dict[str, dict] = {}

    for s, _, _ in g.triples((None, RDF.type, RDFS.Class)):
        name = _local(s)
        parent_node = g.value(s, RDFS.subClassOf)
        parent = _local(parent_node) if parent_node else None
        locked_classes[name] = {"type": name, "parent": parent, "attributes": []}

    for s, _, _ in g.triples((None, RDF.type, RDF.Property)):
        name = _local(s)
        domain_nodes = list(g.objects(s, RDFS.domain))
        range_node = g.value(s, RDFS.range)
        range_ = _local(range_node) if range_node and range_node != RDFS.Literal else None
        if range_node == RDFS.Literal:
            # Datatype property → add to all declared domain classes
            for domain_node in domain_nodes:
                domain = _local(domain_node)
                if domain in locked_classes:
                    locked_classes[domain]["attributes"].append(name)
        else:
            # Object property — use first domain for the locked_properties entry
            domain_node = domain_nodes[0] if domain_nodes else None
            domain = _local(domain_node) if domain_node else None
            locked_properties[name] = {
                "name": name,
                "domain": domain,
                "range": range_,
                "attributes": [],
            }

    return {"locked_classes": locked_classes, "locked_properties": locked_properties}
