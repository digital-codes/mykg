from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import Field

from mykg.orchestrator import PipelineContext


class MergeContext(PipelineContext):
    """PipelineContext extended with merge-graphs-specific fields.

    All standard pipeline step functions (run_assemble, run_validate_graph,
    run_schema_validate, run_human_review, run_schema_flatten) accept
    PipelineContext and work unchanged with MergeContext via Pydantic subclassing.

    Merge-only runtime fields are populated by the merge steps:
      - merge_setup      → session_a, session_b, source_map
      - merge_schema     → synonym_log
      - merge_reextract  → schema_delta_a, schema_delta_b
    """

    session_a_name: str
    session_b_name: str
    sessions_root: Path

    # Runtime fields populated by merge steps
    session_a: Any | None = None  # SessionData from merger.load_session
    session_b: Any | None = None  # SessionData from merger.load_session
    source_map: dict | None = None  # written by merge_setup
    synonym_log: list = Field(default_factory=list)  # written by merge_schema
    schema_delta_a: list = Field(default_factory=list)  # new props absent from session_a
    schema_delta_b: list = Field(default_factory=list)  # new props absent from session_b
