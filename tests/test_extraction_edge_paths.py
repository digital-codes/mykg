from __future__ import annotations

import json
from unittest.mock import MagicMock

from mykg.chunker import Chunk
from mykg.llm.adapter import LLMAdapter
from mykg.pass1 import run_pass1
from mykg.pass2 import _partial_recover, run_pass2

SCHEMA = {
    "concepts": [
        {"type": "Person", "parent": None, "attributes": ["name"]},
        {"type": "Organization", "parent": None, "attributes": ["name"]},
    ],
    "properties": [
        {"name": "works_at", "domain": "Person", "range": "Organization", "attributes": []},
    ],
}

FLAT_SCHEMA = {"Person": ["name"], "Organization": ["name"]}

VALID_SCHEMA_RESPONSE = json.dumps(
    {
        "concepts": [{"type": "Person", "parent": None, "attributes": ["name"]}],
        "properties": [{"name": "knows", "domain": "Person", "range": "Person", "attributes": []}],
    }
)


def _make_adapter(responses: list[str]) -> LLMAdapter:
    adapter = MagicMock(spec=LLMAdapter)
    adapter.complete.side_effect = responses
    return adapter


def _make_chunk(text: str = "Alice works at Acme.", source_file: str = "doc.md") -> Chunk:
    return Chunk(source_file=source_file, chunk_index=0, text=text, token_start=0, token_end=10)


def test_pass1_json_retry_on_bad_json():
    adapter = _make_adapter(["not json at all", VALID_SCHEMA_RESPONSE])
    result = run_pass1([_make_chunk()], adapter, locked_schema_block="")
    assert len(result) == 1
    assert "concepts" in result[0]
    assert "properties" in result[0]


def test_pass1_batch_skipped_on_persistent_bad_json():
    adapter = _make_adapter(["not json", "still not json"])
    result = run_pass1([_make_chunk()], adapter, locked_schema_block="")
    assert result == []


def test_pass1_missing_properties_key_skipped():
    adapter = _make_adapter(['{"concepts": []}'])
    result = run_pass1([_make_chunk()], adapter, locked_schema_block="")
    assert result == []


def test_partial_recover_drops_dangling_edge():
    extraction = {
        "nodes": [
            {"id": "person-alice", "type": "Person", "confidence": 0.9, "attributes": {}},
        ],
        "edges": [
            {
                "type": "works_at",
                "from": "person-alice",
                "to": "org-ghost",
                "confidence": 0.8,
                "attributes": {},
            }
        ],
    }
    result = _partial_recover(extraction, SCHEMA, prior_nodes=None)
    assert result["edges"] == []


def test_partial_recover_drops_hallucinated_anchor():
    extraction = {
        "nodes": [
            {"id": "person-ghost", "type": "Person", "confidence": 0.9, "attributes": {}},
        ],
        "edges": [
            {
                "type": "works_at",
                "from": "person-ghost",
                "to": "org-unknown",
                "confidence": 0.8,
                "attributes": {},
            }
        ],
    }
    result = _partial_recover(extraction, SCHEMA, prior_nodes=None)
    node_ids = [n["id"] for n in result["nodes"]]
    assert "person-ghost" not in node_ids
    assert result["edges"] == []


def test_partial_recover_prior_node_not_in_output_nodes():
    prior_node = {"id": "person-alice", "type": "Person", "confidence": 0.9, "attributes": {}}
    result = _partial_recover({"nodes": [], "edges": []}, SCHEMA, prior_nodes=[prior_node])
    node_ids = [n["id"] for n in result["nodes"]]
    assert "person-alice" not in node_ids


def test_pass2_failed_chunk_recorded(tmp_path):
    class BlankAdapter(LLMAdapter):
        def complete(self, system, user, context_label="", max_tokens=None, timeout=None):
            return ""

        def endpoint_label(self) -> str:
            return "mock-blank"

    manifest = {"doc.md": "Alice works at Acme Corp.\n" * 40}
    _result, _chunk_index, failed = run_pass2(
        manifest,
        SCHEMA,
        FLAT_SCHEMA,
        BlankAdapter(),
        intermediate_dir=tmp_path,
    )
    failed_path = tmp_path / "failed_chunks.json"
    assert failed_path.exists()
    entries = json.loads(failed_path.read_text())
    assert len(entries) > 0
    assert any(e["filename"] == "doc.md" for e in entries)
