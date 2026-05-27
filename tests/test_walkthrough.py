"""Unit tests for mykg.walkthrough helper functions.

All tests use tmp_path and minimal fake session directories — no live LLM calls.
"""

from __future__ import annotations

import json
from pathlib import Path

from mykg.walkthrough import (
    _build_concept_tree,
    _parse_log_lines,
    _section_llm_stats,
    _section_orphan_pass,
    _section_step_timeline,
    _section_warnings,
    generate_walkthrough,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, (dict, list)):
        path.write_text(json.dumps(data, indent=2))
    else:
        path.write_text(data)


# ---------------------------------------------------------------------------
# 1. test_parse_log_basic
# ---------------------------------------------------------------------------


def test_parse_log_basic(tmp_path):
    log_path = tmp_path / "run.log"
    log_path.write_text(
        "21:33:09 [INFO] mykg.cli — Command: mykg extract-graph input/\n"
        "21:33:10 [WARNING] mykg.pass2 — chunk 3 — validation errors: []\n"
        "not a valid log line\n"
    )
    parsed = _parse_log_lines(log_path)
    assert len(parsed) == 2
    assert parsed[0]["ts"] == "21:33:09"
    assert parsed[0]["level"] == "INFO"
    assert parsed[0]["logger"] == "mykg.cli"
    assert "Command:" in parsed[0]["message"]
    assert parsed[1]["level"] == "WARNING"


def test_parse_log_missing_file(tmp_path):
    result = _parse_log_lines(tmp_path / "nonexistent.log")
    assert result == []


# ---------------------------------------------------------------------------
# 2. test_parse_log_step_events
# ---------------------------------------------------------------------------


def test_parse_log_step_events(tmp_path):
    log_path = tmp_path / "run.log"
    log_path.write_text(
        "10:00:00 [INFO] mykg.orchestrator — RUN  ingest\n"
        "10:00:05 [INFO] mykg.orchestrator — DONE ingest\n"
        "10:00:05 [INFO] mykg.orchestrator — RUN  pass1\n"
        "10:01:00 [INFO] mykg.orchestrator — DONE pass1\n"
        "10:01:00 [INFO] mykg.orchestrator — SKIP schema_validate — outputs exist\n"
    )
    parsed = _parse_log_lines(log_path)
    orch = [ln for ln in parsed if "orchestrator" in ln["logger"]]
    assert len(orch) == 5
    runs = [ln for ln in orch if ln["message"].startswith("RUN")]
    dones = [ln for ln in orch if ln["message"].startswith("DONE")]
    skips = [ln for ln in orch if ln["message"].startswith("SKIP")]
    assert len(runs) == 2
    assert len(dones) == 2
    assert len(skips) == 1


# ---------------------------------------------------------------------------
# 3. test_step_timeline_duration
# ---------------------------------------------------------------------------


def test_step_timeline_duration(tmp_path):
    session = tmp_path / "session"
    (session / "intermediate").mkdir(parents=True)
    state = {"started_at": "2026-05-20T20:33:09+00:00", "steps": {}, "errors": {}}

    log_path = session / "run.log"
    log_path.write_text(
        "10:00:00 [INFO] mykg.orchestrator — RUN  ingest\n"
        "10:00:10 [INFO] mykg.orchestrator — DONE ingest\n"
        "10:00:10 [INFO] mykg.orchestrator — RUN  pass1\n"
        "10:05:10 [INFO] mykg.orchestrator — DONE pass1\n"
    )
    lines = _parse_log_lines(log_path)
    result = _section_step_timeline(session, lines, state)
    # ingest: 10s, pass1: 5min = 300s
    assert "10s" in result
    assert "5m" in result


# ---------------------------------------------------------------------------
# 4. test_schema_tree_rendering
# ---------------------------------------------------------------------------


def test_schema_tree_rendering():
    concepts = [
        {"type": "Person", "parent": None, "attributes": ["name", "email"]},
        {"type": "Organization", "parent": None, "attributes": ["name"]},
        {"type": "Employee", "parent": "Person", "attributes": ["role"]},
    ]
    tree = _build_concept_tree(concepts)
    assert "**Person**" in tree
    assert "**Organization**" in tree
    assert "**Employee**" in tree
    # Employee should be indented (child of Person)
    lines = tree.splitlines()
    person_line = next(ln for ln in lines if "Person" in ln and "Employee" not in ln)
    employee_line = next(ln for ln in lines if "Employee" in ln)
    # Employee line has more leading spaces than Person line
    person_indent = len(person_line) - len(person_line.lstrip())
    employee_indent = len(employee_line) - len(employee_line.lstrip())
    assert employee_indent > person_indent
    assert "is-a: Person" in employee_line


# ---------------------------------------------------------------------------
# 5. test_schema_evolution_empty
# ---------------------------------------------------------------------------


def test_schema_evolution_empty(tmp_path):
    session = tmp_path / "session"
    (session / "intermediate").mkdir(parents=True)
    # No schema_history dir, no schema.json
    from mykg.walkthrough import _section_schema_evolution

    result = _section_schema_evolution(session)
    assert "## 4. Schema Evolution" in result
    # Should not raise; should contain graceful fallback text
    assert "not found" in result or "No schema history" in result


