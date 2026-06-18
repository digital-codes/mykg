# Architecture

Last reviewed: 2026-06-11

## System Overview

mykg is a two-pass, LLM-driven knowledge graph extractor. Pass 1 induces an RDFS-compatible
schema (`concepts[]` + `properties[]`) from batched Markdown input; Pass 2 extracts node/edge
instances against that schema, per file, in parallel. An assembler deduplicates and assigns
stable IDs, then an export stage writes four parallel output formats (JSONL, Turtle/OWL,
NetworkX, Neo4j CSV) plus an Obsidian vault and HTML visualization. Every run is isolated inside
a timestamped session folder (`mykg_sessions/<ts>/{input,intermediate,output}`), with
fine-grained intermediate JSON at every stage to support resumable re-entry at multiple points
(D26).

## Architecture Diagram

```
mykg extract-graph <input_dir> [--session NAME] [--review] [--append]
        │
        ▼
[1  preprocess]   non-md sources (PDF/DOCX/images via ephemeral MinerU venv,
                  HTML via in-process markdownify) → input/_preprocessed/*.md
                  + preprocess_manifest.json (SHA-256 change detection, D49)
        │
        ▼
[2  ingest]       rglob *.md → file_manifest.json, chunking (D1/D20)
        │
        ▼
[3  pass1]  (LLM x3) batch induction → merge_proposals → harmonize_schema
                  → review_schema_quality → schema.json + schema.ttl
                  + schema_history/ (D35, D36)
        │
        ▼
[4  schema_validate]  rdflib + custom TBox checks; one LLM correction retry
        │
        ▼
[5  human_review]  optional gate (--review) → schema_approved.flag (D17)
        │
        ▼
[6  schema_flatten]  inheritance flattening (D6) → flattened_schema.json
        │
        ▼
[7  pass2]  (LLM, parallel per file) → raw_extractions_shards/*.json,
            chunk_index_shards/*.json, failed_chunks.json (D33, D37)
        │
        ▼
[8  normalize_names]  (LLM) alias→canonical map → name_normalization.json
        │
        ▼
[9  assemble]  stable IDs (D19) → dedup nodes/edges (D10/D22) →
               edge_metadata.json, nodes.json, merge_log.json
        │
        ▼
[10 orphan_score]   chunk_node_index.json → orphan_candidates.json (D30/D34)
        │
        ▼
[11 orphan_connect]  (LLM) confirm edges per chunk group; may raise
               SchemaUpdatedError → iterative restart from pass2 (D31/D37)
        │
        ▼
[12 validate_graph]  nodes.jsonl, edges.jsonl, knowledge_graph.ttl (+ TTL
               sanitize/validate, D14/D25), networkx_output/, neo4j_csv/,
               obsidian_vault/, knowledge_graph_validation.json
```

Cross-cutting: `orchestrator.py::run` drives `STEPS` via `_is_done`/sentinel re-entry,
three-tier retry+feedback escalation (D31), append-mode invalidation, and the schema-gap
restart loop (D31/D37). `mykg merge-graphs` runs a parallel `MERGE_STEPS` registry that reuses
several extract-pipeline steps.

## Design Decisions

The full authoritative record is CLAUDE.md (D1–D49 + 17 numbered invariants). Decisions most
load-bearing for this review:

- **D3** — provider-agnostic LLM adapter (`LLMAdapter` ABC, `load_adapter` factory); the
  cleanest abstraction in the codebase and the template for any future "fetch adapter."
- **D4/D35** — sequential two-pass pipeline; Pass 1 is itself a 4-stage induction
  (batch → merge → harmonize → quality review), each stage logged to `schema_history/`.
- **D5/D7/D14/D15** — RDFS ontology (concept taxonomy + standard properties), no
  `Relationship` class, edge metadata lives only in `edge_metadata.json` sidecar, TTL stays
  pure RDFS+SKOS.
- **D9/D19** — confidence scores everywhere, `{value, confidence}` envelopes, never-drop-null;
  D19 defines the exact stable-ID format (`<type-prefix>-<name-slug>`) and the
  assemble/validate-export step split.
- **D10/D22** — node/edge dedup keys and confidence-1.0 concatenation merge rule.
- **D17/D27/D28** — human review gate, optional locked base schema, optional SKOS thesaurus
  for synonym resolution.
- **D26/D31/D37** — multi-point re-entry, two-tier correction model, surgical re-extraction on
  schema-gap restarts.
- **D32/D38–D49** — session isolation; the preprocess subsystem (MinerU ephemeral venv,
  HTML→markdown via markdownify, SHA-256 change detection, `source_files` manifest,
  ARG_MAX-safe `--file-list`) — the closest existing analog to a future web-fetch source.
- **Invariants 7/8/12/13/16** — config-driven (no hardcoded values, two-file sync per
  Invariant 17), Pydantic models throughout, ThreadPoolExecutor parallelism everywhere,
  provider rate-limit handling (429 = misconfiguration), and runtime-complexity evaluation for
  new strategies.

## Current State Assessment

The pipeline is functionally complete and the documented invariants are *mostly* enforced in
code — the adapter pattern (D3), TTL purity (D14), and the assemble/export split (D19) are
genuinely solid and well-tested. However, several god-objects/god-modules have accreted around
the original design (`pass2.py` at 828 lines, `exporter.py` at 940 lines, `PipelineContext` at
19 fields, `orchestrator.py::run` mixing generic sequencing with extraction-pipeline-specific
restart logic), and a cluster of validation gaps around dangling edge endpoints, non-Latin
stable IDs, and concurrent sidecar writes mean the system can silently produce
internally-inconsistent "valid" output. None of this blocks a web-fetch feature, but several
of these gaps (especially dangling-endpoint validation and non-Latin ID collisions) become more
likely to be hit once content originates from arbitrary web pages rather than curated notes.

