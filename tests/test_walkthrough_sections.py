"""Unit tests for untested sections in mykg.walkthrough."""

from __future__ import annotations

import json
from pathlib import Path

from mykg.walkthrough import (
    _section_final_graph,
    _section_llm_stats,
    _section_orphan_pass,
    _section_schema_evolution,
    generate_walkthrough,
)


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, (dict, list)):
        path.write_text(json.dumps(data, indent=2))
    else:
        path.write_text(data)


# ---------------------------------------------------------------------------
# 1. _section_schema_evolution — with history
# ---------------------------------------------------------------------------


def test_section_schema_evolution_with_history(tmp_path):
    session = tmp_path / "session"
    delta = {
        "seq": 1,
        "trigger": "pass1_merge",
        "concepts_added": ["Person", "Organization"],
        "concepts_removed": [],
        "properties_added": ["works_at"],
        "properties_removed": [],
        "timestamp": "2026-05-20T10:00:00+00:00",
    }
    _write(session / "intermediate" / "schema_history" / "001_pass1_merge.json", delta)
    _write(
        session / "intermediate" / "schema.json",
        {
            "concepts": [
                {"type": "Person", "parent": None, "attributes": ["name", "email"]},
                {"type": "Organization", "parent": None, "attributes": ["name"]},
            ],
            "properties": [
                {
                    "name": "works_at",
                    "domain": "Person",
                    "range": "Organization",
                    "attributes": ["role"],
                },
            ],
        },
    )

    result = _section_schema_evolution(session)

    assert "## 4. Schema Evolution" in result
    assert "pass1_merge" in result
    assert "Person" in result


# ---------------------------------------------------------------------------
# 2. _section_schema_evolution — no history dir
# ---------------------------------------------------------------------------


def test_section_schema_evolution_no_history(tmp_path):
    session = tmp_path / "session"
    (session / "intermediate").mkdir(parents=True)

    result = _section_schema_evolution(session)

    assert result
    assert "## 4. Schema Evolution" in result


# ---------------------------------------------------------------------------
# 3. _section_llm_stats — groups present
# ---------------------------------------------------------------------------


def test_section_llm_stats_groups(tmp_path):
    session = tmp_path / "session"
    session.mkdir()
    records = [
        {
            "context": "pass1 batch induction",
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_read_tokens": 10,
            "cache_creation_tokens": 5,
            "duration_s": 3.0,
        },
        {
            "context": "pass2 file extraction",
            "input_tokens": 200,
            "output_tokens": 80,
            "cache_read_tokens": 20,
            "cache_creation_tokens": 0,
            "duration_s": 8.0,
        },
        {
            "context": "orphan chunk recovery",
            "input_tokens": 150,
            "output_tokens": 60,
            "cache_read_tokens": 0,
            "cache_creation_tokens": 0,
            "duration_s": 5.0,
        },
    ]
    (session / "llm.log").write_text("\n".join(json.dumps(r) for r in records))

    result = _section_llm_stats(session)

    assert "Pass 1" in result
    assert "Pass 2" in result or "Instance extraction" in result
    assert "Orphan" in result


# ---------------------------------------------------------------------------
# 4. _section_llm_stats — missing file
# ---------------------------------------------------------------------------


def test_section_llm_stats_missing_file(tmp_path):
    session = tmp_path / "session"
    session.mkdir()

    result = _section_llm_stats(session)

    assert result
    assert "## 5. LLM Call Statistics" in result


# ---------------------------------------------------------------------------
# 5. _section_orphan_pass — with data
# ---------------------------------------------------------------------------


def test_section_orphan_pass_with_data(tmp_path):
    session = tmp_path / "session"
    _write(
        session / "intermediate" / "orphan_candidates.json",
        {
            "groups": [
                {"orphan_ids": ["person-charlie", "person-dana"], "connected_ids": ["org-acme"]},
            ],
            "schema_gap_orphans": [],
        },
    )
    _write(
        session / "intermediate" / "orphan_log.json",
        [
            {
                "event": "orphan_edge_added",
                "id": "edge-100",
                "type": "works_at",
                "from": "person-charlie",
                "to": "org-acme",
            },
            {
                "event": "orphan_edge_rejected",
                "orphan_id": "person-dana",
                "candidate_id": "org-acme",
                "reason": "low confidence",
            },
        ],
    )
    nodes = [
        {"id": "person-charlie", "type": "Person"},
        {"id": "person-dana", "type": "Person"},
        {"id": "org-acme", "type": "Organization"},
    ]
    edges = {
        "edge-100": {
            "type": "works_at",
            "from": "person-charlie",
            "to": "org-acme",
            "method": "orphan_inferred",
        },
    }

    result = _section_orphan_pass(session, [], nodes, edges)

    assert "## 7. Orphan Pass Summary" in result
    assert "Total orphans across groups: **2**" in result


# ---------------------------------------------------------------------------
# 6. _section_final_graph — with validation errors
# ---------------------------------------------------------------------------


def test_section_final_graph_with_validation_errors(tmp_path):
    session = tmp_path / "session"
    nodes = [
        {"id": "person-alice", "type": "Person"},
        {"id": "org-acme", "type": "Organization"},
    ]
    edges = {
        "edge-001": {
            "type": "works_at",
            "from": "person-alice",
            "to": "org-acme",
            "method": "llm_extraction",
        },
    }
    _write(
        session / "output" / "knowledge_graph_validation.json",
        {
            "valid": False,
            "tbox_checks": {"errors": ["some error"]},
            "abox_checks": {"errors": []},
        },
    )

    result = _section_final_graph(session, nodes, edges)

    assert "## 1. Final Graph Summary" in result
    assert "**invalid**" in result
    assert "1 TBox" in result


# ---------------------------------------------------------------------------
# 7. generate_walkthrough — minimal session
# ---------------------------------------------------------------------------


def test_generate_walkthrough_minimal(tmp_path):
    session = tmp_path / "2026-05-20T10-00-00"
    (session / "intermediate").mkdir(parents=True)
    (session / "output").mkdir(parents=True)

    _write(
        session / "run.log",
        "10:00:00 [INFO] mykg.orchestrator — RUN  ingest\n"
        "10:00:02 [INFO] mykg.orchestrator — DONE ingest\n",
    )
    _write(
        session / "intermediate" / "pipeline_state.json",
        {"started_at": "2026-05-20T10:00:00+00:00", "steps": {}},
    )
    _write(session / "intermediate" / "file_manifest.json", {"doc.md": "some content"})
    _write(
        session / "intermediate" / "schema.json",
        {"concepts": [], "properties": []},
    )
    _write(session / "intermediate" / "nodes.json", [])
    _write(session / "intermediate" / "edge_metadata.json", {})
    _write(
        session / "output" / "knowledge_graph_validation.json",
        {"valid": True, "tbox_checks": {"errors": []}, "abox_checks": {"errors": []}},
    )

    result = generate_walkthrough(session)

    assert isinstance(result, str)
    assert result
    assert "##" in result
