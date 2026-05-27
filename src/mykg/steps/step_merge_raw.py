from __future__ import annotations

import json

from mykg import config as _cfg
from mykg.logging import get
from mykg.merge_context import MergeContext
from mykg.merger import load_session, merge_raw_extractions, namespace_raw_extractions

log = get("mykg.steps.merge_raw")


def run_merge_raw(ctx: MergeContext) -> None:
    """Merge namespaced raw_extractions from both sessions into raw_extractions.json.

    Reads:   ctx.session_a.raw_extractions, ctx.session_b.raw_extractions
             (already namespaced by merge_reextract, or namespace applied here on re-entry)
    Writes:  intermediate/raw_extractions.json
             intermediate/raw_extractions.done  (sentinel)
             intermediate/name_normalization.json  (empty sentinel if absent)
             intermediate/chunk_node_index.json  (namespaced, built from chunk_index_shards/)
    """
    if ctx.session_a is None or ctx.session_b is None:
        log.info(
            "merge_raw — session_a or session_b not on context (cold re-entry); "
            "reloading from disk"
        )
        ctx.session_a = load_session(ctx.session_a_name, ctx.sessions_root)
        ctx.session_b = load_session(ctx.session_b_name, ctx.sessions_root)

    raw_a = ctx.session_a.raw_extractions
    raw_b = ctx.session_b.raw_extractions

    if not any(k.startswith("session_a/") for k in raw_a):
        raw_a = namespace_raw_extractions(raw_a, "session_a")
    if not any(k.startswith("session_b/") for k in raw_b):
        raw_b = namespace_raw_extractions(raw_b, "session_b")

    merged_raw = merge_raw_extractions(raw_a, raw_b)
    (ctx.intermediate_dir / "raw_extractions.json").write_text(
        json.dumps(merged_raw, indent=_cfg.JSON_INDENT), encoding="utf-8"
    )
    (ctx.intermediate_dir / "raw_extractions.done").write_text("done", encoding="utf-8")

    # Assembler reads name_normalization.json if present; write empty sentinel.
    norm_path = ctx.intermediate_dir / "name_normalization.json"
    if not norm_path.exists():
        norm_path.write_text(
            json.dumps({"mappings": {}}, indent=_cfg.JSON_INDENT), encoding="utf-8"
        )

    # merge_setup already copied and namespaced both sessions' chunk_index_shards/
    # (rewriting _fname to "<session_alias>/<original_fname>"); union them here.
    chunk_node_index: dict[str, dict] = {}
    shards_dir = ctx.intermediate_dir / "chunk_index_shards"
    if shards_dir.is_dir():
        for shard_file in sorted(shards_dir.glob("*.json")):
            try:
                shard = json.loads(shard_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                log.warning("merge_raw — could not read chunk index shard %s: %s", shard_file.name, exc)
                continue
            fname = shard.get("_fname")
            data = shard.get("data")
            if not fname or not isinstance(data, dict):
                log.warning("merge_raw — skipping malformed chunk index shard %s", shard_file.name)
                continue
            chunk_node_index[fname] = data

    (ctx.intermediate_dir / "chunk_node_index.json").write_text(
        json.dumps(chunk_node_index, indent=_cfg.JSON_INDENT), encoding="utf-8"
    )
    ctx.chunk_node_index = chunk_node_index
    log.info(
        "merge_raw — merged %d files total; chunk_node_index has %d namespaced file entries",
        len(merged_raw),
        len(chunk_node_index),
    )