---

## To-Do List

Items are tagged: `[critical]` `[high]` `[medium]` `[low]` and `[done]` when complete.
Add new items at the top. Never delete done items — mark them `[done]` so the history is
preserved.

| # | Priority | Area | Task | Added | Done |
|---|----------|------|------|-------|------|
| 24 | [critical] | Adversarial | Single corrupted Pass2 shard (`raw_extractions_shards/*.json`) crashes the entire pass2 step on re-entry — no per-shard try/except in `step_pass2.py::_run` lines 70-75; add per-shard error isolation (skip + log corrupt shard, don't crash whole step) | 2026-06-11 | — |
| 23 | [critical] | Adversarial | Concurrent pipeline runs corrupt `edge_metadata.json` via last-write-wins read-modify-write with no lock/atomic-write in `step_orphan_connect.py` lines 146-156 | 2026-06-11 | — |
| 22 | [critical] | Adversarial | `_fix_orphan_connect` (feedback.py lines 134-158) writes LLM-corrected dict verbatim to `orphan_connections.json` with only `isinstance(dict)` check — bypasses ALL Stage-2 validation (type/from/to/self-loop/schema checks) and D24's "assembler must validate after every LLM call" | 2026-06-11 | — |
| 21 | [critical] | Adversarial | Non-Latin or symbol-only `name` values collapse to identical stable IDs (`ids.py::_name_slug` strips everything outside `[a-z0-9\s]`) — `deduplicate_nodes` then silently MERGES unrelated entities under e.g. `person-`. Systematic correctness bug for non-English corpora, not just adversarial | 2026-06-11 | — |
| 20 | [critical] | Adversarial | Dangling edge endpoints (from/to not in any node) are invisible to every validator — `assign_stable_ids`'s `_resolve` can fall back to an unresolved string, `deduplicate_edges` doesn't check endpoints, `step_validate_graph` only filters by edge `type`, `export_ttl` emits unconditionally, and `validate_knowledge_graph_ttl`'s ABox checks never visit a subject/object with no `rdf:type` triple — `knowledge_graph_validation.json` reports `"valid": true` despite dangling edges | 2026-06-11 | — |
| 19 | [high] | System | Resolve `_resolve_from_step`/`_delete_from_step` `valid_names` excluding "ingest"/"preprocess" (cli.py ~line 1216) vs D47's documented `--from-step preprocess` — confirm whether `cleanup_converted_outputs` exists or D47 needs correction | 2026-06-11 | — |
| 18 | [high] | System | step_preprocess writes `preprocess_manifest.json` only after all files processed — crash mid-run loses all successful per-file records for that run; switch to incremental manifest writes mirroring the shard pattern | 2026-06-11 | — |
| 17 | [high] | Software | Split `pass2.py` (828 lines, ~10 concerns) into `pass2_prompts.py`, `pass2_validation.py`, and a slimmer `pass2.py` for run/orchestration | 2026-06-11 | — |
| 16 | [high] | Adversarial | Self-loop edges (`from == to`) are never rejected by `validate_extraction` or `confirm_orphan_chunk_groups`/`_process_group` — add explicit `from != to` check at both validation points | 2026-06-11 | — |
| 15 | [high] | Software | `orchestrator.py::run` embeds extraction-pipeline-specific knowledge (schema.json/schema.ttl filenames, inline `export_ttl` import/call at lines 408-420, `_SCHEMA_RESTART_INVALIDATE`) — extract into a dedicated `schema_restart.py` module so the orchestrator stays a generic step-sequencer (helps merge-pipeline reuse too) | 2026-06-11 | — |
| 14 | [medium] | System | `PipelineContext` is a 19-field god-object with no field-ownership grouping; `MergeContext` adds 8 more on top — group "runtime fields populated by steps" (`nodes`, `edge_metadata`, `raw_extractions`, `chunk_node_index`, etc.) and schema-restart fields into nested Pydantic sub-models | 2026-06-11 | — |
| 13 | [medium] | Software | `exporter.py` (940 lines) mixes JSONL/TTL serialization with a ~550-line embedded vis.js HTML/CSS/JS string, NetworkX export, and Obsidian export — extract the HTML visualization into its own module (`exporters/html_viz.py` or static template files via `importlib.resources`) | 2026-06-11 | — |
| 12 | [medium] | Software | `_coerce_attr` (assembler.py) and `pass2._normalize_scalars`/`_backfill_extraction` independently implement overlapping `{value, confidence}` envelope-coercion with different fallback constants (`CONFIDENCE_FALLBACK` vs `CONFIDENCE_SCALAR_OMITTED`) — consolidate into one shared function/module with a documented contract | 2026-06-11 | — |
| 11 | [medium] | Software | `step_validate_graph.run_validate_graph` keeps growing with inline `if config_flag:` blocks for each optional export (Obsidian, Neo4j CSV, NetworkX) — introduce an `OUTPUT_EXPORTERS` registry (config_flag, export_fn) pairs that the function iterates over, making future export formats additive | 2026-06-11 | — |
| 10 | [medium] | Software | `synonym_match` (schema_merge.py lines 25-33) collapses D28's 4-level priority (exact / normalized / skos:exactMatch / skos:closeMatch) into one boolean; refactor to return an enum so exactMatch precedence is explicit and `merge_log.json` can record the actual match tier | 2026-06-11 | — |
| 9 | [medium] | Software | Add Invariant-5 ("no Relationship class") and "no relation_type field" checks to `base_schema.py::parse_base_schema`, mirroring the check already in `schema_merge.py::merge_proposals` — currently a `--base-schema` TTL with a `Relationship` class would be locked in unchecked | 2026-06-11 | — |
| 8 | [medium] | Adversarial | Top-level node/edge `confidence` is never clamped to [0,1] in `deduplicate_nodes`/`deduplicate_edges` (only attribute-level via `_coerce_attr`) — a confidence > 1.0 always passes `>= threshold` filters | 2026-06-11 | — |
| 7 | [medium] | Adversarial | `_load_prior_manifest` (step_preprocess.py lines 49-57) and similar `json.loads` call sites silently swallow `JSONDecodeError`/`OSError` as "no prior state" — corrupt manifest triggers full costly re-conversion with only an INFO log as signal; consider distinguishing "absent" from "corrupt" | 2026-06-11 | — |
| 6 | [medium] | Adversarial | `_copy_input_files` follows symlinks via `shutil.copy2`/`is_file()` — a `.md`-suffixed symlink to a file outside `input_dir` (e.g. `/etc/passwd`) gets its target content copied into `session/input/` | 2026-06-11 | — |
| 5 | [medium] | Adversarial | `--session <name>` with a different `input_dir` additively contaminates an existing session — `_copy_input_files` doesn't clear `session/input/` first; mixing two corpora into one session's schema with no warning | 2026-06-11 | — |
| 4 | [low] | Adversarial | `synonym_match` false-positive collapses (D21/D28) cascade silently into Pass2 extraction merging semantically-different entities sharing a name — only mitigated when `--review` is used (opt-in) | 2026-06-11 | — |
| 3 | [low] | Adversarial | Extremely long `name` values (10k+ chars) produce unbounded stable IDs used as dict keys, TTL local names, CSV values, and Obsidian filenames — risk of `OSError ENAMETOOLONG` on Obsidian export (non-blocking per D19 but inconsistent partial output) | 2026-06-11 | — |
| 2 | [low] | System | `step_preprocess` 3-layer subprocess nesting (pipeline → `mykg parse-docs` → ephemeral venv `mineru`) has no shared progress channel and output isn't captured into `run.log` — violates the spirit of Invariant 11 | 2026-06-11 | — |
| 1 | [low] | System | `human_review` gate (`ctx.review`) is per-invocation, not persisted per-session — re-entry after a manual schema edit can silently bypass D17's intended gate | 2026-06-11 | — |

---

## Change Log

Track architectural changes here as they are made. Each entry should say what changed and why.

| Date | Change | Reason |
|------|--------|--------|
| 2026-06-11 | Created `architecture.md` via `/design-architecture` review | First run of the architecture-review skill; established baseline to-do list and findings ahead of a possible web-fetch feature |

---

## Subagent Findings (latest review)

### System Architect

**Strengths:**
- `pipeline.py::STEPS` is a genuine single source of truth for step ordering.
- `_is_done` + sentinel files give cheap, working re-entry for most steps.
- Shard-based Pass2 resumability (`raw_extractions_shards/`, `chunk_index_shards/`) is the
  primary and effective resumability mechanism (Invariant 10).
- The schema-gap restart loop (orchestrator.py 286-467) is iterative (not recursive) and
  capped by `ORPHAN_SCHEMA_MAX_RESTARTS` — a correct, bounded design per Invariant 16.
- D3's LLM adapter abstraction is thin and genuinely swappable.
- `step_preprocess`'s D49 change-detection logic is well-isolated from the rest of the
  pipeline.
- Session isolation (D32) is enforced at the CLI boundary, not scattered.
- The three-tier error handling + `ErrorGate` (Invariant 13) is a coherent design.

**Issues:**
1. `step_preprocess` issues a single subprocess covering many files but writes
   `preprocess_manifest.json` only at the end — a crash on file 50/100 loses all 49 successful
   records (→ to-do #18).
2. `_resolve_from_step`/`_delete_from_step`'s `valid_names` (cli.py ~line 1216) excludes
   "ingest" and "preprocess", contradicting D47's documented `--from-step preprocess`;
   `cleanup_converted_outputs` referenced by D47 was not found — possible doc/code drift
   (→ to-do #19).
3. `PipelineContext` is a "God object" with no field-ownership boundaries (→ to-do #14).
4. D26's "four re-entry points" are really 7+ distinct behaviors with no unified interface.
5. `_delete_from_step`'s shard-clearing has a hardcoded asymmetry vs `--append`'s selective
   re-extraction, not cross-referenced in D26.
6. The `human_review` gate (`ctx.review`) is per-invocation, not per-session — re-entry can
   silently bypass D17 (→ to-do #1).
7. `step_preprocess`'s 3-layer subprocess nesting has no shared progress channel; output isn't
   captured into `run.log` (Invariant 11 spirit violation) (→ to-do #2).

**Recommended changes:**
- Incremental manifest writes mirroring the shard pattern.
- Resolve the D47/cli.py `--from-step preprocess` contradiction.
- Split `PipelineContext` into `RunConfig` (immutable) + `RunState` (mutable).
- Add `mykg reenter` / `--explain-reentry` helper.
- Capture preprocess subprocess output into `run.log` via `capture_output=True`.

**Web-Fetch Feature: Architectural Integration Recommendations**

- **A. New step `fetch` at position 0** (before `preprocess`): pipeline becomes
  `fetch → preprocess → ingest → ...`. `step_fetch.run_fetch` reads a URL list, performs HTTP
  GET (redirects, timeout, configurable User-Agent, robots.txt check), writes raw bodies to
  `input/_fetched/<slug>.<ext>` (mirrors D41's `_preprocessed` subdir convention). HTML/PDF
  responses flow into existing D44/D40 routing unchanged — D39-D49 format-conversion machinery
  untouched.
- **B. New manifest `intermediate/fetch_manifest.json`**, NOT an extension of
  `preprocess_manifest.json["source_files"]` — keyed by URL (not path), with
  `{url, fetched_at, etag, last_modified, content_sha256, status_code, output_path,
  content_type}`. New 4th state beyond local files: "unreachable this run" vs "404/removed" vs
  "200 unchanged" vs "200 changed".
- **C. CLI surface**: `mykg fetch-docs --urls <url> [...] | --url-list <file> --output <dir>`
  (standalone, mirrors `parse-docs`); `extract-graph <input_dir> --urls <url> [...] |
  --url-list <file>` (pipeline entry, `input_dir` still required, URLs additional source
  materialized into `session/input/_fetched/`). Do NOT make `mykg fetch <url>` a separate
  top-level verb with its own session type.
- **D. New network-specific concerns with no D39-D49 analog:**
  1. Rate limiting/politeness — per-host concurrency limits/delay, new config
     `fetch.max_workers`, `fetch.per_host_delay_seconds`, `fetch.max_concurrent_per_host`.
  2. robots.txt/ToS — check+respect by default, configurable opt-out, record decision per URL
     in `fetch_manifest.json`.
  3. Re-fetch staleness policy — conditional requests (If-None-Match/If-Modified-Since),
     fallback `fetch.max_age_seconds`.
  4. Auth — `fetch.auth_profiles` mapping host patterns to header sets, secrets in
     `.env.mykg` per Invariant 7.
  5. Partial-failure re-entry — `intermediate/failed_fetches.json` following D33's
     `failed_chunks.json` pattern, `fetch` step `blocking=False`, "Re-entry E — fetch errors"
     in D26's table.
  6. Provenance — `source_files` should record original URL not local
     `_fetched/<slug>.html` path, via `fetch_manifest.json` join.
  7. Whole-site crawling is a SEPARATE feature from "list of URLs" — scope as a follow-on.

```
mykg extract-graph <input_dir> --url-list urls.txt --session my-session
          │
          ▼
   [fetch]  → input/_fetched/*.{html,pdf,...}, intermediate/fetch_manifest.json,
              intermediate/failed_fetches.json (non-blocking)
          │
          ▼
   [preprocess]  → unchanged (D39-D49) — _fetched/ content flows through the
                    existing HTML/MinerU routing exactly like local files
          │
          ▼
   [ingest] → [pass1] → ... → [assemble] (provenance: URL, not local path)
```

**Open Questions:**
1. Is `--from-step preprocess` actually supported today?
2. How does the `human_review` gate behave across re-entry after a manual schema edit?
3. Team policy on robots.txt/ToS compliance for fetch?
4. Fetched content "live"/auto-staleness vs "snapshot once, manual re-fetch"?
5. Should `mykg fetch-docs` create session state or be pure file-to-file like `parse-docs`
   (shared `fetcher.py` module question)?
6. ARG_MAX consideration for `--url-list` vs `--urls` repeatable flag — mandate `--url-list`
   as primary?

---

### Software Architect

**Strengths:**
1. D3's LLM adapter interface (`src/mykg/llm/adapter.py`) is a minimal `ABC` (`complete`,
   `endpoint_label` + shared `strip_code_fences`); every adapter implements only this surface,
   `load_adapter` is the single factory dispatch point. Adding a 6th provider needs zero
   pipeline-logic changes — a textbook adapter pattern.
2. `step_assemble.py`/`step_validate_graph.py` map cleanly onto D19's algorithm steps 1-9 in
   order, each gated by its own config flag.
3. `assembler.py` is pure and side-effect-free (`assign_stable_ids`, `deduplicate_nodes`,
   `deduplicate_edges`, `_coerce_attr`) — trivially unit-testable, and is.
4. Confidence-envelope normalization is centralized in `_coerce_attr`
   (assembler.py) and `_normalize_scalars`/`_backfill_extraction` (pass2.py) — D9 and
   "never drop missing attributes" are enforced in code.
5. Invariant 5 ("no Relationship class") is actively enforced in
   `schema_merge.py::merge_proposals` with a logged warning on every Pass 1 merge and
   cross-session merge.
6. TTL purity (D14/D15) is enforced by a dedicated sanitizer+validator pair
   (`ttl_validator.py::sanitize_abox_ttl` + `validate_knowledge_graph_ttl`), called from
   `step_validate_graph` before writing `knowledge_graph.ttl`. `export_ttl` structurally cannot
   leak edge metadata into TTL — it never receives confidence/attributes.
7. D18 separation is real: `cli.py::extract_graph` does session bookkeeping + config + adapter
   construction, then a single `run(STEPS, ctx)` call — no `step_*` function is ever called
   directly from `cli.py`. `mykg/__init__.py` exposes a minimal lazy public surface.
8. `edges.jsonl` is provably derived, never hand-edited — `export_edges_jsonl` takes
   `edge_metadata` as its only input.

**Issues:**
1. `pass2.py` (828 lines) is a god-module by accretion: prompt construction, validation,
   normalization/backfill, within-file dedup, degraded-mode recovery, retry orchestration, and
   two top-level run functions all in one file (→ to-do #17).
2. `exporter.py` (940 lines) mixes JSONL/TTL serialization, a ~550-line embedded vis.js
   HTML/CSS/JS string with no syntax checking or test coverage, NetworkX export, and Obsidian
   export (→ to-do #13).
3. `orchestrator.py::run` (200 lines) embeds extraction-pipeline-specific business logic —
   append-mode skip logic, the schema-gap restart loop, and an inline deferred
   `from mykg.exporter import export_ttl` at line 410 — coupling the "generic" orchestrator to
   extraction-pipeline file names/formats (→ to-do #15).
4. `_coerce_attr` (assembler.py) and `pass2._normalize_scalars`/`_backfill_extraction`
   independently implement overlapping `{value, confidence}` envelope-coercion with different
   fallback constants (`CONFIDENCE_FALLBACK` vs `CONFIDENCE_SCALAR_OMITTED`) — no single source
   of truth for "what does a legal attribute value look like" (→ to-do #12).
5. The "no Relationship class" check (Invariant 5) only runs during `merge_proposals`, not
   during schema-gap restarts or `--base-schema` ingestion — `base_schema.py::parse_base_schema`
   appears to lack the equivalent check (→ to-do #9).
6. `step_preprocess.py::run_preprocess` and `cli.py`'s subprocess-spawning logic are the
   hardest code to test — 185-line function mixing filesystem mutation, subprocess invocation,
   and ephemeral-venv lifecycle. The design (D48/D49) is sound; the size of the function makes
   focused testing harder.
7. `PipelineContext` has grown to 19 fields covering paths, adapter, error gate, base schema,
   thesaurus, flags, 6 "runtime fields populated by steps", worker counts, confidence
   aggregation strategy, and schema-restart bookkeeping — no sub-typing/grouping
   (→ to-do #14). `MergeContext` adds 8 more fields on top.
8. `step_validate_graph.run_validate_graph` keeps absorbing new optional export formats
   (Obsidian, Neo4j CSV) as inline `if config_flag:` blocks — its name undersells what it now
   does (→ to-do #11).

**Recommended changes:**
1. Split `pass2.py` into `pass2_prompts.py`, `pass2_validation.py`, and a slimmer
   orchestration-only `pass2.py`.
2. Extract the vis.js HTML generation into `exporters/html_viz.py` (or static template files
   via `importlib.resources`).
3. Move schema-gap restart logic into a dedicated `schema_restart.py` module called via a
   narrow `schema_restart.handle(steps, ctx, state, schema_exc) -> bool`.
4. Consolidate attribute-envelope coercion into a single shared function/module used by both
   `pass2.py` and `assembler.py`, with a documented fallback-constant contract.
5. Add an Invariant-5 (+ "no relation_type field") check to `base_schema.py::parse_base_schema`,
   mirroring `schema_merge.py::merge_proposals`.
6. Introduce an `OUTPUT_EXPORTERS` registry (config_flag, export_fn pairs) that
   `run_validate_graph` iterates over for optional formats — makes a future "Step 12f"
   (e.g. fetch-provenance export) additive rather than another `if` block.
7. Group `PipelineContext`'s runtime-state fields into a nested Pydantic sub-model (e.g.
   `ctx.extraction_state.{nodes, edge_metadata, raw_extractions, chunk_node_index}`) and
   schema-restart fields into `ctx.schema_restart`.

**Open Questions:**
1. Does `base_schema.py::parse_base_schema` already reject a `Relationship`-named class from
   `--base-schema` TTL? Could not confirm.
2. `docs/implementation-alternatives.md` (CLAUDE.md's "Key design document") does not exist
   anywhere under `docs/` — is `src/mykg/prompts.py`/`src/mykg/data/prompts/` the actual
   current source of truth for D24's "full prompt templates"? D24's pointer is dead.
3. Is the `CONFIDENCE_SCALAR_OMITTED` vs `CONFIDENCE_FALLBACK` distinction intentional (two
   distinct epistemic states) or accidental duplication?

**Software-design recommendations for "fetch web resources"**

- **Where it fits:** Treat as a new sibling concern *inside* (or just before)
  `step_preprocess`, NOT a new top-level `STEPS` entry. Preprocess's job (D39-D49) is "convert
  non-Markdown sources into `.md` under `input/<subdir>/` with change detection and
  provenance" — a fetched URL is conceptually identical. Model it as a new source-discovery
  branch parallel to the existing `mineru_files`/`html_files` split from
  `_discover_non_md_files`. `ingest`, chunker, Pass1/2, assembler, exporters remain completely
  unaware content originated from a URL — same "swap the source, not the pipeline" property D3
  gives for LLM providers. A new top-level step would duplicate D39/D47/D49's
  sentinel/manifest/re-entry semantics.

- **New abstractions:**
  1. `WebFetchAdapter` ABC, structurally analogous to `LLMAdapter` —
     `fetch(url, timeout) -> FetchResult` and `to_markdown(result) -> str`. Reuse
     `markdownify` (already used by `_convert_html_files`) for HTML→MD — fetched HTML bodies
     go through the same conversion function, just sourced from HTTP instead of disk.
  2. A `fetch:` block in `mykg_config.yaml` (not a CLI positional list — needs to be
     re-runnable config per Invariant 7):
     ```yaml
     fetch:
       enabled: false
       sources:
         - url: "https://example.com/docs/"
           mode: "single"        # single | sitemap | recursive
           max_depth: 1
         - url: "https://api.example.com/items"
           mode: "api"
           pagination: "cursor"
       timeout_seconds: 30
       max_workers: 4
       user_agent: "mykg/1.0"
       cache_ttl_seconds: 86400
     ```
     Both `mykg_config.yaml` and `src/mykg/data/mykg_config.yaml` must gain this block per the
     Invariant-17 structural-sync rule.
  3. A provenance sidecar `<stem>.fetch.json` analogous to D46's `<stem>.mineru.json`:
     `{source_url, fetched_at, content_hash, http_status, content_type}` — feeds the
     `source_files` change-detection block in `preprocess_manifest.json`, keyed by URL.

- **Change detection (the hard part):** D49 hashes local file bytes; URLs need a different
  signal. Primary: HTTP `ETag`/`Last-Modified` headers stored in the `.fetch.json` sidecar,
  sent as `If-None-Match`/`If-Modified-Since` on re-fetch — a `304` maps to D49's
  "skip — sha matches" branch. Fallback: content-hash of fetched bytes (same
  `_sha256_path`-style streaming) when caching headers are absent, with `rel` being a
  URL-derived key instead of a filesystem path. `cache_ttl_seconds` bounds how often a
  "no-change" URL is even re-checked — without it, every run makes an HTTP request per
  configured URL regardless of D49's optimization spirit.

- **Pitfalls to avoid:**
  - Don't let `run_preprocess` (already 185 lines) grow further — refactor into
    `_process_mineru_sources()` / `_process_html_sources()` / `_process_web_sources()` *before*
    adding web-fetch; this benefits the existing two backends too.
  - Don't spawn a subprocess/ephemeral venv (D48) for web fetching — that pattern exists
    because of MinerU's massive pinned dependency footprint, which doesn't apply to
    `requests`/`httpx` + `markdownify`. Run in-process like `_convert_html_files` already does.
  - Don't conflate fetch failure with blocking pipeline failure — follow D39's
    per-item try/except-and-record pattern exactly; a single unreachable URL must not halt
    `extract-graph`.
  - Respect Invariant 13 for the fetch layer too — a fetch-target 429 is a "back off this
    host" / reduce `fetch.max_workers` signal, not something to retry-loop on. Consider whether
    `ErrorGate` can be generalized rather than building a parallel mechanism — but don't let
    fetch-target 429s trip the *LLM* error gate, since they are unrelated signals.
  - CLI surface: a `mykg fetch-urls` (or similar) standalone command for ad-hoc testing should
    be its own module (`web_fetch.py`) with its own command, not threaded through
    `_build_parse_docs_targets()`/`_PARSE_DOCS_HARDCODED_SKIP`, which are pure local-path-list
    helpers today and would need invasive changes for URL-shaped input.

---

### Data Architect

**Strengths:**
- D7 schema format compliance verified (no `relation_type`, no `Relationship` class — actively
  rejected).
- D22 edge dedup key matches spec exactly (assembler.py line 211, SHA-256, config-driven
  prefix/length).
- D8/D13 sidecar (`edge_metadata.json`) is a genuine single source of truth for edge metadata.
- D9 confidence normalization via `_coerce_attr` (lines 13-50) correctly clamps to [0,1].
- D9 `_backfill_extraction` (pass2.py lines 194-215) correctly enforces never-drop-null +
  confidence 0.0.
- D19/D10 stable ID format matches spec exactly, plus a global ID map + secondary
  name-slug index for cross-file resolution.
- D14 TTL output is clean RDFS+SKOS with no metadata leakage.
- D6 schema flattening occurs at the correct pipeline position with cycle detection.
- D27 base-schema lock semantics are correctly threaded through merge logic.
- D29 aliases are correctly derived at assembly time, gated by `has_aliases`.

**Issues:**
1. `synonym_match` (schema_merge.py lines 25-33) doesn't implement D28's 4-level priority as 4
   distinct checks — combines exactMatch/closeMatch into one boolean; the distinction is
   recovered separately in `_find_match` (lines 122-136), which is fragile if both relations
   are true for the same pair (→ to-do #10).
2. `merge_log.json` synonym-collapse events lack the "thesaurus evidence" required by D21 —
   only logs `{"event": "synonym_collapse", "kept": key, "discarded": name, "reason":
   "skos:closeMatch"}`, no evidence field.
3. nodes.jsonl field shape confirmed correct vs D12 (not an issue, listed for completeness).
4. `_coerce_attr`'s coercion of the FIRST occurrence's attributes (line 124, outside
   winning/losing tracking) is invisible in `merge_log.json` if it fires.
5. Shard-merge logic producing `raw_extractions.json` from shards was not directly reviewed —
   flagged for the team to confirm shard shape matches `assign_stable_ids`'s expectations
   (line 65, KeyError risk if a shard is missing `nodes`/`edges` keys) — overlaps with
   Adversarial finding #24.

**Recommended changes:**
1. Add `thesaurus_source`/`evidence` fields to synonym_collapse log entries.
2. Refactor `synonym_match` to return an enum (`"exact"|"normalized"|"skos_exact"|
   "skos_close"|None`) so exactMatch precedence is explicit per D28's ordering.
3. Add a defensive shard-shape guard in `assign_stable_ids` — validate `nodes`/`edges` keys
   exist and are lists, warn+skip rather than KeyError.

**Web-Fetched Content as a Source: Data Modeling Recommendations**

- **Provenance:** `source_files` stays a list of session-relative paths (NOT URLs) — unchanged
  contract. New sidecar `intermediate/fetch_manifest.json` (parallel to
  `preprocess_manifest.json`), keyed by session-relative path under `input/`:
  ```json
  {
    "source_files": {
      "_fetched/example.com/team.md": {
        "url": "https://example.com/team",
        "final_url": "https://example.com/team/",
        "fetched_at": "2026-06-11T14:32:00Z",
        "content_sha256": "<hex>",
        "http_status": 200,
        "etag": "\"abc123\"",
        "last_modified": "Wed, 10 Jun 2026 09:00:00 GMT",
        "output_md": "_fetched/example.com/team.md"
      }
    }
  }
  ```
  No schema change needed to nodes.jsonl/edges.jsonl/edge_metadata.json — `source_files` is the
  join key into `fetch_manifest.json`, mirroring D46's `.mineru.json` →
  `preprocess_manifest.json` indirection.

- **Session input layout:** `input/_fetched/<host>/<path-derived-stem>.md` (third subdir
  alongside `_preprocessed`); per-host subfolder avoids collisions. `_files_with_extensions`
  should skip `_fetched/` on the source-discovery side, same as `_preprocessed`.

- **Change detection:** extends D49's skip-vs-process model — fetch URL, optionally send
  conditional headers for a fast 304 path, else compute `content_sha256` vs prior manifest
  entry; skip if unchanged AND `output_md` exists. Key difference: a 200-with-unchanged-bytes
  still costs one HTTP request (unavoidable). New config block needs `fetch.enabled`,
  `fetch.timeout_seconds`, `fetch.max_workers` (Invariant 12), `fetch.user_agent`,
  `fetch.respect_robots_txt`, `fetch.max_page_size_bytes`, `fetch.urls` — both
  `mykg_config.yaml` and `src/mykg/data/mykg_config.yaml` per Invariant 17.

- **Deduplication (D10):** dedup key is content-derived not source-derived — ZERO changes
  needed for "same entity on multiple fetched pages" (existing `deduplicate_nodes` handles via
  `source_files` union). Two NEW edge cases at the fetch/preprocess layer (NOT the dedup
  layer):
  1. Redirects to canonical URLs — record both `url` and `final_url`, store content once keyed
     by `final_url`'s path, original `url` as alias. Without this, two URLs redirecting to the
     same page double-fetch/double-process (wasted LLM calls, provenance noise — not a
     node-dedup problem).
  2. Near-duplicate pages (pagination, printer-friendly variants) — D22's edge hash dedupes
     correctly, but this is a COST problem; optional pre-Pass-1 simhash/minhash
     content-similarity pre-filter, opt-in, bounded per Invariant 16 (e.g.
     `fetch.dedup_max_candidates`, compare only within same host/path-prefix).

- **Output formats (D11-D14):** NO new fields needed in nodes.jsonl/edges.jsonl/
  knowledge_graph.ttl. `source_files` is a sufficient join key. RECOMMEND AGAINST adding
  `prov:wasDerivedFrom` triples to TTL for v1 — would multiply ABox triples by
  `len(source_files)` per node and doesn't fit D14's "one direct triple" pattern. If wanted
  later, make it an opt-in TTL section gated by config flag, analogous to the conditional
  `skos:` prefix emission.

**Open Questions:**
1. What's the unit of "a source" for whole-site fetches — flat URL list (v1) vs
   sitemap/crawl-frontier (later, with its own change-detection implications for "orphaned"
   URLs)?
2. Should `mykg fetch-docs` exist standalone, mirroring `parse-docs` (D40 precedent)?
3. Invariant 13's "429 = misconfiguration, don't retry" framing for LLM providers vs routine
   429s/Retry-After from web servers — fetch needs its OWN retry/backoff policy distinct from
   `llm/retry.py`.
4. Does `--append` extend to "re-fetch and append changed pages" with the same per-file
   re-extraction granularity as D33/D37 — should a URL content change invalidate
   `_fetched/<host>/<stem>.md` for `chunk_node_index.json` exactly like an edited local file?
5. Auth/API-key credentials for fetch sources — `fetch.sources[].auth` should reference env
   vars, never literal secrets in `pipeline_config.yaml` (which is checked into the repo per
   Invariant 17).

---

### Adversarial Architect

**Critical Failure Paths** (6 items — existing codebase issues):

1. **Dangling edge endpoints invisible to every validator, ship in all 3 outputs** —
   `assign_stable_ids`'s `_resolve(endpoint)` (assembler.py lines 81-98) can fall back to
   returning an unresolved endpoint string on ambiguous name_slug_index match;
   `deduplicate_edges` doesn't check from/to against node IDs; `step_validate_graph.py` only
   filters by `type ∈ declared_props` (line 25), never endpoint validity; `export_ttl`
   (exporter.py lines 176-179) emits triples unconditionally; `sanitize_abox_ttl`
   (ttl_validator.py lines 18-38) only strips undeclared-PREDICATE lines;
   `validate_knowledge_graph_ttl`'s ABox checks (lines 78-104) only check `rdf:type`
   declarations and predicate declarations — a dangling subject/object with no `rdf:type`
   triple is NEVER visited, ZERO ABox errors. `knowledge_graph_validation.json` reports
   `"valid": true` despite dangling edges. (→ to-do #20)

2. **Self-loop edges (from==to) propagate unchecked** — neither `validate_extraction`
   (pass2.py) nor `confirm_orphan_chunk_groups`/`_process_group` (orphan_connector.py lines
   805-950) check `from != to`. `export_ttl` emits semantically nonsensical self-loop triples;
   NetworkX DiGraph accepts silently; only a SPARQL `SELECT ?p WHERE { ?x ?p ?x }` would
   surface it. (→ to-do #16)

3. **Non-Latin/symbol-only names collapse to identical stable IDs** — `ids.py`'s `_name_slug`
   strips everything outside `[a-z0-9\s]`; a name entirely in Japanese/Arabic/Korean/
   Cyrillic/Greek/Hebrew or entirely punctuation becomes an empty string, so multiple distinct
   entities all produce `"person-"`. `deduplicate_nodes` MERGES unrelated entities per D10's
   confidence-1.0 concatenation rule — silent, systematic correctness bug for non-English
   corpora (not even adversarial). (→ to-do #21)

4. **`_fix_orphan_connect` feedback handler bypasses ALL Stage 2 validation** — feedback.py
   lines 134-158, the third-attempt correction handler writes the LLM's `corrected` dict
   verbatim to `orphan_connections.json` with only `isinstance(corrected, dict)` check — no
   call to `confirm_orphan_chunk_groups`'s validation. step_orphan_connect.py lines 146-156
   then merges this directly into `edge_metadata.json` with no re-check — the single largest
   validation bypass in the codebase, sidesteps D24 and D30 Stage 2 validation entirely.
   (→ to-do #22)

5. **Concurrent pipeline runs corrupt `edge_metadata.json` via last-write-wins** —
   step_orphan_connect.py lines 146-156 read-modify-write with no file lock, no version check,
   no atomic write:
   ```python
   edge_metadata = json.loads(edge_metadata_path.read_text())
   for eid, edge in orphan_connections.items():
       if eid in edge_metadata:
           skipped += 1
           continue
       edge_metadata[eid] = edge
   edge_metadata_path.write_text(json.dumps(edge_metadata, indent=_cfg.JSON_INDENT))
   ```
   Two concurrent runs → second writer's write silently discards first writer's additions;
   `orphan_connections.json`/`orphan_log.json` for the losing process still claim success but
   edges are absent from `edge_metadata.json` — no crash, no warning, both
   `pipeline_state.json` show `orphan_connect: done`. (→ to-do #23)

6. **Single corrupted Pass2 shard crashes entire re-entry, no per-shard isolation** —
   step_pass2.py `_run()` lines 70-75 does `json.loads(shard_file.read_text())` for every
   `*.json` in `raw_extractions_shards/` with NO try/except; one truncated shard (from
   SIGKILL/OOM mid-`_on_file_done` write, lines 179-188) crashes the WHOLE pass2 step even
   though hundreds of other shards are valid. D26 Re-entry B's `--from-step pass2` deletes ALL
   shards (full re-extraction) — wasteful for single-file corruption. (→ to-do #24)

**Moderate Risks** (8 items):

11. Top-level node/edge `confidence` is never clamped to [0,1] — `_coerce_attr` only clamps
    attribute-level; `deduplicate_nodes`/`deduplicate_edges` (lines 133, 235) do
    `float(node.get("confidence", _cfg.CONFIDENCE_FALLBACK))` with no clamping. A
    confidence > 1.0 would ALWAYS pass any `>= threshold` filter. (→ to-do #8)

12. `_load_manifest` and other `json.loads` calls without try/except crash on truncated files
    (step_ingest.py `_load_manifest` lines 68-89, schema.json, etc.) — loud crash but requires
    manual intervention.

13. `_is_done()` existence-only check (orchestrator.py lines 94-103, only `p.exists()`) skips
    steps whose output is corrupt-but-present — the crash surfaces in a DIFFERENT downstream
    step than the actual root cause.

14. `_load_prior_manifest` (step_preprocess.py lines 49-57,
    `except (json.JSONDecodeError, OSError): return {}`) silently treats a corrupt manifest as
    "no prior state" → full costly MinerU re-conversion with only a missing INFO log line as
    signal. (→ to-do #7)

15. `_copy_input_files` follows symlinks via `shutil.copy2` — `f.is_file()` follows symlinks; a
    `.md`-suffixed symlink to e.g. `/etc/passwd` or files outside `input_dir` gets its TARGET
    content copied into `session/input/`. (→ to-do #6)

16. `--session <name>` with a DIFFERENT `input_dir` additively contaminates an existing
    session — `_copy_input_files` doesn't clear `session/input/` first; mixing two unrelated
    corpora's files into one session's `intermediate/schema.json` with no warning.
    (→ to-do #5)

17. `synonym_match` false-positive collapse (D21/D28) cascades silently — two genuinely-distinct
    concept types merged in `schema.json` → Pass2 extracts both under the merged type → may
    merge semantically-different entities sharing a name (compounds with #3). No validator
    fires. Mitigated by D17's human review gate IF `--review` is used (opt-in) —
    `merge_log.json` DOES record the collapse with a warning. (→ to-do #4)

18. Extremely long `name` values (10,000+ chars) → extremely long stable IDs with no
    truncation — used as dict keys, Turtle local names (`_ttl_local` sanitizes chars not
    length), CSV values, Obsidian filenames (potential `OSError ENAMETOOLONG` at Step 12d,
    partial-output inconsistency since Obsidian export isn't blocking per D19). (→ to-do #3)

**Invariant Violation Analysis** (8 items):

1. "{nodes[]+edges[]}, edges direct not wrapped" — NO bypass found.
2. "knowledge_graph.ttl: no edge metadata/blank nodes/reification/RDF-star" — NO structural
   bypass, but finding #1 shows TTL CONTENT can be semantically wrong (dangling refs) without
   violating this structural invariant.
3. "Edge metadata lives exclusively in edge_metadata.json" — no duplication-elsewhere bypass,
   but finding #5 shows the sidecar itself can LOSE data via concurrent last-write-wins —
   "data loss from the sole source of truth, not duplication elsewhere."
4. "No abstract Relationship class" — NO bypass found.
5. "Missing attributes never dropped, always {value:null, confidence:0.0}" — NO bypass in the
   normal path; BUT finding #4's `_fix_orphan_connect` writes `orphan_connections.json` with NO
   schema-shape validation — a corrected edge missing `attributes` entirely could merge into
   `edge_metadata.json` without null-filled placeholders.
6. "No hardcoded parameters" — NO bypass found; `_HTML_BACKEND_SUFFIXES` hardcoding is
   explicitly justified by D44 as a documented exception.
7. "All data models use Pydantic BaseModel" — LARGELY upheld for typed records
   (OrphanChunkGroup, SchemaGapOrphan, PipelineContext, PipelineState) but
   edge_metadata.json/nodes.json/raw_extractions.json/orphan_connections.json are all raw
   dict/json.loads with NO field/type/range constraints — exactly how findings #4 and #11
   occur.
8. "Each run fully isolated, resumable from its own snapshot" — findings #5 and #6 show the
   "snapshot" can become internally inconsistent (concurrent writers, crash timing) such that
   resuming produces silently wrong/duplicated state — violates the SPIRIT of this invariant
   even though no cross-session leakage occurs.
</content>
