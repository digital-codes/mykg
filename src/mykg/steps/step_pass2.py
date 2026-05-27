from __future__ import annotations

import json

from mykg import config as _cfg
from mykg.logging import get
from mykg.orchestrator import PipelineContext
from mykg.pass2 import run_pass2, run_pass2_batched
from mykg.pass2_concat import build_concat_batches, make_virtual_files
from mykg.schema_flattener import flatten_schema

log = get("mykg.steps.pass2")


def _fname_slug(fname: str) -> str:
    return fname.replace("/", "_").replace("\\", "_").replace(" ", "_")


def run_schema_flatten(ctx: PipelineContext) -> None:
    schema = json.loads((ctx.intermediate_dir / "schema.json").read_text())
    flat = flatten_schema(schema)
    (ctx.intermediate_dir / "flattened_schema.json").write_text(
        json.dumps(flat, indent=_cfg.JSON_INDENT)
    )
    log.info("Step 5 — flattened %d concept(s)", len(flat))


def _load_manifest(ctx: PipelineContext) -> dict[str, str]:
    if ctx.file_contents is not None:
        return ctx.file_contents
    manifest_path = ctx.intermediate_dir / "file_manifest.json"
    if manifest_path.exists():
        raw = json.loads(manifest_path.read_text())
        ctx.file_contents = raw
        log.info("Step 6 — restored file_contents from file_manifest.json (%d file(s))", len(raw))
        return raw
    raise RuntimeError(
        "file_contents is None and intermediate/file_manifest.json not found — "
        "re-run from the ingest step."
    )


def _content_from_entry(entry: str | dict) -> str:
    return entry["content"] if isinstance(entry, dict) else entry


def run_pass2_step(ctx: PipelineContext) -> None:
    manifest = _load_manifest(ctx)
    schema = json.loads((ctx.intermediate_dir / "schema.json").read_text())
    flat = json.loads((ctx.intermediate_dir / "flattened_schema.json").read_text())
    _run(ctx, manifest, schema, flat)


