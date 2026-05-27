from __future__ import annotations

from pathlib import Path

from mykg.logging import get
from mykg.merge_context import MergeContext
from mykg.merge_run import run_merge

log = get("mykg.merge_orchestrator")


def run_merge_graphs(
    session_a_name: str,
    session_b_name: str,
    output_dir: Path,
    intermediate_dir: Path,
    adapter,
    thesaurus,
    base_schema: dict | None,
    review: bool,
    sessions_root: Path,
) -> None:
    """Merge two pipeline sessions into a unified knowledge graph.

    Delegates to the step-based merge pipeline (merge_run.run_merge).
    Steps are defined in merge_pipeline.MERGE_STEPS and follow the same
    skip-if-done / retry / state-persistence pattern as the extract-graph pipeline.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    intermediate_dir.mkdir(parents=True, exist_ok=True)

    ctx = MergeContext(
        session_a_name=session_a_name,
        session_b_name=session_b_name,
        sessions_root=sessions_root,
        input_dir=sessions_root,  # not read by merge steps; required by PipelineContext
        output_dir=output_dir,
        intermediate_dir=intermediate_dir,
        adapter=adapter,
        thesaurus=thesaurus,
        base_schema=base_schema,
        review=review,
    )
    run_merge(ctx)
