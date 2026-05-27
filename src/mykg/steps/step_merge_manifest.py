from __future__ import annotations

import json
from datetime import datetime, timezone

from mykg import config as _cfg
from mykg.logging import get
from mykg.merge_context import MergeContext

log = get("mykg.steps.merge_manifest")


def run_merge_manifest(ctx: MergeContext) -> None:
    """Write merge_manifest.json summarising the completed merge run."""
    manifest = {
        "session_a": ctx.session_a_name,
        "session_b": ctx.session_b_name,
        "merged_at": datetime.now(timezone.utc).isoformat(),
        "schema_synonym_log": ctx.synonym_log,
        "reextraction_strategy": _cfg.MERGE_GRAPHS_REEXTRACTION_STRATEGY,
        "schema_delta_session_a": ctx.schema_delta_a,
        "schema_delta_session_b": ctx.schema_delta_b,
    }
    (ctx.intermediate_dir / "merge_manifest.json").write_text(
        json.dumps(manifest, indent=_cfg.JSON_INDENT), encoding="utf-8"
    )
    log.info("merge_manifest — written")
