# Walkthrough — Session `2026-06-07T21-24-38`

**Run health:** ✓ Clean

## 1. Final Graph Summary

**Total nodes:** 44

| Type | Count |
|---|---|
| Technology | 16 |
| Person | 9 |
| Organization | 9 |
| Team | 5 |
| Project | 4 |
| Location | 1 |

**Total edges:** 49

**Edges by type:**

| Type | Count |
|---|---|
| works_at | 13 |
| contributes_to | 7 |
| manages | 6 |
| uses_technology | 5 |
| part_of | 5 |
| owns_project | 3 |
| provides_technology | 3 |
| reports_to | 2 |
| partners_with | 2 |
| member_of | 1 |
| depends_on | 1 |
| located_in | 1 |

**Edges by method:**

| Method | Count |
|---|---|
| llm_extraction | 49 |

**Validation:** valid

**Output files:**

- `edges.jsonl` — 14.9 KB
- `knowledge_graph.ttl` — 14.6 KB
- `knowledge_graph_validation.json` — 0.1 KB
- `nodes.jsonl` — 15.5 KB
- `networkx_output/` — 8 file(s):
  - `adjacency.txt` — 2.3 KB
  - `edges_nx.txt` — 12.3 KB
  - `knowledge_graph.gexf` — 53.9 KB
  - `knowledge_graph.gml` — 30.0 KB
  - `knowledge_graph.graphml` — 39.8 KB
  - `knowledge_graph.html` — 48.5 KB
  - `knowledge_graph.json` — 38.8 KB
  - `knowledge_graph.net` — 15.9 KB

## 2. Run Overview

| Field | Value |
|---|---|
| Session | `2026-06-07T21-24-38` |
| Run date/time (UTC) | 2026-06-07 21:24:38 |
| LLM provider | agent |
| LLM model | claude-code |
| Input files | 4 |
| Total duration | 8m 11s |
| Schema-gap restarts | 0 |
| Run health | healthy |

## 3. Step Timeline

| Step | Status | Start | Duration |
|---|---|---|---|
| preprocess | done | 22:24:38 | 0s |
| ingest | done | 22:24:38 | 0s |
| pass1 | done | 22:24:38 | 3m 03s |
| schema_validate | done | 22:27:41 | 0s |
| human_review | done | 22:27:41 | 0s |
| schema_flatten | done | 22:27:41 | 0s |
| pass2 | done | 22:27:41 | 1m 58s |
| normalize_names | done | 22:29:39 | 58s |
| assemble | done | 22:30:37 | 0s |
| orphan_score | done | 22:30:37 | 0s |
| orphan_connect | done | 22:30:37 | 2m 12s |
| validate_graph | done | 22:32:49 | 0s |

## 4. Schema Evolution

### History

| Seq | Trigger | Concepts +/- | Properties +/- |
|---|---|---|---|
| 1 | pass1_merge | +6 / -0 | +13 / -0 |
| 2 | schema_harmonize | +0 / -0 | +0 / -1 |
| 3 | schema_quality | +0 / -0 | +0 / -0 |

### Final Schema

**Concepts** (6 total):

- **Location** — attrs: `name, country, region`
- **Organization** — attrs: `name, industry, headquarters`
  - **Team** *(is-a: Organization)* — attrs: `focus, member_count`
- **Person** — attrs: `name, title, email, education`
- **Project** — attrs: `name, status, target_date, budget`
- **Technology** — attrs: `name, category, vendor`

**Properties** (12 total):

- `Person` →[**contributes_to**]→ `Project`  *(edge attrs: role)*
- `Project` →[**depends_on**]→ `Project`
- `Organization` →[**located_in**]→ `Location`
- `Person` →[**manages**]→ `Team`
- `Person` →[**member_of**]→ `Team`  *(edge attrs: role)*
- `Team` →[**owns_project**]→ `Project`
- `Team` →[**part_of**]→ `Organization`
- `Organization` →[**partners_with**]→ `Organization`  *(edge attrs: type, start_date)*
- `Organization` →[**provides_technology**]→ `Technology`
- `Person` →[**reports_to**]→ `Person`
- `Project` →[**uses_technology**]→ `Technology`
- `Person` →[**works_at**]→ `Organization`  *(edge attrs: role, start_date, end_date)*

## 5. LLM Call Statistics

*llm.log not found.*

## 6. Extraction Summary

### Pass 2 Retry Statistics

| Metric | Count |
|---|---|
| Chunks dispatched (total) | 0 |
| JSON parse error → retry | 0 |
| Validation error → retry | 0 |
| Retry also failed (JSON) | 0 |
| Chunks permanently skipped | 0 |
| Partial recoveries (degraded mode) | 0 |
| Nodes dropped (hallucinated anchors) | 0 |
| Edges dropped (partial recovery) | 0 |
| Retry rate | n/a |

### Per-file extraction

| File | Nodes | Edges | Retries |
|---|---|---|---|
| partners.md | 44 | 49 | 0 |
| projects.md | 44 | 49 | 0 |
| team.md | 44 | 49 | 0 |
| technologies.md | 44 | 49 | 0 |

**Name normalization:** 0 aliases mapped across 0 concept type(s).

**Deduplication:** 44 node merge(s), 49 edge merge(s).

**Dangling edges dropped:** 0

## 7. Orphan Pass Summary

- Orphan chunk groups found: **4**
- Total orphans across groups: **52**
- Schema-gap orphans: **0**
- Orphan edges added (LLM confirmed): **0**
- Orphan edges rejected: **52**
- Promoted to schema-gap orphan: **13**

**Orphans remaining in final KG:** 13

- `organization-mit` (Organization)
- `organization-stanford` (Organization)
- `project-data-lake-migration` (Project)
- `technology-weaviate` (Technology)
- `technology-qdrant` (Technology)
- `technology-github-actions` (Technology)
- `technology-kubernetes-eks` (Technology)
- `technology-pytorch` (Technology)
- `technology-hugging-face-transformers` (Technology)
- `technology-fastapi` (Technology)
- `technology-go` (Technology)
- `technology-react` (Technology)
- `technology-typescript` (Technology)

## 8. Warnings & Retries

*No warnings or errors recorded.*

---
*Generated 2026-06-07T21:32:49 UTC*