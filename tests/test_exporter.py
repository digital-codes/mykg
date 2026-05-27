import json

from mykg.exporter import export_edges_jsonl, export_nodes_jsonl, export_ttl

SCHEMA = {
    "concepts": [
        {"type": "Person", "parent": None, "attributes": ["name", "email"]},
        {"type": "Organization", "parent": None, "attributes": ["name"]},
    ],
    "properties": [
        {"name": "works_at", "domain": "Person", "range": "Organization", "attributes": ["role"]}
    ],
}

NODES = [
    {
        "id": "person-alice",
        "type": "Person",
        "confidence": 0.99,
        "source_files": ["team.md"],
        "attributes": {
            "name": {"value": "Alice", "confidence": 0.99},
            "email": {"value": "alice@acme.com", "confidence": 0.97},
        },
    },
    {
        "id": "organization-acme-corp",
        "type": "Organization",
        "confidence": 0.99,
        "source_files": ["team.md"],
        "attributes": {"name": {"value": "Acme Corp", "confidence": 0.99}},
    },
]

EDGE_METADATA = {
    "edge-abc123": {
        "type": "works_at",
        "from": "person-alice",
        "to": "organization-acme-corp",
        "confidence": 0.96,
        "source_files": ["team.md"],
        "attributes": {"role": {"value": "engineer", "confidence": 0.91}},
    }
}


def test_nodes_jsonl_line_count():
    lines = export_nodes_jsonl(NODES).strip().split("\n")
    assert len(lines) == 2


def test_nodes_jsonl_valid_json():
    output = export_nodes_jsonl(NODES)
    for line in output.strip().split("\n"):
        obj = json.loads(line)
        assert "id" in obj
        assert "type" in obj


def test_edges_jsonl_line_count():
    lines = export_edges_jsonl(EDGE_METADATA).strip().split("\n")
    assert len(lines) == 1


def test_edges_jsonl_valid_json():
    output = export_edges_jsonl(EDGE_METADATA)
    obj = json.loads(output.strip())
    assert obj["id"] == "edge-abc123"
    assert obj["type"] == "works_at"


def test_ttl_contains_tbox_classes():
    ttl = export_ttl(SCHEMA, NODES, EDGE_METADATA)
    assert "rdfs:Class" in ttl
    assert "ex:Person" in ttl
    assert "ex:Organization" in ttl


def test_ttl_contains_tbox_properties():
    ttl = export_ttl(SCHEMA, NODES, EDGE_METADATA)
    assert "ex:works_at" in ttl
    assert "rdf:Property" in ttl


def test_ttl_contains_abox_instances():
    ttl = export_ttl(SCHEMA, NODES, EDGE_METADATA)
    assert "data:person-alice" in ttl
    assert "data:organization-acme-corp" in ttl


def test_ttl_contains_abox_object_triple():
    ttl = export_ttl(SCHEMA, NODES, EDGE_METADATA)
    assert "ex:works_at" in ttl
    assert "data:person-alice" in ttl and "data:organization-acme-corp" in ttl


def test_ttl_no_confidence_in_output():
    ttl = export_ttl(SCHEMA, NODES, EDGE_METADATA)
    assert "confidence" not in ttl


def test_ttl_escapes_newline_in_literal():
    """Attribute values containing newlines must be escaped in Turtle output."""
    from mykg.exporter import export_ttl

    schema = {
        "concepts": [{"type": "Person", "parent": None, "attributes": ["bio"]}],
        "properties": [],
    }
    nodes = [
        {
            "id": "person-alice",
            "type": "Person",
            "confidence": 0.9,
            "attributes": {
                "bio": {"value": "line one\nline two\r\nline three\ttabbed", "confidence": 0.9}
            },
        }
    ]
    ttl = export_ttl(schema, nodes, {})
    # Parse with rdflib to confirm it's valid Turtle
    from rdflib import Graph

    g = Graph()
    g.parse(data=ttl, format="turtle")  # must not raise
