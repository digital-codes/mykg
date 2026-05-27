import json
from unittest.mock import MagicMock, patch

from mykg.orchestrator import PipelineContext
from mykg.steps.step_orphan_connect import run_orphan_connect
from mykg.steps.step_orphan_score import run_orphan_score

NODES = [
    {
        "id": "person-alice",
        "type": "Person",
        "confidence": 1.0,
        "attributes": {"name": {"value": "Alice", "confidence": 1.0}},
        "source_files": ["doc.md"],
    },
    {
        "id": "org-acme",
        "type": "Organization",
        "confidence": 1.0,
        "attributes": {"name": {"value": "Acme", "confidence": 1.0}},
        "source_files": ["doc.md"],
    },
    {
        "id": "person-bob",
        "type": "Person",
        "confidence": 1.0,
        "attributes": {"name": {"value": "Bob", "confidence": 1.0}},
        "source_files": ["doc.md"],
    },
]

EDGE_METADATA = {
    "edge-001": {
        "type": "works_at",
        "from": "person-alice",
        "to": "org-acme",
        "confidence": 0.9,
        "method": "llm_extraction",
        "attributes": {},
        "source_files": ["doc.md"],
    }
}

CHUNK_NODE_INDEX = {
    "doc.md": {
        "1": ["person-alice", "org-acme", "person-bob"],
    }
}

SCHEMA = {
    "concepts": [
        {"type": "Person", "parent": None, "attributes": ["name"]},
        {"type": "Organization", "parent": None, "attributes": ["name"]},
    ],
    "properties": [
        {"name": "works_at", "domain": "Person", "range": "Organization", "attributes": []},
    ],
}

ORPHAN_CANDIDATES = {
    "groups": [
        {
            "chunk_key": "doc.md::1",
            "filename": "doc.md",
            "chunk_idx": 1,
            "is_blank_response": False,
            "orphan_ids": ["person-bob"],
            "connected_ids": ["person-alice", "org-acme"],
        }
    ],
    "schema_gap_orphans": [],
}


def _make_ctx(tmp_path, adapter=None):
    ctx = PipelineContext(
        input_dir=tmp_path / "input",
        output_dir=tmp_path / "output",
        intermediate_dir=tmp_path / "intermediate",
        adapter=adapter or MagicMock(),
        base_schema=None,
        thesaurus=None,
        review=False,
    )
    ctx.input_dir.mkdir(parents=True, exist_ok=True)
    ctx.output_dir.mkdir(parents=True, exist_ok=True)
    ctx.intermediate_dir.mkdir(parents=True, exist_ok=True)
    return ctx


def test_orphan_score_happy_path(tmp_path):
    ctx = _make_ctx(tmp_path)
    (ctx.intermediate_dir / "nodes.json").write_text(json.dumps(NODES))
    (ctx.intermediate_dir / "edge_metadata.json").write_text(json.dumps(EDGE_METADATA))
    (ctx.intermediate_dir / "chunk_node_index.json").write_text(json.dumps(CHUNK_NODE_INDEX))
    (ctx.intermediate_dir / "schema.json").write_text(json.dumps(SCHEMA))

    run_orphan_score(ctx)

    candidates_path = ctx.intermediate_dir / "orphan_candidates.json"
    assert candidates_path.exists()
    payload = json.loads(candidates_path.read_text())
    assert "groups" in payload
    all_orphan_ids = [oid for g in payload["groups"] for oid in g["orphan_ids"]]
    assert "person-bob" in all_orphan_ids


def test_orphan_score_disabled(tmp_path):
    ctx = _make_ctx(tmp_path)
    (ctx.intermediate_dir / "nodes.json").write_text(json.dumps(NODES))
    (ctx.intermediate_dir / "edge_metadata.json").write_text(json.dumps(EDGE_METADATA))
    (ctx.intermediate_dir / "chunk_node_index.json").write_text(json.dumps(CHUNK_NODE_INDEX))
    (ctx.intermediate_dir / "schema.json").write_text(json.dumps(SCHEMA))

    with patch("mykg.steps.step_orphan_score._cfg") as mock_cfg:
        mock_cfg.ORPHAN_PASS_ENABLED = False
        mock_cfg.JSON_INDENT = 2
        run_orphan_score(ctx)

    candidates_path = ctx.intermediate_dir / "orphan_candidates.json"
    assert candidates_path.exists()
    payload = json.loads(candidates_path.read_text())
    assert payload == {"groups": [], "schema_gap_orphans": []}


