# mykg

A two-pass knowledge graph extractor that reads Markdown files and produces a property graph with an RDFS-compatible ontology layer.

**Pass 1** — Schema induction: an LLM reads your Markdown files and induces a global schema (concept types + relationship properties).  
**Pass 2** — Instance extraction: the LLM extracts nodes and edges per file against that schema.  
**Assembly** — Nodes and edges are deduplicated, confidence-scored, and exported to three parallel output families.

## Outputs

| File | Description |
|---|---|
| `output/nodes.jsonl` | Concept instances with full attributes and confidence scores |
| `output/edges.jsonl` | Relationship instances derived from the edge metadata sidecar |
| `output/knowledge_graph.ttl` | Pure RDFS Turtle — TBox (classes + properties) + ABox (instances) |
| `output/knowledge_graph_validation.json` | TBox + ABox validation results (advisory) |
| `output/knowledge_graph.html` | Interactive D3.js force-directed graph — open in any browser, no server required |
| `output/networkx_output/knowledge_graph.graphml` | GraphML — full attributes (yEd, Gephi, Cytoscape) |
| `output/networkx_output/knowledge_graph.gexf` | GEXF — Gephi native format |
| `output/networkx_output/knowledge_graph.json` | JSON node-link — D3.js, Sigma.js, web visualizers |
| `output/networkx_output/knowledge_graph.gml` | GML — human-readable, most graph tools |
| `output/networkx_output/knowledge_graph.net` | Pajek — string attributes only |
| `output/networkx_output/edges_nx.txt` | Plain edge list with attributes |
| `output/networkx_output/adjacency.txt` | Adjacency list — topology only |
| `<session>/walkthrough.md` | Post-run report — schema evolution, LLM call summary, orphan stats, pipeline timing |

The HTML graph supports node/edge filtering by type and confidence, search by name, hover popups with full attributes, and a resizable sidebar. It is written alongside the NetworkX formats and skipped when `pipeline.export.networkx_enabled` is `false`.

NetworkX output is enabled by default via `pipeline_config.yaml → pipeline.export.networkx_enabled`. Set to `false` to skip.

Walkthrough report generation is enabled by default via `pipeline_config.yaml → pipeline.report.enabled`. Set to `false` to skip. The report is written at the session root (`sessions/<name>/walkthrough.md`), not inside `output/`.

---

## Output Field Reference

Notable fields that appear in output files:

| Field | File | Values | Description |
|---|---|---|---|
| `aliases` | `nodes.jsonl` | `["Acme", "ACME Corp"]` | Surface-form variants resolved to this canonical node during name normalization. Absent when `normalize_names.enabled: false`. |
| `extraction_quality` | `nodes.jsonl` | `blank_response`, `blank_recovered`, `blank_unresolved` | Set when a node came from a chunk that returned a blank LLM response. Absent on clean extractions. |
| `method` | `edges.jsonl` (via `edge_metadata.json`) | `llm_extraction`, `orphan_inferred` | How the edge was produced. |

---

## Installation

Requires Python 3.11+.

```bash
# With uv (recommended)
uv sync

# With pip
pip install -e .
```

---

## Configuration

All configuration — LLM provider, model, and every pipeline parameter — lives in a single `pipeline_config.yaml` file. Create it in your working directory (or any parent directory — it is discovered automatically).

The file has two top-level sections: `llm` (provider settings) and `pipeline` (all tuneable pipeline constants). `src/mykg/config.py` loads this file at startup; there are no hardcoded defaults anywhere in the code.

### Anthropic (Claude) — custom profile

There is no built-in Anthropic profile. Create one in `pipeline_config.yaml` and set it as the active profile. For a zero-API-key option, use the `claude-cli` profile instead (see below).

```yaml
profile: anthropic-claude

profiles:
  anthropic-claude:
    provider: anthropic
    llm:
      model: claude-opus-4-7
      context_window: 200000
      max_output_tokens: 64000
      timeout: 300
    pipeline:
      chunking:
        window_tokens: 30000
        overlap_tokens: 3000
        tiktoken_encoding: cl100k_base
      pass1:
        batch_token_target: 136000
        max_workers: 4
      pass2:
        max_workers: 4
        stateful_chunks: true
      normalize_names:
        enabled: true
        max_names_per_type: 2000
```

Set `ANTHROPIC_API_KEY` in your environment or `.env` file. Run `python context_calculator.py --context 200000 --max-output 64000` to recompute the token budget for a different model.

### Ollama (local)

Switch to the built-in `ollama-local` profile:

```yaml
profile: ollama-local
```