def _run(
    ctx: PipelineContext,
    manifest: dict,
    schema: dict,
    flat: dict,
) -> None:
    raw_path = ctx.intermediate_dir / "raw_extractions.json"
    chunk_path = ctx.intermediate_dir / "chunk_node_index.json"

    shard_dir = ctx.intermediate_dir / "raw_extractions_shards"
    chunk_shard_dir = ctx.intermediate_dir / "chunk_index_shards"

    existing_raw: dict = {}
    existing_chunk: dict = {}

    if shard_dir.exists():
        for shard_file in shard_dir.glob("*.json"):
            shard_content = json.loads(shard_file.read_text())
            existing_raw[shard_content["_fname"]] = shard_content["data"]
        for shard_file in chunk_shard_dir.glob("*.json") if chunk_shard_dir.exists() else []:
            shard_content = json.loads(shard_file.read_text())
            existing_chunk[shard_content["_fname"]] = shard_content["data"]
        log.debug("Step 6 — loaded %d shard(s) from %s", len(existing_raw), shard_dir)
    elif raw_path.exists():
        existing_raw = json.loads(raw_path.read_text())
        existing_chunk = json.loads(chunk_path.read_text()) if chunk_path.exists() else {}

    concat_map_path = ctx.intermediate_dir / "pass2_concat_map.json"
    concat_map: dict[str, dict] = (
        json.loads(concat_map_path.read_text())
        if _cfg.PASS2_PREP_MODE == "concat" and concat_map_path.exists()
        else {}
    )

    if ctx.append and ctx.append_new_files is not None:
        todo = {f: _content_from_entry(manifest[f]) for f in ctx.append_new_files if f in manifest}
    else:
        todo = {f: _content_from_entry(e) for f, e in manifest.items()}

    skip = set(existing_raw.keys())
    todo = {f: c for f, c in todo.items() if f not in skip}

    log.info(
        "Step 6 — %d file(s) already done, %d remaining",
        len(skip),
        len(todo),
    )

    if _cfg.PASS2_PREP_MODE == "concat" and todo:
        concat_map = build_concat_batches(todo, _cfg.PASS2_CONCAT_BATCH_TOKEN_TARGET)
        todo = make_virtual_files(todo, concat_map)
        concat_map_path.write_text(json.dumps(concat_map, indent=_cfg.JSON_INDENT))
        log.info(
            "Step 6 — concat: %d real file(s) → %d virtual batch(es)",
            sum(len(e["files"]) for e in concat_map.values()),
            len(todo),
        )

    # Surgical re-extraction: when schema_hints are present and shards already exist,
    # only re-run the specific chunks named in shared_chunks rather than all files.
    # This avoids paying full re-extraction cost on every schema-gap restart.
    hints = ctx.schema_hints or []
    reextract_chunks: dict[str, set[int]] | None = None
    if hints and existing_raw:
        reextract_chunks = {}
        for h in hints:
            for ck in h.get("shared_chunks", []):
                # chunk_key format: "filename::chunk_idx" (1-based)
                parts = ck.rsplit("::", 1)
                if len(parts) == 2:
                    fname, idx_str = parts
                    if fname in existing_raw:
                        reextract_chunks.setdefault(fname, set()).add(int(idx_str))
        if reextract_chunks:
            if concat_map:
                real_contents = {f: _content_from_entry(manifest[f]) for f in manifest}
                virtual_contents = make_virtual_files(real_contents, concat_map)
                manifest = {**manifest, **virtual_contents}
            affected = {
                f: _content_from_entry(manifest[f]) for f in reextract_chunks if f in manifest
            }
            log.info(
                "Step 6 — schema-gap surgical re-extraction: %d file(s), chunks %s",
                len(affected),
                {f: sorted(idxs) for f, idxs in reextract_chunks.items()},
            )
            shard_dir.mkdir(exist_ok=True)
            chunk_shard_dir.mkdir(exist_ok=True)

            def _on_file_done_surgical(fname: str, result: dict, file_idx: dict) -> None:
                existing_raw[fname] = result
                existing_chunk[fname] = file_idx
                slug = _fname_slug(fname)
                (shard_dir / f"{slug}.json").write_text(
                    json.dumps({"_fname": fname, "data": result}, indent=_cfg.JSON_INDENT)
                )
                (chunk_shard_dir / f"{slug}.json").write_text(
                    json.dumps({"_fname": fname, "data": file_idx}, indent=_cfg.JSON_INDENT)
                )

            new_raw, new_chunk, _failed = run_pass2(
                affected,
                schema,
                flat,
                ctx.adapter,
                max_workers=ctx.pass2_workers,
                schema_hints=hints,
                on_file_done=_on_file_done_surgical,
                error_gate=ctx.error_gate,
                reextract_chunks=reextract_chunks,
                prior_extractions=existing_raw,
                prior_chunk_index=existing_chunk,
            )
            existing_raw.update(new_raw)
            existing_chunk.update(new_chunk)
            _log_and_write(ctx, existing_raw, existing_chunk)
            return

    if not todo:
        _log_and_write(ctx, existing_raw, existing_chunk)
        return

    shard_dir.mkdir(exist_ok=True)
    chunk_shard_dir.mkdir(exist_ok=True)

    def _on_file_done(fname: str, result: dict, file_idx: dict) -> None:
        existing_raw[fname] = result
        existing_chunk[fname] = file_idx
        slug = _fname_slug(fname)
        (shard_dir / f"{slug}.json").write_text(
            json.dumps({"_fname": fname, "data": result}, indent=_cfg.JSON_INDENT)
        )
        (chunk_shard_dir / f"{slug}.json").write_text(
            json.dumps({"_fname": fname, "data": file_idx}, indent=_cfg.JSON_INDENT)
        )

    if _cfg.PASS2_PREP_MODE == "batch_chunks":
        new_raw, new_chunk, _failed, batch_map = run_pass2_batched(
            todo,
            schema,
            flat,
            ctx.adapter,
            batch_token_target=_cfg.PASS2_BATCH_TOKEN_TARGET,
            per_file=_cfg.PASS2_BATCH_PER_FILE,
            max_workers=ctx.pass2_workers,
            schema_hints=ctx.schema_hints or None,
            on_file_done=_on_file_done,
            error_gate=ctx.error_gate,
            intermediate_dir=ctx.intermediate_dir,
            batch_retry_max=_cfg.PASS2_BATCH_RETRY_MAX,
        )
        (ctx.intermediate_dir / "pass2_batch_map.json").write_text(
            json.dumps(batch_map, indent=_cfg.JSON_INDENT)
        )
        log.info(
            "Step 6 — batch map: %d batch(es) written to pass2_batch_map.json",
            len(batch_map),
        )
    else:
        new_raw, new_chunk, _failed = run_pass2(
            todo,
            schema,
            flat,
            ctx.adapter,
            max_workers=ctx.pass2_workers,
            schema_hints=ctx.schema_hints or None,
            on_file_done=_on_file_done,
            skip_files=skip,
            error_gate=ctx.error_gate,
        )

    existing_raw.update(new_raw)
    existing_chunk.update(new_chunk)
    _log_and_write(ctx, existing_raw, existing_chunk)


def _log_and_write(
    ctx: PipelineContext,
    raw: dict,
    chunk_node_index: dict,
) -> None:
    total_nodes = sum(len(v.get("nodes", [])) for v in raw.values())
    total_edges = sum(len(v.get("edges", [])) for v in raw.values())
    _log = log.warning if total_nodes == 0 and total_edges == 0 else log.info
    _log("Step 6 — extracted %d node(s), %d edge(s) (raw, total)", total_nodes, total_edges)
    (ctx.intermediate_dir / "raw_extractions.json").write_text(
        json.dumps(raw, indent=_cfg.JSON_INDENT)
    )
    (ctx.intermediate_dir / "chunk_node_index.json").write_text(
        json.dumps(chunk_node_index, indent=_cfg.JSON_INDENT)
    )
    (ctx.intermediate_dir / "raw_extractions.done").write_text("")
    ctx.raw_extractions = raw
    ctx.chunk_node_index = chunk_node_index
