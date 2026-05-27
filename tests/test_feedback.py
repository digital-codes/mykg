import json
from unittest.mock import MagicMock

import pytest

from mykg.feedback import _fix_normalization, _fix_schema, apply
from mykg.orchestrator import PipelineContext


def _make_ctx(tmp_path):
    ctx = PipelineContext(
        input_dir=tmp_path / "input",
        output_dir=tmp_path / "output",
        intermediate_dir=tmp_path / "intermediate",
        adapter=MagicMock(),
        base_schema=None,
        thesaurus=None,
        review=False,
    )
    ctx.intermediate_dir.mkdir(parents=True, exist_ok=True)
    ctx.output_dir.mkdir(parents=True, exist_ok=True)
    return ctx


def test_feedback_schema_validate_writes_corrected_schema(tmp_path):
    ctx = _make_ctx(tmp_path)
    bad_schema = {"concepts": [], "properties": []}
    (ctx.intermediate_dir / "schema.json").write_text(json.dumps(bad_schema))

    corrected = {
        "concepts": [{"type": "Person", "parent": None, "attributes": ["name"]}],
        "properties": [],
    }
    ctx.adapter.complete.return_value = json.dumps(corrected)

    apply("schema_validate", "rdfs:range Foo is not declared", ctx)

    result = json.loads((ctx.intermediate_dir / "schema.json").read_text())
    assert result["concepts"][0]["type"] == "Person"
    assert (ctx.intermediate_dir / "schema.ttl").exists()


def test_feedback_unknown_step_logs_advisory(tmp_path):
    ctx = _make_ctx(tmp_path)
    # Should not raise — unknown steps get advisory log only
    apply("assemble", "some dedup error", ctx)


def test_feedback_pass1_writes_corrected_schema(tmp_path):
    ctx = _make_ctx(tmp_path)
    corrected = {
        "concepts": [{"type": "Org", "parent": None, "attributes": ["name"]}],
        "properties": [],
    }
    ctx.adapter.complete.return_value = json.dumps(corrected)

    apply("pass1", "JSON parse error", ctx)

    result = json.loads((ctx.intermediate_dir / "schema.json").read_text())
    assert result["concepts"][0]["type"] == "Org"


def test_feedback_ttl_validate_is_advisory_only(tmp_path):
    # TTL errors are advisory per D25; no LLM correction handler is registered.
    ctx = _make_ctx(tmp_path)
    bad_ttl = '@prefix ex: <http://mykg.local/schema/> .\ndata:bad,id ex:name "test" .'
    (ctx.output_dir / "knowledge_graph.ttl").write_text(bad_ttl)

    apply("ttl_validate", "Bad syntax at line 2", ctx)

    # File must be unchanged — no handler fires
    assert (ctx.output_dir / "knowledge_graph.ttl").read_text() == bad_ttl
    ctx.adapter.complete.assert_not_called()


def test_feedback_normalize_names_writes_corrected_map(tmp_path):
    ctx = _make_ctx(tmp_path)
    original = {
        "metadata": {
            "generated_at": "2026-01-01T00:00:00+00:00",
            "aliases_mapped": 0,
            "input_name_count_by_type": {},
        },
        "mappings": {"Person": {"Alice": "WRONG"}},
    }
    (ctx.intermediate_dir / "name_normalization.json").write_text(json.dumps(original))

    corrected_mappings = {
        "metadata": {
            "generated_at": "2026-01-01T00:00:00+00:00",
            "aliases_mapped": 1,
            "input_name_count_by_type": {},
        },
        "mappings": {"Person": {"Alice": "Alice Smith"}},
    }
    ctx.adapter.complete.return_value = json.dumps(corrected_mappings)

    apply("normalize_names", "canonical 'WRONG' not in inventory", ctx)

    result = json.loads((ctx.intermediate_dir / "name_normalization.json").read_text())
    assert result["mappings"]["Person"]["Alice"] == "Alice Smith"


def test_feedback_normalize_names_no_existing_file(tmp_path):
    ctx = _make_ctx(tmp_path)
    corrected = {"metadata": {}, "mappings": {}}
    ctx.adapter.complete.return_value = json.dumps(corrected)

    # Should not raise even if name_normalization.json doesn't exist yet
    apply("normalize_names", "some error", ctx)

    assert (ctx.intermediate_dir / "name_normalization.json").exists()


def test_feedback_apply_returns_true_when_handler_runs(tmp_path):
    """apply() must return True when a registered handler executes."""
    ctx = _make_ctx(tmp_path)
    corrected = {"concepts": [], "properties": []}
    ctx.adapter.complete.return_value = json.dumps(corrected)

    result = apply("schema_validate", "some rdfs error", ctx)
    assert result is True


def test_feedback_apply_returns_false_for_unknown_step(tmp_path):
    """apply() must return False when no handler is registered for the step."""
    ctx = _make_ctx(tmp_path)

    result = apply("pass2", "extraction failed", ctx)
    assert result is False


def test_fix_schema_raises_on_bad_structure(tmp_path):
    """_fix_schema must raise ValueError when LLM returns valid JSON but wrong shape."""
    ctx = _make_ctx(tmp_path)
    (ctx.intermediate_dir / "schema.json").write_text(
        json.dumps({"concepts": [], "properties": []})
    )
    ctx.adapter.complete.return_value = json.dumps({"error": "cannot fix"})

    with pytest.raises(ValueError, match="invalid schema structure"):
        _fix_schema("some rdfs error", ctx)

    result = json.loads((ctx.intermediate_dir / "schema.json").read_text())
    assert "concepts" in result


def test_fix_normalization_raises_on_bad_structure(tmp_path):
    """_fix_normalization must raise ValueError when LLM returns valid JSON but wrong shape."""
    ctx = _make_ctx(tmp_path)
    original = {"metadata": {}, "mappings": {"Person": {"Alice": "Alice Smith"}}}
    (ctx.intermediate_dir / "name_normalization.json").write_text(json.dumps(original))
    ctx.adapter.complete.return_value = json.dumps({"result": "ok"})

    with pytest.raises(ValueError, match="invalid normalization structure"):
        _fix_normalization("some normalization error", ctx)

    result = json.loads((ctx.intermediate_dir / "name_normalization.json").read_text())
    assert result["mappings"]["Person"]["Alice"] == "Alice Smith"


def test_orchestrator_llm_correction_false_when_no_handler(tmp_path):
    """pipeline_state.json must not record llm_correction_applied=True when no handler ran."""
    import json as _json

    import pytest

    from mykg.orchestrator import PipelineContext, PipelineHaltError, Step, run

    ctx = PipelineContext(
        input_dir=tmp_path / "input",
        output_dir=tmp_path / "output",
        intermediate_dir=tmp_path / "intermediate",
        adapter=MagicMock(),
        base_schema=None,
        thesaurus=None,
        review=False,
    )
    ctx.intermediate_dir.mkdir(parents=True, exist_ok=True)
    ctx.output_dir.mkdir(parents=True, exist_ok=True)

    call_count = {"n": 0}

    def always_fails(c):
        call_count["n"] += 1
        raise ValueError("extraction failed")

    # pass2 has no feedback handler — llm_correction must stay False
    steps = [
        Step(name="pass2", fn=always_fails, outputs=["raw_extractions.json"], is_llm_step=True)
    ]

    with pytest.raises(PipelineHaltError):
        run(steps, ctx)

    state = _json.loads((ctx.intermediate_dir / "pipeline_state.json").read_text())
    assert state["errors"]["pass2"]["llm_correction_applied"] is False