def test_orphan_connect_happy_path(tmp_path):
    adapter = MagicMock()
    adapter.complete.return_value = json.dumps(
        [
            {
                "type": "works_at",
                "from": "person-bob",
                "to": "org-acme",
                "confidence": 0.85,
                "attributes": {},
            }
        ]
    )
    ctx = _make_ctx(tmp_path, adapter)
    (ctx.intermediate_dir / "orphan_candidates.json").write_text(json.dumps(ORPHAN_CANDIDATES))
    (ctx.intermediate_dir / "nodes.json").write_text(json.dumps(NODES))
    (ctx.intermediate_dir / "schema.json").write_text(json.dumps(SCHEMA))
    (ctx.intermediate_dir / "edge_metadata.json").write_text(json.dumps({}))

    with patch("mykg.orphan_connector.llm_complete_with_retry") as mock_llm:
        mock_llm.return_value = json.dumps(
            [
                {
                    "type": "works_at",
                    "from": "person-bob",
                    "to": "org-acme",
                    "confidence": 0.85,
                    "attributes": {},
                }
            ]
        )
        run_orphan_connect(ctx)

    connections_path = ctx.intermediate_dir / "orphan_connections.json"
    assert connections_path.exists()
    connections = json.loads(connections_path.read_text())
    assert len(connections) == 1
    edge = next(iter(connections.values()))
    assert edge["type"] == "works_at"
    assert edge["from"] == "person-bob"
    assert edge["to"] == "org-acme"

    edge_metadata = json.loads((ctx.intermediate_dir / "edge_metadata.json").read_text())
    assert any(
        e["type"] == "works_at" and e["from"] == "person-bob" for e in edge_metadata.values()
    )


def test_orphan_connect_disabled(tmp_path):
    ctx = _make_ctx(tmp_path)

    with patch("mykg.steps.step_orphan_connect._cfg") as mock_cfg:
        mock_cfg.ORPHAN_PASS_ENABLED = False
        mock_cfg.JSON_INDENT = 2
        run_orphan_connect(ctx)

    connections_path = ctx.intermediate_dir / "orphan_connections.json"
    assert connections_path.exists()
    connections = json.loads(connections_path.read_text())
    assert connections == {}


def test_orphan_connect_invalid_edge_dropped(tmp_path):
    ctx = _make_ctx(tmp_path)
    (ctx.intermediate_dir / "orphan_candidates.json").write_text(json.dumps(ORPHAN_CANDIDATES))
    (ctx.intermediate_dir / "nodes.json").write_text(json.dumps(NODES))
    (ctx.intermediate_dir / "schema.json").write_text(json.dumps(SCHEMA))
    (ctx.intermediate_dir / "edge_metadata.json").write_text(json.dumps({}))

    with patch("mykg.orphan_connector.llm_complete_with_retry") as mock_llm:
        # First call: edge confirmation (returns invalid edge type — will be rejected).
        # Second call: schema-gap proposal (returns empty new_properties — no SchemaUpdatedError).
        mock_llm.side_effect = [
            json.dumps(
                [
                    {
                        "type": "invented_relation_xyz",
                        "from": "person-bob",
                        "to": "org-acme",
                        "confidence": 0.9,
                        "attributes": {},
                    }
                ]
            ),
            json.dumps({"new_properties": []}),
        ]
        run_orphan_connect(ctx)

    connections_path = ctx.intermediate_dir / "orphan_connections.json"
    assert connections_path.exists()
    connections = json.loads(connections_path.read_text())
    assert len(connections) == 0

    orphan_log = json.loads((ctx.intermediate_dir / "orphan_log.json").read_text())
    rejection_events = [e for e in orphan_log if e["event"] == "orphan_edge_rejected"]
    assert len(rejection_events) >= 1
    assert rejection_events[0]["orphan_id"] == "person-bob"


def test_orphan_connect_empty_candidates(tmp_path):
    ctx = _make_ctx(tmp_path)
    (ctx.intermediate_dir / "orphan_candidates.json").write_text(
        json.dumps({"groups": [], "schema_gap_orphans": []})
    )
    (ctx.intermediate_dir / "nodes.json").write_text(json.dumps(NODES))
    (ctx.intermediate_dir / "schema.json").write_text(json.dumps(SCHEMA))
    (ctx.intermediate_dir / "edge_metadata.json").write_text(json.dumps({}))

    run_orphan_connect(ctx)

    connections_path = ctx.intermediate_dir / "orphan_connections.json"
    assert connections_path.exists()
    connections = json.loads(connections_path.read_text())
    assert connections == {}
