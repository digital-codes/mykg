from __future__ import annotations

import json

from mykg import config as _cfg
from mykg.logging import get
from mykg.merge_context import MergeContext
from mykg.merger import compute_schema_delta, namespace_raw_extractions, reextract_for_merge

log = get("mykg.steps.merge_reextract")

_SENTINEL = "merge_reextract.done"


def run_merge_reextract(ctx: MergeContext) -> None:
    """Re-extract files from each session whose schema now has new properties.

    Strategy is read from mykg_config.yaml → merge_graphs.reextraction_strategy:
      none     — skip; use original extractions as-is
      surgical — re-extract only files where new properties are absent
      full     — re-extract all files from both sessions

    Reads:   session shards in intermediate_dir, flattened_schema.json, schema.json
    Writes:  updated shards in intermediate_dir, merge_reextract.done (sentinel)
    Populates: ctx.schema_delta_a, ctx.schema_delta_b
               ctx.session_a.raw_extractions, ctx.session_b.raw_extractions (namespaced)
    """
    if ctx.session_a is None or ctx.session_b is None:
        raise RuntimeError(
            "merge_reextract requires session_a and session_b on context — "
            "run merge_setup first"
        )

    strategy = _cfg.MERGE_GRAPHS_REEXTRACTION_STRATEGY
    log.info("merge_reextract — strategy=%s", strategy)

    merged_schema = json.loads(
        (ctx.intermediate_dir / "schema.json").read_text(encoding="utf-8")
    )
    flattened = json.loads(
        (ctx.intermediate_dir / "flattened_schema.json").read_text(encoding="utf-8")
    )

    raw_a = namespace_raw_extractions(ctx.session_a.raw_extractions, "session_a")
    raw_b = namespace_raw_extractions(ctx.session_b.raw_extractions, "session_b")

    delta_a = compute_schema_delta(ctx.session_a.schema, merged_schema)
    delta_b = compute_schema_delta(ctx.session_b.schema, merged_schema)

    raw_a = reextract_for_merge(
        "session_a",
        ctx.session_a.path,
        raw_a,
        merged_schema,
        flattened,
        ctx.intermediate_dir,
        ctx.adapter,
        {},
        strategy,
        original_schema=ctx.session_a.schema,
    )
    raw_b = reextract_for_merge(
        "session_b",
        ctx.session_b.path,
        raw_b,
        merged_schema,
        flattened,
        ctx.intermediate_dir,
        ctx.adapter,
        {},
        strategy,
        original_schema=ctx.session_b.schema,
    )

    # Stash namespaced (and possibly re-extracted) raw dicts on context for merge_raw
    ctx.session_a.raw_extractions = raw_a
    ctx.session_b.raw_extractions = raw_b

    ctx.schema_delta_a = sorted(delta_a)
    ctx.schema_delta_b = sorted(delta_b)

    (ctx.intermediate_dir / _SENTINEL).write_text("done", encoding="utf-8")
    log.info("merge_reextract — complete")