# ---------------------------------------------------------------------------
# 6. test_llm_stats_grouping
# ---------------------------------------------------------------------------


def test_llm_stats_grouping(tmp_path):
    session = tmp_path / "session"
    session.mkdir()
    llm_log = session / "llm.log"
    records = [
        {
            "ts": "10:00:01",
            "context": "pass1 batch 1/4",
            "input_tokens": 100,
            "output_tokens": 50,
            "duration_s": 5.0,
            "model": "m",
        },
        {
            "ts": "10:00:02",
            "context": "pass1 batch 2/4",
            "input_tokens": 200,
            "output_tokens": 80,
            "duration_s": 7.0,
            "model": "m",
        },
        {
            "ts": "10:01:00",
            "context": "pass2 chunk extraction",
            "input_tokens": 300,
            "output_tokens": 120,
            "duration_s": 10.0,
            "model": "m",
        },
        {
            "ts": "10:02:00",
            "context": "schema_harmonize call",
            "input_tokens": 500,
            "output_tokens": 200,
            "duration_s": 40.0,
            "model": "m",
        },
    ]
    llm_log.write_text("\n".join(json.dumps(r) for r in records))

    result = _section_llm_stats(session)
    assert "Pass 1 batch induction" in result
    assert "Instance extraction (Pass 2)" in result
    assert "Schema harmonization" in result
    # Total row should show 4 calls
    assert "**4**" in result or "4" in result
    # Total input tokens: 100+200+300+500 = 1,100
    assert "1,100" in result


# ---------------------------------------------------------------------------
# 7. test_orphan_remaining_count
# ---------------------------------------------------------------------------


def test_orphan_remaining_count(tmp_path):
    session = tmp_path / "session"
    (session / "intermediate").mkdir(parents=True)

    nodes = [
        {
            "id": "person-alice",
            "type": "Person",
            "confidence": 1.0,
            "attributes": {},
            "source_files": [],
        },
        {
            "id": "person-bob",
            "type": "Person",
            "confidence": 1.0,
            "attributes": {},
            "source_files": [],
        },
        {
            "id": "org-acme",
            "type": "Organization",
            "confidence": 1.0,
            "attributes": {},
            "source_files": [],
        },
    ]
    edge_metadata = {
        "edge-001": {
            "id": "edge-001",
            "type": "works_at",
            "from": "person-alice",
            "to": "org-acme",
            "confidence": 0.9,
            "method": "llm_extraction",
            "attributes": {},
            "source_files": [],
        },
    }

    result = _section_orphan_pass(session, [], nodes, edge_metadata)
    # person-bob is orphaned (not in any edge)
    assert "person-bob" in result
    assert "1" in result  # orphans remaining count


# ---------------------------------------------------------------------------
# 8. test_generate_walkthrough_partial
# ---------------------------------------------------------------------------


def test_generate_walkthrough_partial(tmp_path):
    """generate_walkthrough must not raise when most files are absent."""
    session = tmp_path / "partial_session"
    (session / "intermediate").mkdir(parents=True)
    (session / "output").mkdir(parents=True)

    # Minimal run.log only
    (session / "run.log").write_text(
        "10:00:00 [INFO] mykg.cli — LLM endpoint: openrouter / test-model\n"
        "10:00:01 [INFO] mykg.orchestrator — RUN  ingest\n"
        "10:00:02 [INFO] mykg.orchestrator — DONE ingest\n"
    )

    result = generate_walkthrough(session)
    assert isinstance(result, str)
    assert "## 1. Final Graph Summary" in result
    assert "## 2. Run Overview" in result
    assert "## 3. Step Timeline" in result
    assert "## 4. Schema Evolution" in result
    assert "## 5. LLM Call Statistics" in result
    assert "## 6. Extraction Summary" in result
    assert "## 7. Orphan Pass Summary" in result
    assert "## 8. Warnings & Retries" in result


# ---------------------------------------------------------------------------
# 9. test_warnings_section
# ---------------------------------------------------------------------------


def test_warnings_section(tmp_path):
    log_path = tmp_path / "run.log"
    log_path.write_text(
        "10:00:00 [INFO] mykg.cli — Normal startup\n"
        "10:00:05 [WARNING] mykg.pass2 — chunk 3 — validation errors: ['bad type'] — retrying\n"
        "10:00:10 [ERROR] mykg.orchestrator — FAILED pass2 — timeout\n"
        "10:00:15 [INFO] mykg.pass2 — 65_HS1.md — total: 5 node(s), 3 edge(s)\n"
        "10:00:20 [WARNING] mykg.pass2 — 65_HS1.md — dropping edge a→b (dangling after dedup)\n"
    )
    lines = _parse_log_lines(log_path)
    result = _section_warnings(lines)

    assert "## 8. Warnings & Retries" in result
    # INFO lines must NOT appear
    assert "Normal startup" not in result
    assert "total: 5 node" not in result
    # WARNING and ERROR lines must appear
    assert "validation errors" in result
    assert "FAILED" in result
    assert "dropping edge" in result
    # Grouped correctly
    assert "Chunk Errors & Retries" in result
    assert "Dangling Edges" in result