Requires [Ollama](https://ollama.com) running locally. Pull a model first:

```bash
ollama pull llama3.3
```

No API key required — billing is via your local hardware. To use a different model, edit `llm.model` in the profile and recompute the token budget with `python context_calculator.py --context <N> --max-output <M>`.

Optional overrides inside the `llm:` block:

```yaml
llm:
  model: gemma2:27b             # any model you have pulled
  base_url: http://localhost:11434   # change if Ollama runs on a different host/port
```

### OpenAI (GPT-4o)

Switch to the built-in `openai` profile:

```yaml
profile: openai
```

Set `OPENAI_API_KEY` in your environment or `.env` file. To use a different model or context window, copy the profile block and adjust `llm.model`, `llm.context_window`, `llm.max_output_tokens`, and the matching `pipeline.chunking` / `pipeline.pass1.batch_token_target` values (run `python context_calculator.py` to recompute the token budget).

Optional overrides inside the `llm:` block:

```yaml
llm:
  model: gpt-4o-mini        # any OpenAI model slug
  base_url: https://...     # Azure OpenAI or any OpenAI-compatible endpoint
  api_key: sk-...           # override OPENAI_API_KEY env var
```

### OpenRouter

Switch to the built-in `openrouter-free` profile:

```yaml
profile: openrouter-free
```

Set `OPENROUTER_API_KEY` in your environment or `.env` file. Optional overrides inside the `llm:` block:

```yaml
llm:
  model: anthropic/claude-opus-4   # any OpenRouter model slug (openrouter.ai/models)
  base_url: https://openrouter.ai/api/v1
```

### ClaudeCLI

Switch to the built-in `claude-cli` profile:

```yaml
profile: claude-cli
```

Uses the locally-installed `claude -p` subprocess — no `ANTHROPIC_API_KEY` required; billing via your Claude Pro/Max plan. All worker counts are fixed at 1 in this profile (the CLI is serial by design).

Requires the `claude` CLI to be installed and authenticated before running.

### Pipeline parameters

All pipeline parameters are in the `pipeline` section. Key tuneables:

| Key | Default | Description |
|---|---|---|
| `pipeline.ingest.max_workers` | `8` | Parallel workers for file reading and chunking |
| `pipeline.chunking.window_tokens` | `2000` | Chunk size in tokens |
| `pipeline.chunking.overlap_tokens` | `200` | Overlap between adjacent chunks |
| `pipeline.chunking.tiktoken_encoding` | `cl100k_base` | tiktoken encoding used for tokenization |
| `pipeline.pass1.batch_token_target` | `8000` | Max tokens per Pass 1 LLM batch |
| `pipeline.pass1.max_workers` | `4` | Parallel LLM workers for Pass 1 batch induction |
| `pipeline.pass1.per_file_batching` | `false` | When true, chunks from different files are never mixed in one batch |
| `pipeline.pass2.max_workers` | `1` | Parallel workers for Pass 2 |
| `pipeline.pass2.stateful_chunks` | `false` | When true, prior-chunk nodes are passed to subsequent chunks for stable cross-chunk IDs |
| `pipeline.pass2.prep_mode` | `per_file` | How Pass 2 prepares files for the LLM: `per_file` (one call per chunk, default), `concat` (small files batched together), `batch_chunks` (chunks packed greedily across files) |
| `pipeline.pass2.batch_token_target` | `8000` | Target tokens per batch when `prep_mode: batch_chunks` |
| `pipeline.pass2.batch_per_file` | `false` | When `prep_mode: batch_chunks`, keep chunks from different files in separate batches |
| `pipeline.normalize_names.enabled` | `true` | Run the name normalization step; set `false` to skip |
| `pipeline.normalize_names.max_names_per_type` | `200` | Max names per type sent to the normalization LLM |
| `pipeline.assembly.confidence_agg` | `mean` | Confidence aggregation strategy (`mean` or `max`) |
| `pipeline.assembly.edge_id_hex_length` | `6` | Hex chars from SHA-256 digest used as edge ID suffix |
| `pipeline.assembly.confidence_fallback` | `0.0` | Confidence assigned when LLM omits the field |
| `pipeline.assembly.confidence_scalar_omitted` | `0.7` | Confidence assigned to attribute values the LLM returns as plain scalars (no `{value, confidence}` wrapper) — e.g., when the model omits the wrapper for string fields |
| `pipeline.export.schema_namespace` | `http://mykg.local/schema/` | RDFS schema namespace URI in Turtle output |
| `pipeline.export.data_namespace` | `http://mykg.local/data/` | Instance data namespace URI in Turtle output |
| `pipeline.paths.output_dir` | `output` | Default output directory (used only when `--output-dir` is explicit) |
| `pipeline.paths.intermediate_dir` | `intermediate` | Default intermediate directory (used only when `--intermediate-dir` is explicit) |
| `pipeline.paths.sessions_dir` | `sessions` | Root folder for all session subdirectories |
| `pipeline.export.networkx_enabled` | `true` | Write NetworkX formats to `output/networkx_output/`; set `false` to skip |
| `pipeline.orphan_pass.enabled` | `true` | Run the orphan-connection pass; set `false` to skip both stages |
| `pipeline.orphan_pass.min_cooccurrence` | `1` | Minimum chunk co-occurrences for a pair to become a candidate |
| `pipeline.orphan_pass.top_k_per_orphan` | `3` | Max candidate edges per orphan sent to Stage 2 LLM |
| `pipeline.orphan_pass.confidence_base` | `0.5` | Base factor in `final = llm_conf × min(1.0, base + weight × score)` |
| `pipeline.orphan_pass.confidence_weight` | `0.5` | Heuristic weight in the orphan confidence formula |
| `pipeline.orphan_pass.max_workers` | `4` | Parallel LLM calls in Stage 2 |
| `pipeline.orphan_pass.excerpt_window` | `400` | Token window around an orphan mention used as LLM context in Stage 2 |
| `pipeline.orphan_pass.excerpt_context` | `150` | Tokens of surrounding context added around the excerpt window |
| `pipeline.orphan_pass.excerpt_max_total` | `4000` | Hard cap on total characters in the Stage 2 orphan prompt; prevents exceeding model context on nodes with many candidates |
| `pipeline.orphan_pass.blank_recovery_enabled` | `true` | Detect and attempt recovery of blank-response orphans |
| `pipeline.orphan_pass.connected_sample_size` | `20` | Max connected nodes included in the Stage 2 orphan prompt |
| `pipeline.orphan_pass.schema_max_restarts` | `1` | Maximum number of automated Pass 2 restarts triggered by schema-gap orphan recovery; set to `0` to disable automated restarts |
| `pipeline.error_gate.enabled` | `true` | Circuit breaker that pauses all workers on repeated API errors |
| `pipeline.error_gate.threshold` | `3` | Consecutive API errors before the gate trips |
| `pipeline.logging.max_bytes` | `10485760` | Max bytes per log file before rotation (10 MB) |
| `pipeline.logging.backup_count` | `3` | Number of rotated log files to keep |
| `pipeline.logging.capture_prompts` | `true` | Write full LLM prompts to `intermediate/llm_calls/` for debugging |

### Pass 2 File Preparation Modes

`pipeline.pass2.prep_mode` controls how input is prepared for each LLM extraction call:

| Mode | Best for | Behaviour |
|---|---|---|
| `per_file` (default) | Most corpora | One LLM call per chunk; each chunk is extracted independently. Simplest and most predictable. |
| `concat` | Many small files | Small files are concatenated into virtual batches so each LLM call handles several files at once, reducing total LLM calls. Files below `pipeline.pass2.concat_batch_token_target` tokens are eligible. |
| `batch_chunks` | Very large corpora | Chunks across files are packed greedily up to `pipeline.pass2.batch_token_target` tokens per call, with a real-time progress ETA displayed during extraction. Set `batch_per_file: true` to keep chunks from different files in separate batches. |

To switch modes, update the `prep_mode` key in the active profile in `pipeline_config.yaml`.

### Name Normalization

After Pass 2, the pipeline runs a name normalization step that resolves surface-form variants of the same entity (e.g., "Acme Corp", "ACME", "Acme Corporation") to a single canonical name. The LLM groups synonyms per concept type and returns a mapping; the assembler then merges the variants and records the non-canonical names as `aliases` on the resulting node.

Config:
```yaml
pipeline:
  normalize_names:
    enabled: true                # set false to skip entirely
    max_names_per_type: 2000     # cap on names per type sent in one LLM call
```

The intermediate mapping is written to `intermediate/name_normalization.json`. To re-run only the assembly step after editing this file manually, use `--from-step assemble`.

### Walkthrough Report

After every successful run, mykg writes `sessions/<name>/walkthrough.md` (when `pipeline.report.enabled: true`, the default). The report contains:
- Schema evolution summary — concept types and properties added at each Pass 1 stage
- LLM call statistics — call count, token usage, duration per step
- Orphan connection summary — candidates scored, edges confirmed, blank-response recoveries
- Pipeline timing — wall-clock time per step

You can regenerate the walkthrough for an existing session without re-running the pipeline:
```bash
mykg walkthrough --session 2026-05-17T18-31-07
```

---

## Running

```bash
# With uv
uv run mykg extract-graph <input_dir>

# With pip install -e .
mykg extract-graph <input_dir>
```

`<input_dir>` is a directory of `.md` files.

### All Options

```
mykg extract-graph [OPTIONS] INPUT_DIR
```

| Option | Default | Description |
|---|---|---|
| `--session NAME` | — | Resume an existing session by folder name; omit to auto-create a new timestamped session |
| `--output-dir PATH` | — | Override output dir (bypasses session management; cannot combine with `--session`) |
| `--intermediate-dir PATH` | — | Override intermediate dir (bypasses session management; cannot combine with `--session`) |
| `--log-file PATH` | — | Write logs to file — relative paths are placed inside the session folder; absolute paths are used as-is |
| `--verbose` / `-v` | — | Enable DEBUG-level logging |
| `--base-schema PATH` | — | Locked TBox TTL file (see below) |
| `--thesaurus PATH` | — | SKOS TTL thesaurus file (see below) |
| `--review` | — | Pause for human schema review after Pass 1 |
| `--from-step NAME` | — | Re-run from a specific step (deletes its outputs and all downstream). For the orphan pass use the explicit aliases `orphan_connect_fullsweep` (full clean re-run) or `orphan_connect_incremental` (preserve prior confirmed edges, only re-send unresolved groups) |
| `--workers N` | `1` | Parallel workers for Pass 2 (1 = sequential) |
| `--confidence-agg mean\|max` | `mean` | Confidence aggregation strategy when deduplicating nodes/edges |
| `--append` | — | Skip Pass 1; re-run only on new/modified files, then re-assemble and re-export |

---

## Examples

```bash
# Minimal — auto-creates a new timestamped session under sessions/
mykg extract-graph my_notes/
# → Session: 2026-05-17T18-31-07
# All outputs go to sessions/2026-05-17T18-31-07/{input,intermediate,output}/
# Log is auto-placed at sessions/2026-05-17T18-31-07/run.log

# Write a named log file (placed inside the session folder automatically)
mykg extract-graph my_notes/ --log-file run.log --verbose

# Resume an existing session (add new files, re-assemble, re-export)
mykg extract-graph my_notes/ --session 2026-05-17T18-31-07 --append

# Resume an existing session and force-re-run from a specific step
mykg extract-graph my_notes/ --session 2026-05-17T18-31-07 --from-step pass2

# Bypass session management and write to explicit directories
mykg extract-graph my_notes/ --output-dir kg/output --intermediate-dir kg/intermediate

# Run Pass 2 with 4 parallel workers
mykg extract-graph my_notes/ --workers 4

# Keep highest-confidence node/edge when deduplicating instead of averaging
mykg extract-graph my_notes/ --confidence-agg max

# Pause after Pass 1 for schema review
mykg extract-graph my_notes/ --review
# ... edit sessions/<name>/intermediate/schema.json ...
mykg approve-schema --session 2026-05-17T18-31-07
mykg extract-graph my_notes/ --session 2026-05-17T18-31-07 --review   # resumes from Pass 2

# Lock an existing ontology so the LLM can't rename or remove its classes
mykg extract-graph my_notes/ --base-schema ontology/core.ttl

# Resolve near-duplicate concept names using a SKOS vocabulary
mykg extract-graph my_notes/ --thesaurus ontology/terms.skos.ttl

# Re-run from Pass 2 after editing the schema (reuses existing schema files)
mykg extract-graph my_notes/ --session 2026-05-17T18-31-07 --from-step pass2

# Re-run only assembly + export after editing raw_extractions.json
mykg extract-graph my_notes/ --session 2026-05-17T18-31-07 --from-step assemble

# Re-run only the export step (e.g. after fixing exporter logic)
mykg extract-graph my_notes/ --session 2026-05-17T18-31-07 --from-step export
```

---

## Sessions

Every `mykg extract-graph` run automatically creates an isolated session folder:

```
sessions/
  2026-05-17T18-31-07/     ← auto-created (UTC timestamp)
    input/                 ← copy of all input Markdown files
    intermediate/          ← all intermediate pipeline files
    output/                ← all final output files
    run.log                ← log file (auto-placed here)
```

**Starting a new run** — omit `--session`:
```bash
mykg extract-graph my_notes/
# → Session: 2026-05-17T18-31-07
```

**Resuming an existing session** — pass its folder name:
```bash
# Append new/modified files and re-export
mykg extract-graph my_notes/ --session 2026-05-17T18-31-07 --append

# Re-run from a specific step
mykg extract-graph my_notes/ --session 2026-05-17T18-31-07 --from-step pass2

# Approve the schema for a session under review
mykg approve-schema --session 2026-05-17T18-31-07
```

**Bypassing sessions** — pass explicit directory flags; session management is skipped:
```bash
mykg extract-graph my_notes/ --output-dir kg/output --intermediate-dir kg/intermediate
```

The sessions root is configured via `pipeline.paths.sessions_dir` (default: `sessions/` in cwd).

---

## Pipeline Steps

The pipeline runs 11 steps in sequence. Each step writes intermediate files so the pipeline is fully resumable.

| # | Step | LLM | Key outputs |
|---|---|---|---|
| 1 | `ingest` | — | `file_manifest.json`; optionally `base_schema_parsed.json`, `thesaurus_parsed.json` |
| 2 | `pass1` | ✓ (3 calls) | `intermediate/schema.json`, `intermediate/schema.ttl`, `intermediate/schema_history/`. Internally: (1) parallel batch induction; (2) algorithmic merge + synonym dedup; (3) harmonization LLM call; (4) quality review LLM call. |
| 3 | `schema_validate` | — | `intermediate/schema_validate.done`; `intermediate/schema_validation_errors.json` on failure |
| 4 | `human_review` | — | `intermediate/schema_approved.flag` *(gate — active only with `--review`)* |
| 5 | `schema_flatten` | — | `intermediate/flattened_schema.json` |
| 6 | `pass2` | ✓ | `intermediate/raw_extractions.json`, `intermediate/chunk_node_index.json`, `intermediate/failed_chunks.json` |
| 7 | `normalize_names` | ✓ | `intermediate/name_normalization.json` |
| 8 | `assemble` | — | `intermediate/edge_metadata.json`, `intermediate/nodes.json`, `intermediate/merge_log.json` |
| 9 | `orphan_score` | — | `intermediate/orphan_candidates.json` — co-occurrence heuristic, no LLM |
| 10 | `orphan_connect` | ✓ | `intermediate/orphan_connections.json`, `intermediate/orphan_log.json`, `intermediate/schema_gap_proposals.json`; merges confirmed edges into `edge_metadata.json` |
| 11 | `validate_graph` | — | `output/nodes.jsonl`, `output/edges.jsonl`, `output/knowledge_graph.ttl`, `output/knowledge_graph_validation.json`, `output/networkx_output/` (when `networkx_enabled: true`) |

### Pass 1 Schema Induction

Pass 1 runs four sequential stages to produce a clean global schema:

1. **Parallel batch induction** — All document chunks are dispatched concurrently to the LLM (up to `pass1.max_workers` workers). Each batch returns a `{concepts, properties}` proposal. Use `pass1.per_file_batching: true` to keep chunks from different files in separate batches.
2. **Algorithmic merge** — All batch proposals are unioned, deduplicated by exact name match, and near-duplicates resolved by string similarity (`synonym_match`). No LLM call. Result written to `intermediate/schema.json`.
3. **Harmonization LLM call** — A single LLM call reviews the merged schema and collapses semantic near-duplicates the algorithmic merge missed (e.g., "MilitaryUnit" vs "ArmyUnit"). The original schema is kept if the response is unparseable.
4. **Quality review LLM call** — A second LLM call removes over-narrow concept types (named-entity singletons like "FourthAirForce"), fixes singleton types, collapses subclasses with no own attributes, and ensures every concept has at least a `name` attribute.

Each stage writes a delta record to `intermediate/schema_history/` (see Intermediate Files Reference). The schema at the end of stage 4 is the version used for the human review gate and all of Pass 2.

---

## Human Review Gate

When `--review` is passed, the pipeline pauses after Pass 1 and waits for you to approve the schema before running Pass 2.

**Workflow:**

1. Run with `--review`:
   ```bash
   mykg extract-graph my_notes/ --review
   # → Session: 2026-05-17T18-31-07
   ```

2. The pipeline writes `sessions/<name>/intermediate/schema.json` and `schema.ttl`, validates the schema, then halts.

3. Review and edit `sessions/<name>/intermediate/schema.json` as needed (add/remove concept types, fix properties).

4. Approve to continue:
   ```bash
   mykg approve-schema --session 2026-05-17T18-31-07
   ```
   This regenerates `schema.ttl` from your edited `schema.json` and writes the approval flag.

5. Re-run with the same session — the pipeline resumes from Pass 2:
   ```bash
   mykg extract-graph my_notes/ --session 2026-05-17T18-31-07 --review
   ```

---

## Re-running from a Specific Step

Use `--from-step` to delete a step's outputs and all downstream outputs, then re-run from that point. This is useful after editing intermediate files or diagnosing extraction errors.

```bash
SESSION=2026-05-17T18-31-07

# Re-run from Pass 2 onward (reuse the existing schema)
mykg extract-graph my_notes/ --session $SESSION --from-step pass2

# Re-run only assembly and export (reuse raw extractions)
mykg extract-graph my_notes/ --session $SESSION --from-step assemble

# Re-run both orphan stages (keeps existing assembly outputs)
mykg extract-graph my_notes/ --session $SESSION --from-step orphan_score

# Re-run only LLM confirmation — full clean sweep (keeps Stage 1 candidates, discards prior confirmed edges)
mykg extract-graph my_notes/ --session $SESSION --from-step orphan_connect_fullsweep

# Re-run only LLM confirmation — additive sweep (loads prior orphan_connections.json as seed; only unresolved groups sent to LLM)
mykg extract-graph my_notes/ --session $SESSION --from-step orphan_connect_incremental

# Valid step names:
# pass1, schema_validate, human_review, schema_flatten, pass2, normalize_names,
# assemble, orphan_score, orphan_connect_fullsweep, orphan_connect_incremental, export
```

**Four re-entry patterns:**

- **Re-entry A (schema changed):** Edit `sessions/<name>/intermediate/schema.json` → `mykg approve-schema --session <name>` → `--from-step pass1`
- **Re-entry B (extraction errors):** Edit `sessions/<name>/intermediate/raw_extractions.json` → `--from-step pass2`
- **Re-entry C (assembly errors):** Review `sessions/<name>/intermediate/merge_log.json`, optionally edit `raw_extractions.json` → `--from-step assemble`
- **Re-entry D (orphan pass):** Delete `sessions/<name>/intermediate/orphan_candidates.json` → `--from-step orphan_score` (both stages), or use `--from-step orphan_connect_fullsweep` (LLM only, full clean re-run) / `--from-step orphan_connect_incremental` (LLM only, additive — preserves prior confirmed edges)
- **Re-entry for merge:** Re-run `mykg merge-graphs <A> <B> --session <merged-name>` to resume from the last incomplete step. To pass the human review gate, run `mykg approve-schema --session <merged-name>` first. To force re-extraction, delete `intermediate/merge_reextract.done` before re-running.

### Schema-gap orphans: two recovery strategies

When the orphan-connect pass promotes nodes to "schema-gap orphans" (the LLM proposes new properties but the restart limit is reached), you have two options:

**Strategy 1 — Full re-extraction (`--from-step pass2`)**

Re-extracts all files with the updated schema. The new properties are injected into every Pass 2 prompt, so the LLM can produce those edges directly from the raw text. Also recovers any edges between already-connected nodes that were silently dropped during the original pass2 run.

Cost: full Pass 2 run (~same duration as original).

```bash
mykg extract-graph my_notes/ --session <name> --from-step pass2
```

**Strategy 2 — Full orphan re-run (`--from-step orphan_connect_fullsweep`)**

Skips re-extraction entirely. Discards all prior confirmed orphan edges and re-runs the full LLM confirmation pass using the updated schema. The new properties are included in the orphan prompt, so the LLM can produce edges of the new types. Only processes chunks where orphan nodes appear — edges between non-orphan nodes that were dropped during the original pass2 are not recovered.

Cost: one LLM call per affected chunk (~minutes).

```bash
mykg extract-graph my_notes/ --session <name> --from-step orphan_connect_fullsweep
```

**Strategy 3 — Additive orphan re-run (`--from-step orphan_connect_incremental`)**

Like Strategy 2, but loads the existing `orphan_connections.json` as a seed. Only orphan groups that are not already fully resolved are re-sent to the LLM. Confirmed edges from the prior run are preserved and carried forward unchanged. Useful when the schema was extended but many orphans were already correctly connected — avoids paying the full LLM cost again.

Cost: one LLM call per *unresolved* chunk (often a fraction of Strategy 2).

```bash
mykg extract-graph my_notes/ --session <name> --from-step orphan_connect_incremental
```

**When to use which:**

| | Strategy 1 (pass2) | Strategy 2 (fullsweep) | Strategy 3 (incremental) |
|---|---|---|---|
| Recovers all dropped edges of new types | Yes | Only for orphan chunks | Only for unresolved orphan chunks |
| Recovers edges between non-orphan nodes | Yes | No | No |
| Preserves prior confirmed orphan edges | No | No | Yes |
| Runtime | ~hours | ~minutes | ~minutes (fewer LLM calls) |
| Use when | New properties are semantically broad, likely across many files | Few prior confirmed edges; want a clean re-run | Many orphans already correctly connected; only unresolved groups need the updated schema |

By default, the pipeline will trigger at most one automated Pass 2 restart (`schema_max_restarts: 1`). Set to `0` in `pipeline_config.yaml` to disable automated restarts entirely and handle schema gaps manually with `--from-step pass2` after editing `intermediate/schema.json`.

---

## Optional: Locked Base Schema (`--base-schema`)

Provide a TBox-only RDFS TTL file to lock certain classes and properties. Locked entries cannot be renamed, removed, or have their structure changed by LLM proposals — they are authoritative vocabulary.

```bash
mykg extract-graph my_notes/ --base-schema ontology/base.ttl
```

**Lock rules for classes:**
- Cannot be renamed, removed, or have their `parent` (superclass) changed by LLM proposals
- Can receive additional attributes proposed by the LLM (attributes are unioned in)
- LLM proposals with the same or a similar name are merged into the locked entry; the locked structure wins

**Lock rules for properties:**
- Cannot be renamed, removed, or have their `domain` or `range` changed
- Can receive additional edge-attribute fields proposed by the LLM (attributes are unioned in)

Near-duplicate LLM proposals (matched by string similarity) are collapsed into the locked entry with a warning in `intermediate/merge_log.json`. Every batch prompt also includes an `EXISTING SCHEMA` block that lists locked class and property names with an explicit instruction not to rename, remove, or duplicate them.

The parsed lock list is written to `intermediate/base_schema_parsed.json`.

---

## Optional: SKOS Thesaurus (`--thesaurus`)

Provide a SKOS TTL file to resolve near-duplicate concept names during schema merge (Pass 1).

```bash
mykg extract-graph my_notes/ --thesaurus ontology/thesaurus.skos.ttl
```

Synonym resolution rules:
- `skos:exactMatch` — silent collapse (treated as identical)
- `skos:closeMatch` — collapse with a warning logged to `intermediate/merge_log.json`
- `skos:broader` / `skos:narrower` — advisory hints only (not enforced)

Without a thesaurus, only exact and normalized string matching applies.

Thesaurus metadata is written to `intermediate/thesaurus_parsed.json`.

---

## Orphan-Connection Pass

After assembly, some nodes may have zero edges — they are present in the graph but unreachable by traversal. The orphan-connection pass attempts to connect these nodes in two stages:

**Stage 1 — `orphan_score` (no LLM):** Uses `intermediate/chunk_node_index.json` to find nodes that co-occur in the same source chunk as each orphan. Candidates are scored by normalized co-occurrence count and filtered by schema type compatibility (only domain/range-compatible pairs are kept). Results are written to `intermediate/orphan_candidates.json`.

**Stage 2 — `orphan_connect` (LLM):** Asks the LLM to confirm whether a real schema relationship exists for each candidate pair. Confirmed edges are assigned final confidence via `llm_conf × min(1.0, base + weight × heuristic_score)` and merged directly into `intermediate/edge_metadata.json` before `export` runs — so all three output families (JSONL, Turtle, NetworkX) receive them automatically.

Orphan edges carry `"method": "orphan_inferred"` to distinguish them from `"llm_extraction"` edges in the sidecar.

To disable the pass entirely: set `pipeline.orphan_pass.enabled: false` in `pipeline_config.yaml`.

---

## Merging Sessions (`mykg merge-graphs`)

Combines two independently-produced pipeline sessions into a unified knowledge graph written to a new session folder. Both source sessions are read-only — no existing session is modified.

```bash
mykg merge-graphs <session-A> <session-B> [OPTIONS]
```

| Option | Description |
|---|---|
| `--output-session TEXT` | Name for the merged session folder (default: auto-timestamped) |
| `--no-review` | Skip the human review gate after schema merge |
| `--thesaurus PATH` | SKOS TTL thesaurus for schema synonym matching |
| `--base-schema PATH` | Locked TBox TTL base schema |
| `--log-file PATH` | Write logs here (default: merged session root/run.log) |
| `-v, --verbose` | Enable DEBUG-level logging |

### Example

```bash
mykg merge-graphs 2026-05-01T10-00-00 2026-05-15T14-30-00
```

### What happens

1. **Schema merge** — both schemas are merged with the same three-stage chain as Pass 1: algorithmic union + LLM harmonization + LLM quality review. Schema writes are recorded in `schema_history/` with trigger `session_merge`.
2. **Human review gate** — pauses for schema review unless `--no-review` is set. Approve by running `mykg approve-schema --session <merged-name>` or `touch sessions/<merged>/intermediate/schema_approved.flag`.
3. **Schema flatten** — inheritance is walked and attributes unioned per concept type into `flattened_schema.json`.
4. **Re-extraction** — controlled by `merge_graphs.reextraction_strategy` in `pipeline_config.yaml` (see below).
5. **Merge raw extractions** — both sessions' extractions are namespaced (`session_a/<filename>`, `session_b/<filename>`) and combined.
6. **Assemble** — stable IDs are assigned, nodes and edges deduplicated. The same entity from both sessions converges to one node (ID is deterministic: type + canonical name). Decisions logged to `merge_log.json`.
7. **Export** — all three output families (JSONL, Turtle, NetworkX) are written to the merged session's `output/`.
8. **Finalize** — `merge_manifest.json` is written with `session_a`, `session_b`, `merged_at`, schema deltas, and re-extraction strategy used.

### Re-extraction strategies

When the merged schema adds properties absent from a source session's original schema, those properties have zero instances in that session's files unless extraction is re-run.

Configure in `pipeline_config.yaml`:

```yaml
merge_graphs:
  reextraction_strategy: none   # none | surgical | full
```

| Strategy | What happens | LLM cost |
|---|---|---|
| `none` | Accept gaps — new properties will have zero instances for that session's files | Zero |
| `surgical` | Re-extracts only chunks from files in sessions where new properties are absent. New node IDs produced by the LLM are dropped — only new edges (using the merged property types) and enriched attribute values on existing nodes survive. | O(affected files) |
| `full` | Re-run pass2 on every file from both sessions | O(all files) |

> `full` is a stub in the current implementation — it logs a warning and returns existing extractions unchanged.

### File collision handling

Both sessions may have files with the same filename. All file-keyed structures are namespaced before merging:

```
session A's "notes.md"  →  "session_a/notes.md"
session B's "notes.md"  →  "session_b/notes.md"
```

If both sessions extracted the same real-world entity from their respective files, it will be deduplicated in assembly into a single node with `source_files: ["session_a/notes.md", "session_b/notes.md"]`.

### Merged session layout

```
sessions/<merged-timestamp>/
  input/                        ← empty; inputs referenced by source_map.json
  intermediate/
    schema.json                 ← merged schema
    schema.ttl                  ← RDFS TBox of merged schema
    flattened_schema.json
    raw_extractions.json        ← combined namespaced extractions
    nodes.json                  ← deduplicated node list
    edge_metadata.json          ← deduplicated edge sidecar
    merge_log.json              ← dedup audit trail
    source_map.json             ← file provenance for both sessions
    merge_manifest.json         ← merge audit record
    schema_history/             ← entries from both sessions
    raw_extractions_shards/     ← namespaced copies from both sessions
    chunk_index_shards/         ← namespaced copies from both sessions
  output/
    nodes.jsonl
    edges.jsonl
    knowledge_graph.ttl
    knowledge_graph_validation.json
    networkx_output/
  run.log
```

After a successful merge, `walkthrough.md` is generated automatically at the merged session root. For merge sessions it includes **§2 Merge Provenance**: a Before & After counts table, Node Provenance breakdown (A-only, B-only, deduplicated, net-new), and Edge Provenance breakdown (A→A, B→B, cross-session, edges using new merged property types).

### Running the orphan pass on a merged graph

The orphan pass does not run automatically after merge. To run it:

```bash
mykg extract-graph <any-input-dir> --session <merged-session-name> --from-step orphan_score
```

### `prep_mode` compatibility

Sessions run with different Pass 2 `prep_mode` values (`per_file`, `concat`, `batch_chunks`) can be merged freely — all three modes produce the same shard format and the merge logic treats them identically.

---

## Confidence Scores

Every extracted attribute, node, and edge carries a confidence score `0.0–1.0`. Missing attributes are never dropped — they are represented as `{"value": null, "confidence": 0.0}`. Downstream consumers filter by threshold.

When the same entity appears in multiple source files, attributes are merged by keeping the highest-confidence value per attribute. The node/edge-level confidence is aggregated using `--confidence-agg mean` (default) or `max`.

---

## Development

### Testing

```bash
# Run all non-live tests (fast, no API key needed)
uv run pytest -m "not live" -v

# Run all tests including live integration tests
# Requires OPENROUTER_API_KEY set in environment or .env
uv run pytest -m live -v

# Run a single test file
uv run pytest tests/test_assembler.py -v

# Run with verbose output and stop on first failure
uv run pytest -m "not live" -x -v
```

Live tests (`@pytest.mark.live`) make real API calls to OpenRouter. They are skipped automatically if `OPENROUTER_API_KEY` is not set.

### Coverage

```bash
# Coverage runs automatically with pytest (configured in pyproject.toml)
uv run pytest -m "not live"

# Open the HTML report
open htmlcov/index.html      # macOS
xdg-open htmlcov/index.html  # Linux
```

The HTML report at `htmlcov/index.html` shows line-by-line coverage for every source file. Coverage is configured in `pyproject.toml` under `[tool.coverage.*]`.

### Profiling

```bash
# Profile a full pipeline run
python -m cProfile -o profile.out -m mykg.cli extract input_files/

# Visualize the profile interactively
uv run snakeviz profile.out
```

snakeviz opens an interactive flame chart in your browser showing call counts and cumulative time per function.

### Token Budget Calculator

When switching to a model with a different context window, use the bundled calculator to derive the correct `window_tokens`, `overlap_tokens`, and `batch_token_target` values:

```bash
# Manual: specify context window and max output tokens
python context_calculator.py --context 128000 --max-output 16384

# Auto: read context window from active profile and measure your corpus
python context_calculator.py --from-config --input-dir input_files/
```

The calculator outputs a ready-to-paste YAML snippet for the `pipeline:` section.

### Linting and Formatting

```bash
# Check for lint violations
uv run ruff check src/ tests/

# Auto-fix fixable violations
uv run ruff check --fix src/ tests/

# Check formatting
uv run ruff format --check src/ tests/

# Apply formatting
uv run ruff format src/ tests/
```

---

## Intermediate Files Reference

All intermediate state is preserved for debugging and re-entry. In session mode the paths below are relative to `sessions/<name>/` — e.g. `sessions/2026-05-17T18-31-07/intermediate/schema.json`.

| File | Description |
|---|---|
| `intermediate/base_schema_parsed.json` | Locked classes + properties from `--base-schema` |
| `intermediate/schema_history/` | Numbered delta files (`<seq>_<trigger>.json`) tracking schema changes. Trigger labels: `pass1_merge` (initial merge), `schema_harmonize` (after harmonization LLM), `schema_quality` (after quality review LLM), `schema_validate` (after validation correction), `schema_gap` (new properties from orphan recovery), `schema_gap_correct` (correction after invalid schema-gap proposal). Useful for auditing schema evolution across a run. |
| `intermediate/thesaurus_parsed.json` | SKOS thesaurus metadata |
| `intermediate/schema.json` | Induced schema: `concepts[]` + `properties[]` — pipeline source of truth |
| `intermediate/schema.ttl` | TBox-only RDFS view of the schema |
| `intermediate/schema_validation_errors.json` | Both validation attempts (first + LLM-corrected retry) |
| `intermediate/schema_approved.flag` | Written by `mykg approve-schema` |
| `intermediate/flattened_schema.json` | Per-concept attribute lists with inheritance resolved |
| `intermediate/file_manifest.json` | Map of filename → content; enables re-entry after cold restart |
| `intermediate/raw_extractions.json` | Raw `nodes[]` + `edges[]` per source file, before assembly |
| `intermediate/chunk_node_index.json` | Map of `{filename: {chunk_idx: [stable_ids]}}` — prerequisite for orphan Stage 1 |
| `intermediate/name_normalization.json` | LLM alias→canonical name map from `normalize_names` step |
| `intermediate/edge_metadata.json` | Deduplicated edge attributes keyed by edge ID — source for `edges.jsonl`; updated in-place by `orphan_connect` |
| `intermediate/nodes.json` | Deduplicated node list — used by export on re-entry |
| `intermediate/merge_log.json` | Audit trail: node/edge merge decisions + synonym collapses |
| `intermediate/orphan_candidates.json` | Stage 1 output: scored candidate pairs for zero-edge nodes |
| `intermediate/orphan_connections.json` | Stage 2 output: confirmed orphan edges (keyed by edge ID) |
| `intermediate/orphan_log.json` | Audit trail: `orphan_edge_added` (new edge confirmed by LLM — id, type, from, to, confidence, rationale, llm_confidence, chunk_key), `orphan_edge_rejected` (edge rejected — orphan_id, candidate_id, reason), `orphan_edge_retained` (edge carried forward from a prior incremental sweep — id, type, from, to, confidence) |
| `intermediate/source_map.json` | File provenance map written at merge setup. Keys are namespaced file paths (`session_alias/filename`); values carry original session, alias, file path, SHA-256, and role (`input_a` / `input_b`). Includes a `_meta` block with session names and prep modes |
| `intermediate/merge_manifest.json` | Merge audit record written at merge finalization: `session_a`, `session_b`, `merged_at`, `schema_synonym_log`, `reextraction_strategy`, `schema_delta_session_a`, `schema_delta_session_b` |

### Output Files Reference

| File | Description |
|---|---|
| `output/nodes.jsonl` | Deduplicated concept instances with attributes and confidence scores |
| `output/edges.jsonl` | Flat edge records derived from the edge metadata sidecar |
| `output/knowledge_graph.ttl` | RDFS TBox + RDF ABox — pure triples, no edge metadata |
| `output/knowledge_graph_validation.json` | TBox + ABox validation results (advisory) |
| `output/networkx_output/knowledge_graph.graphml` | NetworkX: GraphML, full attributes |
| `output/networkx_output/knowledge_graph.gexf` | NetworkX: GEXF, Gephi native |
| `output/networkx_output/knowledge_graph.json` | NetworkX: JSON node-link (D3.js, Sigma.js) |
| `output/networkx_output/knowledge_graph.gml` | NetworkX: GML, human-readable |
| `output/networkx_output/knowledge_graph.net` | NetworkX: Pajek (string attributes only) |
| `output/networkx_output/edges_nx.txt` | NetworkX: plain edge list with attributes |
| `output/networkx_output/adjacency.txt` | NetworkX: adjacency list, topology only |
| `output/knowledge_graph.html` | Interactive D3.js visualization — node/edge filtering, search, hover popups, resizable sidebar |
