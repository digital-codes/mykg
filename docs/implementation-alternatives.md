# Knowledge Graph Extractor — Implementation Alternatives

> **Configuration note:** All numeric constants in this document (chunk window sizes, batch token targets, edge ID format, namespace URIs, confidence aggregation, etc.) are now configurable via `pipeline_config.yaml → pipeline.*`. The hardcoded values shown are the defaults. See `README.md` and `src/mykg/config.py` for the full parameter list.

## Context & Requirements

This document captures the brainstorming session for a two-pass knowledge graph extractor that reads Markdown files and produces a property graph.

### Key Requirements Established

| Dimension | Decision |
|---|---|
| **Input** | Markdown files — mix of personal notes, technical docs, domain-specific content |
| **Primary use cases** | Search & retrieval, LLM reasoning/Q&A, visualization |
| **LLM backend** | Provider-agnostic / pluggable |
| **Output format** | Property graph (`nodes.jsonl` + `edges.jsonl`) + RDF/OWL (`knowledge_graph.ttl`) |
| **Ontology model** | Concept taxonomy (`is-a` hierarchy) + standard RDFS properties for relationships |
| **Uncertainty handling** | Confidence scores on every node and relationship instance |
| **Interface** | Python library + CLI wrapper |

---

## The Two-Pass Concept

All three options share the same fundamental two-pass structure:

- **Pass 1 — Schema Induction:** Read the input files and derive a *schema* — the vocabulary of concept types (e.g., `Person`, `Technology`, `Project`), attribute names (e.g., `name`, `founded_date`), and relationship types (e.g., `works_at`, `depends_on`).
- **Pass 2 — Instance Extraction:** Use the schema as a structured prompt template to extract concrete *instances* (individuals), their attribute values, and relationship instances. The LLM returns `nodes[]` (concept instances) and `edges[]` (relationship instances with `from`/`to`/`type`/`attributes`). Every extracted element carries a confidence score. The assembler deduplicates, writes the edge metadata sidecar, and produces `edges.jsonl` and `knowledge_graph.ttl`.

The three options differ in *how and when* the schema is built.

---

## Option A — Sequential Two-Pass with Global Schema

**Recommended approach.**

### High-Level Algorithm

```
INPUT: directory of .md files

PASS 1 — SCHEMA INDUCTION
─────────────────────────
1. Pre-process files
   - Parse frontmatter metadata (YAML/TOML headers)
   - Extract headings, lists, code blocks as structural signals
   - Chunk large files into overlapping windows (configured via `pipeline_config.yaml → pipeline.chunking`; defaults: 2000 tokens window, 200 token overlap)

2. Batch chunks → LLM (schema induction prompt)
   - For each batch, ask LLM:
     "Given these documents, identify:
      - Concept types (classes) and their likely attributes
      - Relationship types between concept types
      - Metadata signals (frontmatter keys, heading patterns)"
   - Collect per-batch schema proposals

3. Merge batch proposals → candidate global schema
   concepts[] merge:
   - Union all concept types across proposals; deduplicate by exact name first
   - Resolve near-duplicates via synonym_match() — exact/normalised string,
     then SKOS thesaurus if --thesaurus provided
     (e.g. "ML Model" + "Machine Learning Model" → "MLModel")
   - For each merged concept: union attribute lists from all proposals;
     keep the most specific parent (deepest in the hierarchy)
   properties[] merge:
   - Union all properties by name; deduplicate exact matches
   - For conflicting domain/range on same property name: keep the most general
     (e.g. "Person" vs "SoftwareEngineer" → keep "Person")
   - For attributes on same property: union the lists
   - Write result as intermediate/schema.json — same concepts[]+properties[] structure
     as a single-batch proposal

4. [Optional human review gate]
   - schema.json is human-readable and editable before Pass 2 runs
   - User can add, rename, or remove concept types and properties at this point

─────────────────────────
PASS 2 — INSTANCE EXTRACTION
─────────────────────────
5. For each file (independently):
   - Feed file content + global schema to LLM
   - Prompt: "Extract all instances of these concept types,
     their attributes, and relationships. For each item,
     provide a confidence score 0.0–1.0."
   - LLM returns structured JSON: nodes[] (concept instances) + edges[] (relationship instances)
   - edges[] contain: id, type (property name from schema), from (node ID), to (node ID),
     confidence, attributes (role, start_date, etc.)

6. Assemble property graph
   a. Node ID assignment
      - Generate stable ID for each node: hash(type + canonical_name)
      - Canonical name = lowercased, whitespace-normalized label
      - Same entity mentioned in multiple files → same ID

   b. Deduplication
      - Group all extracted nodes by ID across all files
      - For each group with >1 occurrence:
        * Merge attribute values — keep the value with highest confidence
        * Aggregate confidence: mean or max (configurable)
        * Record provenance: list of source files where the node appeared
      - Write merged nodes → intermediate/raw_extractions.json
      - Log every merge decision → intermediate/merge_log.json
        (which files contributed, which attribute value won, confidence delta)

   c. Edge deduplication
      - Edges deduplicated by: hash(type + from_id + to_id)
      - Duplicate edges from different files → merge attributes keeping highest confidence,
        aggregate confidence (mean), union source_files
      - Write intermediate/edge_metadata.json: all deduplicated edges keyed by edge ID

   d. Materialization
      - Export output/edges.jsonl: flat edge records from edge_metadata.json sidecar
      - Export output/nodes.jsonl: one record per deduplicated node with full attributes
      - Export output/knowledge_graph.ttl — two sections:

        SECTION 1: TBox — generated from intermediate/schema.json
        ──────────────────────────────────────────────────────────
        For each entry in concepts[]:
          ex:X rdf:type rdfs:Class .
          ex:X rdfs:subClassOf ex:Parent .   (omit if parent is null)

        For each attribute in concepts[].attributes[]:
          ex:attr rdf:type rdf:Property ;
              rdfs:domain ex:X ;             (the concept that owns this attribute)
              rdfs:range  rdfs:Literal .     (always Literal — datatype properties)

        For each entry in properties[]:
          ex:p rdf:type rdf:Property ;
              rdfs:domain ex:Domain ;        (the subject class)
              rdfs:range  ex:Range .         (the object class — another entity, not Literal)

        SECTION 2: ABox — generated from deduplicated nodes[] + edge_metadata.json
        ──────────────────────────────────────────────────────────────────────────
        For each node:
          data:ID rdf:type ex:Type .
          data:ID ex:attr "value" .          (one triple per non-null attribute value)
          data:ID skos:altLabel "alias" .    (one triple per alias, when aliases present)

        For each edge in edge_metadata.json:
          data:FromID ex:property_name data:ToID .   (one direct object property triple)

OUTPUT: intermediate/schema.json, intermediate/flattened_schema.json,
        intermediate/raw_extractions.json, intermediate/edge_metadata.json,
        intermediate/merge_log.json,
        output/knowledge_graph.ttl, output/nodes.jsonl, output/edges.jsonl
```

### Workflow Diagram

```
┌─────────────┐     ┌─────────────┐     ┌──────────────────┐
│  .md files  │────▶│  Pre-process│────▶│  Batch chunks    │
└─────────────┘     │  + chunk    │     │  → LLM (Pass 1)  │
                    └─────────────┘     └────────┬─────────┘
                                                 │ schema proposals
                                        ┌────────▼─────────┐
                                        │  Merge → Global  │
                                        │  Schema          │
                                        └────────┬─────────┘
                                                 │ [optional review]
                                        ┌────────▼─────────┐
                                        │  Per-file LLM    │
                                        │  extraction      │
                                        │  (Pass 2)        │
                                        └────────┬─────────┘
                                                 │ nodes[] + edges[] per file
                                        ┌────────▼──────────────────────┐
                                        │  Assemble                     │
                                        │  a. Stable ID assignment      │
                                        │  b. Node deduplication        │
                                        │     (merge attrs, agg conf)   │
                                        │  c. Edge dedup                │
                                        │     hash(type+from+to)        │
                                        │  d. Write edge_metadata.json  │
                                        │  e. Export nodes.jsonl        │
                                        │  f. Export edges.jsonl        │
                                        │  g. Export knowledge_graph.ttl│
                                        │     TBox: schema.json →       │
                                        │       rdfs:Class per concept  │
                                        │       rdf:Property (Literal)  │
                                        │         per concept attribute │
                                        │       rdf:Property (entity)   │
                                        │         per properties[] entry│
                                        │     ABox: nodes+edges →       │
                                        │       rdf:type per node       │
                                        │       literal triples per attr│
                                        │       object triple per edge  │
                                        └────────┬──────────────────────┘
                                                 ▼
                          intermediate/schema.json, flattened_schema.json,
                          raw_extractions.json, edge_metadata.json, merge_log.json
                          output/knowledge_graph.ttl, nodes.jsonl, edges.jsonl
```

### Detailed Step-by-Step Workflow

---

#### STEP 1 — Pre-process & Chunk (+ optional base schema + thesaurus load)

```
DATA IN:   input/*.md                    (raw Markdown files, arbitrary size)
           --base-schema <file>.ttl      (optional; a locked RDFS TBox to extend)
           --thesaurus <file>.skos.ttl   (optional; SKOS thesaurus for synonym resolution)
                                         (if omitted, synonym resolution uses exact + normalised
                                          string match only — no thesaurus lookup)

OPERATION:
  [If --base-schema provided]
    1a. Parse the TTL file using rdflib:
          g = rdflib.Graph()
          g.parse(base_schema_path, format="turtle")
    1b. Extract locked classes:
          locked_classes = {
            str(s).split("/")[-1]: {
              "type": str(s).split("/")[-1],
              "parent": str(o).split("/")[-1] if (s, RDFS.subClassOf, o) in g else None,
              "attributes": []   (datatype properties collected in next step)
            }
            for s, p, o in g if p == RDF.type and o == RDFS.Class
          }
    1c. Collect datatype property attributes per class:
          for s, p, o in g:
            if p == RDF.type and o == RDF.Property:
              domain = g.value(s, RDFS.domain)
              range_ = g.value(s, RDFS.range)
              if range_ == RDFS.Literal and domain in locked_classes:
                locked_classes[domain]["attributes"].append(str(s).split("/")[-1])
    1d. Extract locked object properties:
          locked_properties = {
            str(s).split("/")[-1]: {
              "name": str(s).split("/")[-1],
              "domain": str(g.value(s, RDFS.domain)).split("/")[-1],
              "range":  str(g.value(s, RDFS.range)).split("/")[-1],
              "attributes": []
            }
            for s, p, o in g if p == RDF.type and o == RDF.Property
                              and g.value(s, RDFS.range) != RDFS.Literal
          }
    1e. Write parsed base schema to disk:
          intermediate/base_schema_parsed.json
          {
            "source": "<path to TTL file>",
            "locked_classes":     { ... },
            "locked_properties":  { ... }
          }
    1f. Validate base schema (same checks as Step 3b Phase B):
          on error: halt immediately with clear message — the user-supplied file is invalid

  [If --thesaurus provided]
    1g. Parse SKOS file using rdflib:
          g = rdflib.Graph()
          g.parse(thesaurus_path, format="turtle")
        Build synonym index from SKOS relations:
          skos:exactMatch  → definite synonyms (collapse without warning)
          skos:closeMatch  → near-synonyms (collapse with warning in merge_log.json)
          skos:broader     → hypernym (candidate parent class — advisory only)
          skos:narrower    → hyponym (candidate child class — advisory only)
        Index structure: { "term": {"exact": [...], "close": [...],
                                    "broader": [...], "narrower": [...]} }
    1h. Write thesaurus metadata to disk:
          intermediate/thesaurus_parsed.json
          {
            "source": "custom_skos.ttl",
            "term_count": 1842,
            "relations_used": ["skos:exactMatch", "skos:closeMatch"]
          }

  [For each .md file]
    2a. Parse YAML/TOML frontmatter → extract key/value metadata pairs
    2b. Extract structural signals: headings (H1–H4), bullet lists, code blocks
    2c. Measure token count (tiktoken, cl100k_base encoding)
    2d. If file > window_tokens → split into overlapping windows:
          window size = pipeline_config.yaml → pipeline.chunking.window_tokens   (default: 2000)
          overlap     = pipeline_config.yaml → pipeline.chunking.overlap_tokens  (default: 200)
          encoding    = pipeline_config.yaml → pipeline.chunking.tiktoken_encoding (default: cl100k_base)
        Else → single chunk = entire file
    2e. Tag each chunk with: source_file, chunk_index, token_start, token_end

DATA OUT:  list of chunks, each:
  {
    "source_file": "team.md",
    "chunk_index": 0,
    "text": "## Team\n\nAlice is a senior engineer..."
  }

  intermediate/base_schema_parsed.json  (only if --base-schema was provided)
  {
    "source": "vehicles.ttl",
    "locked_classes": {
      "Vehicle":    {"type": "Vehicle",    "parent": null,      "attributes": ["name", "year"]},
      "ElectricCar":{"type": "ElectricCar","parent": "Vehicle", "attributes": ["range_km"]}
    },
    "locked_properties": {
      "manufactured_by": {"name": "manufactured_by", "domain": "Vehicle",
                          "range": "Manufacturer", "attributes": []}
    }
  }

  intermediate/thesaurus_parsed.json  (only if --thesaurus was provided)
  {
    "source": "custom_skos.ttl",
    "term_count": 1842,
    "relations_used": ["skos:exactMatch", "skos:closeMatch"]
  }
```

---

#### STEP 2 — Pass 1 LLM Calls (Schema Induction per Batch)

```
DATA IN:   chunks from Step 1
           Pass 1 system prompt (teaches concepts[]+properties[] format)
           intermediate/base_schema_parsed.json  (optional — present only if --base-schema given)

OPERATION:
  Group chunks into batches (target: pipeline_config.yaml → pipeline.pass1.batch_token_target; default: ~8000 tokens per batch)

  All batches are dispatched in parallel via `ThreadPoolExecutor` (worker count: `pipeline.pass1.max_workers`, default 4). Each worker makes one independent LLM call for its batch; results are collected, sorted by batch index for determinism, and filtered for parse failures.

  When `pipeline.pass1.per_file_batching` is true, chunks from different files are never mixed in one batch — this is the Option B batching strategy applied within Pass 1.

  [If base_schema_parsed.json exists]
    Build a locked schema block to inject into every batch prompt:
      EXISTING SCHEMA (DO NOT RENAME, REMOVE, OR DUPLICATE THESE):
      Classes:    Vehicle, ElectricCar, Manufacturer
      Properties: manufactured_by (Vehicle → Manufacturer)
      You may add new subclasses of these, new properties, or new root classes.
      You may add new attributes to existing classes.
      Do not output any of the locked names as new entries — they already exist.

  For each batch:
    1. Build prompt:
         system: Pass 1 system prompt
                 + locked schema block (if base schema present)
         user:   concatenated chunk texts in this batch
    2. Call LLM → receive raw JSON response
    3. Parse and validate response structure:
         must have keys: "concepts", "properties"
         each concept must have: type (str), parent (str|null), attributes (list)
         each property must have: name (str), domain (str), range (str), attributes (list)
    4. On parse failure: log error, skip batch, continue

DATA OUT:  list of per-batch schema proposals, each:
  {
    "source_batch": [0, 1],
    "concepts": [
      {"type": "Person",           "parent": null,     "attributes": ["name", "email", "birth_date"]},
      {"type": "SoftwareEngineer", "parent": "Person", "attributes": ["programming_languages", "seniority"]},
      {"type": "Organization",     "parent": null,     "attributes": ["name", "industry"]}
    ],
    "properties": [
      {"name": "works_at", "domain": "Person", "range": "Organization",
       "attributes": ["role", "start_date", "end_date"]}
    ]
  }
```

---

#### STEP 3 — Merge Schema Proposals → Global Schema

```
DATA IN:   list of per-batch schema proposals from Step 2
           intermediate/base_schema_parsed.json   (optional)
           intermediate/thesaurus_parsed.json      (optional — present only if --thesaurus given)

OPERATION:
  Define synonym_match(a, b) — used throughout merge for near-duplicate detection:
    **Important: this function is purely lexical — no LLM is involved.**
    It collapses type names that are the same word written differently (formatting variation),
    NOT names that are semantically related. "SoftwareEngineer" and "Developer" are different
    words and will NOT be collapsed unless a thesaurus explicitly maps them.
    Semantic synonyms can only be resolved by:
      (a) the LLM proposing a single unified type during Pass 1 schema induction, or
      (b) supplying a --thesaurus file with skos:exactMatch / skos:closeMatch entries, or
      (c) the human review gate (Step 4) — manually merging types in schema.json.

    Normalisation algorithm (applied to both names before comparing):
      Step 1: insert underscore at lowercase→uppercase boundary (PascalCase split)
                "SoftwareEngineer" → "Software_Engineer"
      Step 2: collapse all spaces, hyphens, and underscores to a single underscore, lowercase
                "Software_Engineer" → "software_engineer"
                "Software Engineer" → "software_engineer"   ← matches above
                "Software-Engineer" → "software_engineer"   ← matches above

    What normalisation catches:
      "SoftwareEngineer" == "Software Engineer"  → True  (PascalCase vs spaced)
      "SoftwareEngineer" == "Software-Engineer"  → True  (PascalCase vs hyphenated)
      "works_at"         == "WorksAt"            → True  (snake_case vs PascalCase)

    What normalisation does NOT catch (acronyms have no lowercase boundary):
      "MLModel" vs "ML Model" → False  (both normalise to different strings)
      Use a --thesaurus entry for acronym variants.

    1. Exact string match → True (always checked first)
    2. Normalise both (PascalCase split + collapse separators + lowercase)
       If normalised strings match → True
    3. If thesaurus loaded:
         check if b ∈ index[a]["exact"] or a ∈ index[b]["exact"] → True (definite, silent collapse)
         check if b ∈ index[a]["close"] or a ∈ index[b]["close"] → True (near, collapse with warning)
    4. Otherwise → False  (no thesaurus = no lookup beyond steps 1–2)

  [If base_schema_parsed.json exists]
    Seed the merge with locked_classes and locked_properties as the authoritative base.
    Lock rules (enforced throughout all merge steps):
      - A locked class name may never be renamed, removed, or have its parent changed
      - A locked class may receive additional attributes (union with LLM proposals)
      - A locked property name may never be renamed, removed, or have its domain/range changed
      - A locked property may receive additional edge attributes (union with LLM proposals)
      - LLM proposals where synonym_match(proposal, locked_name) is True (exact):
        merge into locked entry — attributes unioned, structure from locked entry wins
      - LLM proposals where synonym_match(proposal, locked_name) is True (near):
        collapse into locked entry, log warning to merge_log.json

  concepts[] merge:
    1. Start with locked_classes as the base set (empty dict if no base schema)
    2. Collect all concept types from LLM proposals
    3. For each proposal concept:
         a. If synonym_match(proposal, any locked class) → merge into locked entry; skip
         b. Otherwise: add to induced concept pool
    4. Among induced concepts, find and collapse synonym pairs:
         For each pair (a, b) in induced pool:
           if synonym_match(a, b):
             if SKOS exact match: collapse silently → keep the name that appears most across proposals
             if SKOS close match: collapse with warning → log both names,
               chosen name, and thesaurus evidence to merge_log.json
    5. For each surviving induced concept: union attribute lists; keep most specific parent
    6. Verify every non-null parent resolves to a declared concept (locked or induced)

  properties[] merge:
    1. Start with locked_properties as the base set (empty dict if no base schema)
    2. Collect all properties from LLM proposals
    3. For each proposal property:
         a. If synonym_match(proposal, any locked property) → merge into locked entry; skip
         b. Otherwise: add to induced property pool
    4. Among induced properties, find and collapse synonym pairs using synonym_match:
         Collapse silently on exact match; collapse with warning on near match
    5. For same name with conflicting domain/range: keep the most general class
    6. For same name with different edge attributes: union the attribute lists
    7. Verify domain and range refer to class names present in merged concepts[]

  Write result to disk as JSON.
  Then generate schema.ttl from the merged schema using the same TBox rules as Step 12
  Section 1 (classes + hierarchy + datatype properties + object properties) — no ABox yet.

DATA OUT:  intermediate/schema.json
  {
    "concepts": [
      {"type": "Person",           "parent": null,     "attributes": ["name", "email", "birth_date"]},
      {"type": "SoftwareEngineer", "parent": "Person", "attributes": ["programming_languages", "seniority"]},
      {"type": "Organization",     "parent": null,     "attributes": ["name", "industry", "founded_date"]}
    ],
    "properties": [
      {"name": "works_at", "domain": "Person", "range": "Organization",
       "attributes": ["role", "start_date", "end_date"]}
    ]
  }

  intermediate/schema.ttl  (TBox only — no instance data)
  # Namespaces and prefix labels are configurable via pipeline_config.yaml → pipeline.export.*
  @prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
  @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
  @prefix ex:   <http://mykg.local/schema/> .   # schema_prefix_label + schema_namespace

  # Define Classes
  ex:Person           rdf:type rdfs:Class .
  ex:SoftwareEngineer rdf:type rdfs:Class .
  ex:Organization     rdf:type rdfs:Class .

  # Create Class Hierarchy
  ex:SoftwareEngineer rdfs:subClassOf ex:Person .

  # Define Datatype Properties
  ex:name rdf:type rdf:Property ;
      rdfs:domain ex:Person ;
      rdfs:range  rdfs:Literal .

  ex:email rdf:type rdf:Property ;
      rdfs:domain ex:Person ;
      rdfs:range  rdfs:Literal .

  # Define Object Properties
  ex:works_at rdf:type rdf:Property ;
      rdfs:domain ex:Person ;
      rdfs:range  ex:Organization .
```

---

#### STEP 3b — Validate schema.ttl (RDFS Validation Gate)

```
DATA IN:   intermediate/schema.ttl   (generated in Step 3)
           intermediate/schema.json  (used to cross-check semantic rules)

OPERATION:
  Phase A — Syntax validation (rdflib parse):
    1. Attempt to parse schema.ttl using rdflib:
         g = rdflib.Graph()
         g.parse("intermediate/schema.ttl", format="turtle")
    2. On ParseError: catch exception, record error message and line number

  Phase B — Semantic validation (custom checks on parsed graph):
    3. Collect all declared classes:
         declared_classes = {s for s, p, o in g if p == RDF.type and o == RDFS.Class}
    4. Check every rdfs:domain value is a declared class
    5. Check every rdfs:range value is either rdfs:Literal or a declared class
    6. Check every rdfs:subClassOf parent is a declared class
    7. Check no property has both rdfs:Literal and entity range (conflicting range)
    8. Check every non-null parent in concepts[] resolves to a declared class (no orphan concepts)

  Phase C — Gate decision and optional LLM correction:
    - If NO errors:
        log "schema.ttl valid (N classes, M properties)"
        → proceed directly to STEP 4

    - If errors found (first attempt):
        write schema_validation_errors.json, print formatted report
        → send errors back to LLM with a schema correction prompt (one retry only):

        Correction prompt sent to LLM:
        ┌──────────────────────────────────────────────────────────────┐
        │ The schema you produced contains RDFS validation errors.     │
        │ Please return a corrected schema.json fixing the issues      │
        │ listed below. Return the complete corrected JSON only —      │
        │ same format as before (concepts[] + properties[]).           │
        │                                                              │
        │ ERRORS:                                                      │
        │ [1] ex:works_at rdfs:range ex:Organisation                   │
        │     → ex:Organisation is not a declared rdfs:Class           │
        │     → Did you mean ex:Organization?                          │
        │ [2] ex:SoftwareEngineer rdfs:subClassOf ex:Employe           │
        │     → ex:Employe is not a declared rdfs:Class                │
        │     → Did you mean ex:Employee?                              │
        └──────────────────────────────────────────────────────────────┘

        → LLM returns corrected schema JSON
        → overwrite intermediate/schema.json with corrected version
        → regenerate intermediate/schema.ttl from corrected schema.json
        → run Phase A + Phase B validation one more time (second attempt)
        → regardless of second validation result: proceed to STEP 4
          (second attempt errors, if any, are appended to schema_validation_errors.json
           for the human reviewer)

DATA OUT (always):  pipeline proceeds to STEP 4

  intermediate/schema_validation_errors.json  (written only if first attempt had errors)
  {
    "first_attempt": {
      "valid": false,
      "errors": [
        {
          "type": "undefined_range",
          "property": "ex:works_at",
          "range": "ex:Organisation",
          "message": "rdfs:range ex:Organisation is not a declared rdfs:Class",
          "hint": "Did you mean ex:Organization?"
        },
        {
          "type": "undefined_parent",
          "concept": "ex:SoftwareEngineer",
          "parent": "ex:Employe",
          "message": "rdfs:subClassOf ex:Employe is not a declared rdfs:Class",
          "hint": "Did you mean ex:Employee?"
        }
      ]
    },
    "llm_correction_attempted": true,
    "second_attempt": {
      "valid": true,
      "errors": []
    }
  }
```

---

#### STEP 4 — [Optional] Human Review Gate
##### (always follows STEP 3b, with or without validation errors)

```
DATA IN:   intermediate/schema.json                       (editable source of truth)
           intermediate/schema.ttl                        (RDFS view — load in Protégé)
           intermediate/schema_validation_errors.json     (present only if Step 3b found issues)

OPERATION:
  Always reached after Step 3b, regardless of validation outcome.
  If schema_validation_errors.json is present, the human reviewer reads it first
  and decides what (if anything) to fix before approving the schema.
  The human review covers both validator-flagged issues and semantic correctness
  the validator cannot catch: wrong concept granularity, missing properties,
  misnamed types, incomplete attribute lists.

  Pipeline pauses. User reviews both files:
    - schema.ttl can be loaded into Protégé or a SPARQL endpoint to visually inspect
      the class hierarchy and property definitions before any extraction runs
    - schema.json is the file to EDIT — it is the pipeline's source of truth
  User may edit schema.json to:
    - Add new concept types or properties
    - Rename types (e.g. "Org" → "Organization")
    - Remove spurious types the LLM hallucinated
    - Adjust parent relationships
    - Add or remove attribute names
  After editing schema.json, re-run the schema.ttl export to keep them in sync.
  User signals approval (CLI flag or file touch) → pipeline proceeds to Step 5.

  Note: schema.ttl is always regenerated from schema.json — never edit schema.ttl directly,
  as changes will be overwritten on the next run.

DATA OUT:  intermediate/schema.json  (same file, possibly edited)
           intermediate/schema.ttl   (regenerated if schema.json was edited)
```

---

#### STEP 5 — Flatten Schema for Extraction Prompts

```
DATA IN:   intermediate/schema.json

OPERATION:
  For each concept in concepts[]:
    1. Walk the parent chain to the topmost ancestor (parent == null)
    2. Collect own attributes at each level
    3. Concatenate in order: root attrs → ... → own attrs
         SoftwareEngineer:
           Person:           [name, email, birth_date]
           + SoftwareEngineer: [programming_languages, seniority]
           = flat:             [name, email, birth_date,
                                programming_languages, seniority]
    4. Store flat list keyed by concept type

DATA OUT:  intermediate/flattened_schema.json
  {
    "Person":           ["name", "email", "birth_date"],
    "SoftwareEngineer": ["name", "email", "birth_date",
                         "programming_languages", "seniority"],
    "Organization":     ["name", "industry", "founded_date"]
  }
```

---

#### STEP 6 — Pass 2 LLM Calls (Instance Extraction per File)

```
DATA IN:   input/*.md  (original files, not chunks — Pass 2 works file-by-file)
           intermediate/schema.json            (concept + property definitions)
           intermediate/flattened_schema.json  (flat attribute lists per concept)
           Pass 2 system prompt (teaches nodes[]+edges[] format)

OPERATION:  (all files run in parallel)
  For each file:
    1. Build extraction prompt:
         system: Pass 2 system prompt
         user:   file content + schema summary showing:
                   - each concept type with its FLAT attribute list
                   - each property with domain, range, edge attributes
    2. Call LLM → receive raw JSON response
    3. Validate response:
         - top-level keys must be exactly "nodes" and "edges"
         - each node.type must match a concept name in schema
         - each edge.type must match a property name in schema
         - each edge.from and edge.to must be node IDs present in this response's nodes[]
         - no attribute may be omitted (null is allowed, omission is not)
    4. On validation failure: log raw response, emit warning, optionally retry once
       with error-correction prompt
    5. Append validated result to raw extractions

DATA OUT:  intermediate/raw_extractions.json  (one entry per file)
  {
    "team.md": {
      "nodes": [
        {
          "id": "person-alice",
          "type": "SoftwareEngineer",
          "confidence": 0.97,
          "attributes": {
            "name":                  {"value": "Alice",            "confidence": 0.99},
            "description":           {"value": null,               "confidence": 0.0},
            "email":                 {"value": "alice@acme.com",   "confidence": 0.97},
            "birth_date":            {"value": null,               "confidence": 0.0},
            "programming_languages": {"value": ["Python", "Rust"], "confidence": 0.98},
            "seniority":             {"value": "senior",           "confidence": 0.95}
          }
        },
        {
          "id": "org-acme-corp",
          "type": "Organization",
          "confidence": 0.99,
          "attributes": {
            "name":         {"value": "Acme Corp", "confidence": 0.99},
            "description":  {"value": null,         "confidence": 0.0},
            "industry":     {"value": null,         "confidence": 0.0},
            "founded_date": {"value": null,         "confidence": 0.0}
          }
        }
      ],
      "edges": [
        {
          "id": "edge-001",
          "type": "works_at",
          "from": "person-alice",
          "to":   "org-acme-corp",
          "confidence": 0.96,
          "attributes": {
            "role":       {"value": "engineer", "confidence": 0.91},
            "start_date": {"value": null,       "confidence": 0.0},
            "end_date":   {"value": null,       "confidence": 0.0}
          }
        }
      ]
    }
  }
```

---

#### STEP 7 — Stable ID Assignment

```
DATA IN:   intermediate/raw_extractions.json

OPERATION:
  For each node across all files:
    1. canonical_name = node.attributes.name.value
                        → lowercase
                        → strip leading/trailing whitespace
                        → collapse internal whitespace to single space
    2. stable_id = "<type-prefix>-<name-slug>"
         type-prefix = node.type.lower()  (e.g. "softwareengineer", "organization")
         name-slug   = canonical_name with spaces replaced by hyphens
         e.g. "softwareengineer-alice", "organization-acme-corp"
    3. Replace LLM-generated id with stable_id in all node records
    4. Update all edge.from and edge.to references to use stable_ids

DATA OUT:  raw_extractions.json updated in place with stable IDs on all nodes and edges
```

---

#### STEP 8 — Node Deduplication

```
DATA IN:   intermediate/raw_extractions.json  (stable IDs assigned)

OPERATION:
  1. Collect all nodes across all files; group by stable_id
  2. For each group with >1 occurrence (same entity appeared in multiple files):
       For each attribute:
         - keep the value with the highest confidence score
         - if both values are strings at confidence 1.0 and differ: concatenate with "; " (lossless merge)
         - otherwise if tied: keep first seen
       Aggregate node confidence: mean of all per-file confidence scores
       Union source_files: list of all files that mentioned this node
  3. For each group with exactly 1 occurrence: pass through, set source_files = [that file]
  4. Log every merge decision:
       which files contributed, which attribute value won, losing value, confidence delta

DATA OUT:
  deduplicated node list (held in memory, passed to Steps 10 and 12)

  intermediate/merge_log.json
  {
    "node_merges": [
      {
        "stable_id": "softwareengineer-alice",
        "source_files": ["team.md", "projects.md"],
        "attribute_decisions": {
          "email": {
            "winner": "alice@acme.com",  "winner_conf": 0.97,
            "loser":  "a@acme.com",      "loser_conf":  0.61,
            "winner_source": "team.md"
          }
        },
        "confidence_agg": "mean",
        "final_confidence": 0.94
      }
    ]
  }
```

---

#### STEP 9 — Edge Deduplication

```
DATA IN:   intermediate/raw_extractions.json  (all edges across all files)

OPERATION:
  1. For each edge compute dedup key: hash(edge.type + "|" + edge.from + "|" + edge.to)
  2. Group edges by dedup key
  3. For each group with >1 occurrence:
       For each edge attribute: keep value with highest confidence; if both are strings at confidence 1.0 and differ, concatenate with "; "
       Aggregate edge confidence: mean across all occurrences
       Union source_files
  4. Assign final edge ID: pipeline.assembly.edge_id_prefix + first N chars of dedup key hash
         (prefix default: "edge-"; N = pipeline.assembly.edge_id_hex_length default: 6)
         separator used in dedup key: pipeline.assembly.edge_dedup_separator (default: "|")
  5. Append edge merge decisions to merge_log.json

DATA OUT:
  intermediate/edge_metadata.json
  {
    "edge-a3f1bc": {
      "type":       "works_at",
      "from":       "softwareengineer-alice",
      "to":         "organization-acme-corp",
      "confidence": 0.96,
      "attributes": {
        "role":       {"value": "engineer", "confidence": 0.91},
        "start_date": {"value": null,       "confidence": 0.0},
        "end_date":   {"value": null,       "confidence": 0.0}
      },
      "source_files": ["team.md"]
    }
  }
```

---

#### STEP 10 — Export nodes.jsonl

```
DATA IN:   deduplicated node list from Step 8

OPERATION:
  For each deduplicated node: serialize to one compact JSON line

DATA OUT:  output/nodes.jsonl
  {"id":"softwareengineer-alice","type":"SoftwareEngineer","confidence":0.97,"source_files":["team.md"],"attributes":{"name":{"value":"Alice","confidence":0.99},"description":{"value":null,"confidence":0.0},"email":{"value":"alice@acme.com","confidence":0.97},"birth_date":{"value":null,"confidence":0.0},"programming_languages":{"value":["Python","Rust"],"confidence":0.98},"seniority":{"value":"senior","confidence":0.95}}}
  {"id":"organization-acme-corp","type":"Organization","confidence":0.99,"source_files":["team.md"],"attributes":{"name":{"value":"Acme Corp","confidence":0.99},"description":{"value":null,"confidence":0.0},"industry":{"value":null,"confidence":0.0},"founded_date":{"value":null,"confidence":0.0}}}
```

---

#### STEP 11 — Export edges.jsonl

```
DATA IN:   intermediate/edge_metadata.json from Step 9
           intermediate/schema.json (properties[] — for declared-predicate filter)

OPERATION:
  1. Filter edge_metadata to valid_edge_metadata: keep only edges whose "type" is
     declared in schema["properties"][*]["name"]. Edges whose type was dropped from
     the schema by harmonization/quality-review (common in cross-session merges) are
     excluded. intermediate/edge_metadata.json is left untouched — it is the
     unfiltered source of truth.
  2. For each edge in valid_edge_metadata: serialize to one compact JSON line.

  NOTE: The same valid_edge_metadata set is used for all three output formats
  (edges.jsonl, knowledge_graph.ttl, NetworkX). All formats are always in sync.

DATA OUT:  output/edges.jsonl
  {"id":"edge-a3f1bc","type":"works_at","from":"softwareengineer-alice","to":"organization-acme-corp","confidence":0.96,"source_files":["team.md"],"attributes":{"role":{"value":"engineer","confidence":0.91},"start_date":{"value":null,"confidence":0.0},"end_date":{"value":null,"confidence":0.0}}}
```

---

#### STEP 12 — Export knowledge_graph.ttl

```
DATA IN:   intermediate/schema.json          (concepts[] + properties[])
           deduplicated node list from Step 8
           valid_edge_metadata               (filtered subset of edge_metadata.json — see Step 11)

OPERATION:
  1. Build TTL from valid_edge_metadata (same filtered set as edges.jsonl).
  2. Run sanitize_abox_ttl() — regex pass that strips any ABox object-property line
     whose predicate is not in schema["properties"]. This is a safety net for edge
     cases where the in-memory filter missed something (e.g. a TTL serialization quirk).
  3. Run validate_knowledge_graph_ttl() — full rdflib + semantic check.
     If validation fails, errors are reported but the file is still written (advisory).
  4. Write output/knowledge_graph.ttl.

  Write prefixes, then two sections:

  SECTION 1 — TBox (from schema.json):

    # Define Classes
    For each concept in concepts[]:
      emit:  ex:Type rdf:type rdfs:Class .

    # Create Class Hierarchy
    For each concept where parent != null:
      emit:  ex:Child rdfs:subClassOf ex:Parent .

    # Define Datatype Properties (concept attributes → rdfs:Literal range)
    For each concept, for each attr in concept.attributes[]:
      emit:  ex:attr rdf:type rdf:Property ;
                 rdfs:domain ex:ConceptType ;
                 rdfs:range  rdfs:Literal .

    # Define Object Properties (properties[] entries → entity range)
    For each property in properties[]:
      emit:  ex:prop rdf:type rdf:Property ;
                 rdfs:domain ex:Domain ;
                 rdfs:range  ex:Range .

  SECTION 2 — ABox (from nodes + edge_metadata.json):

    # Define Entities
    For each node:
      emit:  data:ID rdf:type ex:Type .

    # Datatype triples — skip null values
    For each node, for each attribute where value != null:
      emit:  data:ID ex:attr "value" .

    # Object property triples — one per edge
    For each edge in edge_metadata.json:
      emit:  data:FromID ex:property_name data:ToID .

DATA OUT:  output/knowledge_graph.ttl
  # Namespaces and prefix labels are configurable via pipeline_config.yaml → pipeline.export.*
  @prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
  @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
  @prefix ex:   <http://mykg.local/schema/> .   # schema_prefix_label + schema_namespace
  @prefix data: <http://mykg.local/data/> .     # data_prefix_label + data_namespace

  # ==========================================
  # 1. THE RDFS SCHEMA (The Blueprint)
  # ==========================================

  # Define Classes
  ex:Person           rdf:type rdfs:Class .
  ex:SoftwareEngineer rdf:type rdfs:Class .
  ex:Organization     rdf:type rdfs:Class .

  # Create Class Hierarchy
  ex:SoftwareEngineer rdfs:subClassOf ex:Person .

  # Define Datatype Properties
  ex:name rdf:type rdf:Property ;
      rdfs:domain ex:Person ;
      rdfs:range  rdfs:Literal .

  ex:email rdf:type rdf:Property ;
      rdfs:domain ex:Person ;
      rdfs:range  rdfs:Literal .

  # Define Object Properties
  ex:works_at rdf:type rdf:Property ;
      rdfs:domain ex:Person ;
      rdfs:range  ex:Organization .

  # ==========================================
  # 2. THE RDF INSTANCE DATA (The Facts)
  # ==========================================

  # Define Entities
  data:Alice    rdf:type ex:SoftwareEngineer .
  data:AcmeCorp rdf:type ex:Organization .

  # Use Properties to Link Entities
  data:Alice    ex:name     "Alice" .
  data:Alice    ex:email    "alice@acme.com" .
  data:AcmeCorp ex:name     "Acme Corp" .
  data:Alice    ex:works_at data:AcmeCorp .
```

---

#### STEP 12b — Validate knowledge_graph.ttl

```
DATA IN:   knowledge_graph.ttl string   (in memory, BEFORE writing to disk)

NOTE: Validation runs on the in-memory TTL string — not by re-reading the file.
  sanitize_abox_ttl() and validate_knowledge_graph_ttl() are both called in
  step_validate_graph before any output file is written. This guarantees that the written
  file, edges.jsonl, and NetworkX outputs are all consistent with the validated
  in-memory state.

OPERATION:
  Phase A — Syntax validation (rdflib parse):
    1. g = rdflib.Graph()
       g.parse(data=ttl_string, format="turtle")
    2. On ParseError: record error, skip Phase B

  Phase B — Semantic validation (TBox checks, same as Step 3b):
    3. Collect declared_classes, declared_properties from TBox triples
    4. Check every rdfs:domain / rdfs:range refers to a declared class
    5. Check every rdfs:subClassOf parent is a declared class
    6. Check every non-null parent in concepts[] resolves to a declared class (no orphan concepts)

  Phase C — Semantic validation (ABox checks, additional):
    7. Check every rdf:type object in ABox is a declared class
         data:Alice rdf:type ex:SoftwareEngineer → ex:SoftwareEngineer must be in declared_classes
    8. Check every datatype property predicate in ABox is a declared property
         data:Alice ex:name "Alice" → ex:name must be in declared_properties
    9. Check every object property triple's predicate is a declared property
         data:Alice ex:works_at data:AcmeCorp → ex:works_at must be in declared_properties
   10. Check every object property triple's object is a declared instance
         data:AcmeCorp must appear as a subject of an rdf:type triple

  Phase D — Report and complete:
    - Write output/knowledge_graph_validation.json with results
    - If NO errors: log "knowledge_graph.ttl valid"
    - If errors found: print formatted report (advisory — pipeline is already complete
      at this point; errors inform the user that the TTL may behave unexpectedly
      in downstream RDF tooling)

DATA OUT:  output/knowledge_graph_validation.json
  {
    "valid": true,
    "tbox_checks": {"classes": 4, "properties": 3, "errors": []},
    "abox_checks": {"instances": 2, "triples": 5, "errors": []}
  }

  Example with ABox error:
  {
    "valid": false,
    "tbox_checks": {"classes": 4, "properties": 3, "errors": []},
    "abox_checks": {
      "instances": 2,
      "triples": 5,
      "errors": [
        {
          "type": "undeclared_predicate",
          "triple": "data:Alice ex:seniority \"senior\"",
          "message": "ex:seniority is not a declared rdf:Property",
          "hint": "Check that seniority is listed in concepts[].attributes for SoftwareEngineer in schema.json"
        }
      ]
    }
  }
```

---

#### Summary — All Files Written

| Step | File | Format | Contents |
|---|---|---|---|
| 1 | `intermediate/base_schema_parsed.json` | JSON | Locked classes + properties parsed from `--base-schema` TTL (absent if no base schema) |
| 1 | `intermediate/thesaurus_parsed.json` | JSON | Thesaurus metadata — SKOS source path, term count, relations used (absent if no `--thesaurus`) |
| 3 | `intermediate/schema.json` | JSON | Merged RDFS schema: `concepts[]` + `properties[]` — source of truth |
| 3 | `intermediate/schema.ttl` | Turtle | TBox-only RDFS — validated by Step 3b; load in Protégé for review |
| 3b | `intermediate/schema_validation_errors.json` | JSON | Validation errors (written only on failure; absent if valid) |
| 5 | `intermediate/flattened_schema.json` | JSON | Flat attribute list per concept type |
| 6 | `intermediate/raw_extractions.json` | JSON | Raw `nodes[]`+`edges[]` per file, undeduped |
| 8 | `intermediate/merge_log.json` | JSON | Node merge decisions |
| 9 | `intermediate/edge_metadata.json` | JSON | Deduplicated edges keyed by edge ID |
| 9 | `intermediate/merge_log.json` | JSON | Edge merge decisions (appended) |
| 10 | `output/nodes.jsonl` | JSONL | One deduplicated node per line |
| 11 | `output/edges.jsonl` | JSONL | One deduplicated edge per line |
| 12 | `output/knowledge_graph.ttl` | Turtle | TBox (schema) + ABox (instances) |
| 12b | `output/knowledge_graph_validation.json` | JSON | TBox + ABox validation results (always written) |
| 12c | `output/networkx_output/` | Multiple | NetworkX formats (when `networkx_enabled: true`): GML, GraphML, GEXF, Pajek, JSON node-link, edge list, adjacency list; attributes flattened to `attr_<name>_value` / `attr_<name>_confidence` scalars |

---

### Re-run Guide — Restarting from Existing Artifacts

After reviewing final outputs and validation errors, the pipeline can be re-entered at three points depending on what needs fixing. All intermediate files are preserved between runs — only steps downstream of the re-entry point need to rerun.

#### Re-entry A — Schema changed (fix schema.json after Step 4 review)

Re-enter at: **STEP 3b**
Rerun: Steps 3b → 4 → 5 → 6 → 7 → 8 → 9 → 10 → 11 → 12 → 12b

**Trigger:** wrong concept name, missing property, bad parent chain, Step 3b errors not resolved by LLM

Steps:
1. Edit `intermediate/schema.json`
2. Regenerate `intermediate/schema.ttl` from `schema.json`
3. Re-enter at Step 3b (revalidate)
4. Continue from Step 4 onward — all extractions must rerun because the schema changed

#### Re-entry B — Extraction errors only (schema is correct, Pass 2 output is wrong)

Re-enter at: **STEP 6**
Reuse: `intermediate/schema.json`, `intermediate/flattened_schema.json`
Rerun: Steps 6 → 7 → 8 → 9 → 10 → 11 → 12 → 12b

**Trigger:** LLM missed entities, extracted wrong attribute values, invented edge types, `knowledge_graph_validation.json` shows ABox errors traceable to raw extractions

Steps:
1. Optionally edit `intermediate/raw_extractions.json` to fix specific file entries manually, OR delete specific file entries to force re-extraction for those files only
2. Re-enter at Step 6 for affected files (or all files if corrections are broad)
3. Continue from Step 7 onward

#### Re-entry C — Assembly errors only (raw extractions are correct, assembly is wrong)

Re-enter at: **STEP 7**
Reuse: `intermediate/schema.json`, `intermediate/flattened_schema.json`, `intermediate/raw_extractions.json`
Rerun: Steps 7 → 8 → 9 → 10 → 11 → 12 → 12b

**Trigger:** bad dedup decisions visible in `merge_log.json`, ABox validation errors in `knowledge_graph_validation.json` traceable to assembler logic rather than LLM output

Steps:
1. Review `intermediate/merge_log.json` to identify bad merge decisions
2. Optionally edit `intermediate/raw_extractions.json` to correct IDs or attribute values
3. Re-enter at Step 7 — assembler reruns from `raw_extractions.json`

#### Files Reused vs Regenerated per Re-entry Point

| File | Re-entry A | Re-entry B | Re-entry C |
|---|---|---|---|
| `intermediate/schema.json` | Edited then reused | Reused | Reused |
| `intermediate/schema.ttl` | Regenerated | Reused | Reused |
| `intermediate/flattened_schema.json` | Regenerated | Reused | Reused |
| `intermediate/raw_extractions.json` | Regenerated (full Pass 2 rerun) | Regenerated (full or partial) | Reused (or manually edited) |
| `intermediate/edge_metadata.json` | Regenerated | Regenerated | Regenerated |
| `intermediate/merge_log.json` | Regenerated | Regenerated | Regenerated |
| `output/nodes.jsonl` | Regenerated | Regenerated | Regenerated |
| `output/edges.jsonl` | Regenerated | Regenerated | Regenerated |
| `output/knowledge_graph.ttl` | Regenerated | Regenerated | Regenerated |
| `output/knowledge_graph_validation.json` | Regenerated | Regenerated | Regenerated |

---

### Trade-offs

| Pro | Con |
|---|---|
| Single reviewable schema artifact | Large corpora need careful batching |
| Low LLM call count → low cost | Global schema may miss niche local concepts |
| Clean confidence scoring in Pass 2 | Synonym resolution needs thesaurus for best results (optional) |
| Files extracted independently → parallelizable in Pass 2 | Schema quality depends on batch coverage |
| Human-in-the-loop gate between passes | |

---

## Option B — Per-File Schema + Late Merge

### High-Level Algorithm

```
INPUT: directory of .md files

PASS 1 — PER-FILE SCHEMA INDUCTION (fully parallelizable)
─────────────────────────
1. For each file independently:
   - Pre-process + chunk (same as Option A)
   - LLM call: "Induce a local schema for this document"
   - Output: local_schema_i.json per file

2. Schema merge step
   - Collect all local schemas
   - Build term-frequency index across all schemas
   - Use LLM (or string similarity) to cluster synonymous types:
     e.g. "ML Model" + "Machine Learning Model" + "Model" → "MLModel"
   - Produce unified global schema with provenance
     (which files contributed each type)

3. [Optional human review gate]
   - Write merged schema to schema.json

─────────────────────────
PASS 2 — INSTANCE EXTRACTION
─────────────────────────
4. For each file (independently, parallelizable):
   - Feed file content + unified schema to LLM
   - LLM returns nodes[] (concept instances) + edges[] (relationship instances)

5. Assemble property graph
   a. Node ID assignment
      - Same as Option A: hash(type + canonical_name)
      - Extra challenge: two files may have extracted the same entity under
        slightly different surface forms (e.g. "Acme" vs "Acme Corp")
        → fuzzy name matching pass before ID assignment
        → merge_log.json records fuzzy match decisions for human review

   b. Type normalization
      - Schema merge in Pass 1 may have aliased types
        (e.g. local "MLModel" mapped to global "Model")
      - Apply type alias map from schema merge step to all extracted nodes
        before deduplication

   c. Node deduplication
      - Same as Option A: group by ID, merge attributes, aggregate confidence
      - Provenance tracking is especially important here — record which
        local schema each node originated from

   d. Edge deduplication
      - Same as Option A: hash(type + from_id + to_id)
      - Fuzzy entity resolution applied to from/to IDs before hashing

   e. Materialization
      - Same as Option A: write edge_metadata.json + emit edges.jsonl + knowledge_graph.ttl

OUTPUT: intermediate/schema.json (per-file + merged), intermediate/flattened_schema.json,
        intermediate/raw_extractions.json, intermediate/edge_metadata.json,
        intermediate/merge_log.json,
        output/knowledge_graph.ttl, output/nodes.jsonl, output/edges.jsonl
```

### Workflow Diagram

```
┌─────────────┐     ┌──────────────────────────────────────┐
│  .md files  │────▶│  Per-file LLM schema induction       │
└─────────────┘     │  (all files run in parallel)         │
                    └──────────────┬───────────────────────┘
                                   │ N local schemas
                    ┌──────────────▼───────────────────────┐
                    │  Merge step                          │
                    │  - Cluster synonyms                  │
                    │  - Resolve conflicts                 │
                    │  - Build unified schema              │
                    └──────────────┬───────────────────────┘
                                   │ [optional review]
                    ┌──────────────▼───────────────────────┐
                    │  Per-file LLM extraction (Pass 2)    │
                    └──────────────┬───────────────────────┘
                                   │ nodes[] + edges[] per file
                    ┌──────────────▼──────────────────────────────┐
                    │  Assemble                                    │
                    │  a. Stable ID + fuzzy name matching          │
                    │  b. Type normalization (alias map from merge)│
                    │  c. Node deduplication (merge attrs, conf)   │
                    │  d. Edge dedup — hash(type+from+to)          │
                    │  e. Materialize edges.jsonl                  │
                    │  f. Export knowledge_graph.ttl               │
                    └──────────────────────────────────────────────┘
```

### Trade-offs

| Pro | Con |
|---|---|
| Pass 1 fully parallelizable | Merge logic is the hardest part of the system |
| Handles heterogeneous corpora well | Schema hard to review before merge completes |
| Local schemas capture niche concepts | Higher LLM call count (N files × 2 passes) |
| Natural synonym resolution point | Merge quality determines overall schema quality |
| Good scaling path for large corpora | More complex to implement and test |

---

## Option C — Iterative Refinement

### High-Level Algorithm

```
INPUT: directory of .md files

PASS 1 — INCREMENTAL SCHEMA GROWTH (sequential)
─────────────────────────
1. Initialize empty schema: {}

2. For each file (in order):
   a. Pre-process + chunk file
   b. LLM call with current schema in context:
      "Given the existing schema and this new document,
       propose additions or modifications:
       - New concept types not yet in the schema
       - New relationship types
       - Refinements to existing type definitions"
   c. Validate proposed changes (no contradictions)
   d. Apply approved changes → updated schema
   e. Log schema delta for audit trail

3. Schema stabilization check
   - If last N files produced no schema changes → schema is stable
   - Otherwise continue

4. [Optional human review gate]

─────────────────────────
PASS 2 — INSTANCE EXTRACTION
─────────────────────────
5. For each file (independently, parallelizable — schema is now stable):
   - Feed file content + stable schema to LLM
   - LLM returns nodes[] (concept instances) + edges[] (relationship instances)

6. Assemble property graph
   a. Node ID assignment
      - Same as Option A: hash(type + canonical_name)
      - Schema is already stable and consistent — no type aliasing needed
        (advantage over Option B)

   b. Node deduplication
      - Same as Option A: group by ID, merge attributes, aggregate confidence
      - Confidence scores are stable here — schema did not change during
        extraction, so scores are directly comparable across files
        (advantage over Option C Pass 1 where scores shift as schema evolves)

   c. Edge deduplication
      - Same as Option A: hash(type + from_id + to_id)

   d. Materialization
      - Same as Options A and B: write edge_metadata.json + emit edges.jsonl + knowledge_graph.ttl

   Note: because Pass 1 was sequential and slow, consider running Pass 2
   in parallel across files to recover some throughput at this stage.

OUTPUT: intermediate/schema_history/ (deltas), intermediate/schema.json,
        intermediate/flattened_schema.json, intermediate/raw_extractions.json,
        intermediate/edge_metadata.json, intermediate/merge_log.json,
        output/knowledge_graph.ttl, output/nodes.jsonl, output/edges.jsonl
```

### Workflow Diagram

```
┌─────────────┐
│  .md files  │
└──────┬──────┘
       │ file 1
┌──────▼──────┐     ┌──────────────┐
│  Schema: {} │────▶│  LLM: propose│──▶ Schema v1
└─────────────┘     │  additions   │
                    └──────────────┘
                          │ file 2
                    ┌─────▼────────┐
               v1 ─▶  LLM: propose│──▶ Schema v2
                    │  additions   │
                    └──────────────┘
                          │ file N
                    ┌─────▼────────┐
              vN-1 ▶  LLM: propose│──▶ Schema vN (stable)
                    │  additions   │
                    └──────────────┘
                          │ [optional review]
                    ┌─────▼────────────────────────────────────┐
                    │  Pass 2 (parallel): extract instances    │
                    │  against stable schema → nodes[]+edges[] │
                    └─────────────────┬────────────────────────┘
                                      │
                    ┌─────────────────▼────────────────────────┐
                    │  Assemble                                 │
                    │  a. Stable ID assignment                  │
                    │  b. Node deduplication (stable scores)   │
                    │  c. Edge dedup — hash(type+from+to)      │
                    │  d. Materialize edges.jsonl              │
                    │  e. Export knowledge_graph.ttl           │
                    └──────────────────────────────────────────┘
```

### Trade-offs

| Pro | Con |
|---|---|
| Schema converges naturally from evidence | Fully sequential — cannot parallelize Pass 1 |
| Full audit trail of schema evolution | Highest LLM call count → highest cost |
| Handles any corpus diversity | Slow — each file waits for previous |
| Good for exploratory/research use | Hard to predict when schema stabilizes |
| | Confidence scores shift as schema evolves |

---

## Side-by-Side Comparison

| Dimension | Option A: Global Schema | Option B: Per-File + Merge | Option C: Iterative Refinement |
|---|---|---|---|
| **Schema consistency** | High — single shared vocabulary | Medium — depends on merge quality | High — converges naturally |
| **Scalability** | Medium — batching needed for large corpora | High — fully parallelizable | Low — sequential by design |
| **Schema reviewability** | Excellent — clean artifact between passes | Poor — merge happens before you see it | Medium — visible but evolving |
| **Implementation complexity** | Low | Medium (merge logic is hard) | High |
| **LLM call count** | Low — one schema pass + one extraction pass | Medium — N local schemas + merge | High — N incremental updates |
| **API cost** | Low-Medium | Medium | High |
| **Handles diverse corpora** | Medium — needs good batching strategy | High | High |
| **Synonym/alias resolution** | Lexical only (formatting variants); semantic synonyms need thesaurus or human review | Built into merge step | Emergent during refinement |
| **Confidence scoring fit** | Natural — applies cleanly in Pass 2 | Natural | Complex — scores shift as schema evolves |
| **Best for** | Focused corpora, human-in-the-loop review | Large heterogeneous corpora | Research/experimental use |

---

## Algorithm Step-by-Step Comparison

```
STEP                    OPTION A (current)              OPTION B                        OPTION C
──────────────────────────────────────────────────────────────────────────────────────────────────────────

INGEST
  chunk files           chunk_file() all files          chunk_file() all files          chunk_file() one file at a time
  manifest              file_manifest.json              file_manifest.json              file_manifest.json

PASS 1
  scope                 all chunks across all files     all chunks of one file          all chunks of one file
  batching              _build_batches()                _build_batches()                no batching — one call per file
                        token-based, cross-file         per_file_batching=True
  parallelism           parallel batches                parallel per-file               sequential — file N waits for N-1
  prompt                "induce schema from scratch"    "induce schema from scratch"    "existing schema={} + this file
                                                                                         → propose additions only"
  LLM calls             ceil(chunks/batch_size)         N files (min)                   N files
  output per call       full proposal {concepts,        full proposal {concepts,        delta proposal {concepts,
                        properties}                     properties}                     properties} — net-new only
  after each call       —                               —                               apply delta → schema grows
                                                                                        synonym_match() against current
                                                                                        log delta → schema_history/
  stabilization         —                               —                               exit when last N files = empty delta
  merge                 merge_proposals()               merge_proposals()               apply_schema_delta() — subset
                        all proposals at once           all proposals at once           of merge_proposals(), per file

SCHEMA VALIDATE         once after merge                once after merge                once per delta + once after stable
HUMAN REVIEW GATE       optional                        optional                        optional (after stabilization)
SCHEMA FLATTEN          flatten_schema()                flatten_schema()                flatten_schema()

PASS 2
  parallelism           parallel per file               parallel per file               parallel per file
  schema                fixed — may be incomplete       fixed — may be incomplete       stable — fully converged
  schema-gap restarts   yes — surgical re-extract       yes — surgical re-extract       rarely/never — already converged
  LLM calls             total_chunks × restarts         total_chunks × restarts         total_chunks × 1

NORMALIZE               normalize_names()               normalize_names()               normalize_names()
ASSEMBLE                deduplicate nodes/edges         deduplicate nodes/edges         deduplicate nodes/edges
ORPHAN SCORE            co-occurrence heuristic         co-occurrence heuristic         co-occurrence heuristic
ORPHAN CONNECT          LLM confirmation                LLM confirmation                LLM confirmation
SCHEMA-GAP LOOP         frequent                        frequent                        rare — schema already complete
EXPORT                  JSONL + TTL + NetworkX          JSONL + TTL + NetworkX          JSONL + TTL + NetworkX

──────────────────────────────────────────────────────────────────────────────────────────────────────────
CODE CHANGES NEEDED     none (current)                  per_file_batching=True          new: sequential Pass 1 loop
                                                        (already implemented)           new: incremental prompt variant
                                                                                        new: apply_schema_delta()
                                                                                        new: stabilization counter
                                                                                        new: schema_history/ writer
──────────────────────────────────────────────────────────────────────────────────────────────────────────
LLM CALLS (4 files,     ~53 (observed)                  ~57                             ~33–40
14 chunks, 2 restarts)
```

### LLM Call Breakdown (4 files, 14 chunks)

| Call type | Option A (observed) | Option B (estimated) | Option C (estimated) |
|---|---|---|---|
| **Pass 1 initial** | 2 (batched) | 4 (one per file) | 4 (one per file, sequential) |
| **Pass 1 retries** | 3 | 4–6 | 4–6 |
| **Pass 1 schema correction** | 1 | 1 | 1 per delta (1–4) |
| **Pass 2 initial chunk calls** | 24 (2 pass2 runs × ~12) | 24 | 14 (one pass2 run × 14 chunks) |
| **Pass 2 retries** | 15 | 15 | ~8 (fewer schema mismatches) |
| **Orphan Stage 2 calls** | 2 | 2 | 1–2 |
| **Schema-gap proposals** | 4 | 4 | 0–1 (schema already converged) |
| **Schema-gap restarts (pass2 re-runs)** | 2 | 2 | 0 |
| **Normalize calls** | 2 | 2 | 1 |
| **Total (approx)** | **53** | **57** | **33–40** |

Key insight: Option A's schema-gap restarts cause Pass 2 to re-run, doubling chunk call count.
Option C eliminates restarts by converging the schema before Pass 2 runs — ~35% fewer total calls
despite more Pass 1 calls. The surgical re-extract fix (implemented) reduces Option A's restart
cost but does not eliminate it.

---

## Recommendation

**Option A** is the recommended starting point. It maps cleanly to the two-pass mental model, produces a clean reviewable schema artifact between passes, keeps LLM costs low, and confidence scoring is straightforward in Pass 2.

**Option B** is the right scaling escape hatch: if corpora grow beyond a few hundred files or span wildly diverse domains, migrate to per-file parallel induction. The merge step is the hard engineering problem — but it's a separable module that can be added later without redesigning the rest of the system.

**Option C** is best reserved for research or exploratory contexts where schema evolution itself is a deliverable.

A pragmatic path: **build Option A, design the schema induction module with the Option B merge interface in mind** so the upgrade path is clean.

---

## Ontology Layer — Concept Taxonomy + Property Graph

Beyond the three pipeline options, a key design decision is how to represent the schema itself. The goal is to combine two ideas:

- **Property graph** — nodes, edges, and properties on both (rich, flexible)
- **Concept taxonomy** — `is-a` hierarchy for inheritance and subtype queries

### Inheritance Strategy Options

Once a taxonomy exists, the question is how inherited attributes flow into the extraction prompts.

| Dimension | A: Inherit Silently | B: Flatten at Prompt Time | C: Store Canonical + Flatten for Extraction |
|---|---|---|---|
| **Schema representation** | Hierarchical only | Flat only | Hierarchical (canonical) + flat (runtime) |
| **LLM prompt complexity** | Low — LLM must infer inheritance | Low — all attributes explicit per concept | Low — flattened per concept before prompt |
| **LLM reliability** | Lower — LLM may miss inherited attributes | Higher — everything explicit | Higher — everything explicit |
| **Schema file readability** | High — compact, no repetition | Low — lots of duplication across related types | High — compact canonical form |
| **Inheritance correctness** | Depends on LLM reasoning | Lost — not represented at all | Preserved in schema, resolved at runtime |
| **Attribute override support** | Hard — implicit | Not applicable | Natural — child overrides parent before flatten |
| **Extensibility toward OWL-lite** | Medium — hierarchy exists but underspecified | Poor — hierarchy discarded | Excellent — canonical form is the upgrade path |
| **Implementation complexity** | Low | Low | Medium (need a flatten step) |
| **Runtime cost** | Lowest | Low | Low (flatten is cheap, done once per run) |
| **Consistency across documents** | Risk — LLM may behave differently per file | High — same flat spec every time | High — deterministic flatten guarantees consistency |
| **Best for** | Prototyping only | Simple corpora, no hierarchy needed | Production use with taxonomy |

### Concrete Examples per Option

**Schema used in all three examples:**
```
Person (root)  → attributes: [name, email, birth_date]
  SoftwareEngineer → attributes: [programming_languages, seniority]
```

---

#### Option A — Inherit Silently

The schema stored on disk only lists own attributes. The LLM prompt mentions the hierarchy and is expected to infer what's inherited.

Schema file:
```json
{ "type": "SoftwareEngineer", "attributes": ["programming_languages", "seniority"], "parent": "Person" }
{ "type": "Person",           "attributes": ["name", "email", "birth_date"],        "parent": null }
```

LLM extraction prompt:
```
Extract all SoftwareEngineer instances.
Attributes to extract: programming_languages, seniority
Note: SoftwareEngineer is a subtype of Person.
Inherited attributes may also apply.
```

Result — what the LLM might return:
```json
{
  "type": "SoftwareEngineer",
  "programming_languages": ["Python"],
  "seniority": "senior"
  // LLM likely missed: name, email, birth_date — never explicitly asked
}
```

**Problem:** The LLM is inconsistent. Some runs extract `name`, others don't. You can't rely on it.

---

#### Option B — Flatten at Prompt Time

The schema is stored flat — no hierarchy at all. Every concept lists all its attributes including ones that would be inherited.

Schema file:
```json
{
  "type": "SoftwareEngineer",
  "attributes": ["name", "description", "email", "birth_date", "programming_languages", "seniority"]
}
```

LLM extraction prompt:
```
Extract all SoftwareEngineer instances.
Attributes to extract: name, description, email, birth_date,
                       programming_languages, seniority
```

Result — what the LLM returns:
```json
{
  "type": "SoftwareEngineer",
  "name":                  { "value": "Alice",    "confidence": 0.99 },
  "email":                 { "value": "alice@acme.com", "confidence": 0.97 },
  "programming_languages": { "value": ["Python"], "confidence": 0.98 },
  "seniority":             { "value": "senior",   "confidence": 0.95 },
  "birth_date":            { "value": null,        "confidence": 0.0  },
  "description":           { "value": null,        "confidence": 0.0  }
}
```

**Problem:** If you later add `birth_date` to `Person`, you must manually update every subtype's flat attribute list. Hierarchy is gone — you can't query "all Person subtypes" without rebuilding it externally.

---

#### Option C — Store Canonical + Flatten for Extraction (Chosen)

Schema stored hierarchically (compact, no repetition). Pipeline flattens at runtime before building the LLM prompt.

Schema file (canonical):
```json
{ "type": "Person",           "attributes": ["name", "email", "birth_date"],      "parent": null }
{ "type": "SoftwareEngineer", "attributes": ["programming_languages","seniority"], "parent": "Person" }
```

Flatten step (pipeline, not LLM):
```
SoftwareEngineer
  own attrs:      [programming_languages, seniority]
  + Person:       [name, email, birth_date]
  ──────────────────────────────────────────────────
  flattened:      [name, email, birth_date,
                   programming_languages, seniority]
```

LLM extraction prompt (generated from flattened list):
```
Extract all SoftwareEngineer instances.
Attributes to extract: name, email, birth_date,
                       programming_languages, seniority
```

Result — same clean output as Option B, but if you later add `phone` to `Person`:
- Schema change: one line in `Person`
- Flatten step: automatically picks it up for `SoftwareEngineer`, `Researcher`, every other subtype
- No manual updates anywhere

**Why it wins:** The LLM gets the same simple explicit prompt as Option B, but the schema stays DRY and the hierarchy is preserved for taxonomy queries downstream.

---

**Decision: Option C — Store Canonical + Flatten for Extraction.** The schema stays clean and hierarchical, the LLM gets simple flat instructions, and the canonical form is the natural upgrade path toward OWL-lite property constraints.

---

## Ontology Schema Format

The schema produced by Pass 1 has two top-level arrays:

```json
{
  "concepts": [
    { "type": "Person",           "attributes": ["name", "email", "birth_date"],               "parent": null },
    { "type": "SoftwareEngineer", "attributes": ["programming_languages", "seniority"],        "parent": "Person" },
    { "type": "Organization",     "attributes": ["name", "industry", "founded_date"],          "parent": null },
    { "type": "Software",         "attributes": ["name", "version"],                           "parent": null }
  ],
  "properties": [
    { "name": "works_at",          "domain": "Person",   "range": "Organization",
      "attributes": ["role", "start_date", "end_date"] },
    { "name": "collaborates_with", "domain": "Person",   "range": "Person",
      "attributes": ["project"] },
    { "name": "depends_on",        "domain": "Software", "range": "Software",
      "attributes": ["version", "constraint"] }
  ]
}
```

- **`concepts[]`** — RDFS classes with `is-a` hierarchy. Own attributes only (compact, DRY). Root classes have `"parent": null`. No abstract `Relationship` class.
- **`properties[]`** — RDFS object properties. `domain`/`range` map to class names in `concepts[]`. `attributes` lists the edge-level metadata fields captured per relationship instance — stored in `intermediate/edge_metadata.json`, not in the Turtle file.

### Concept Taxonomy

```
Person (root)
└── SoftwareEngineer

Organization (root)

Software (root)
```

### Flatten Step (done once before Pass 2)

The pipeline walks up the inheritance chain and merges attribute lists before building extraction prompts:

```
SoftwareEngineer
  own:      [programming_languages, seniority]
  + Person: [name, email, birth_date]
  ─────────────────────────────────────────────
  flat:     [name, email, birth_date, programming_languages, seniority]
```

The LLM never sees the word "inheritance" — it receives a clean flat list per concept type.

---

## End-to-End Extraction Example

### Source Markdown

```markdown
## Team

Alice is a senior engineer at Acme Corp. She specializes in Python
and Rust and can be reached at alice@acme.com.
```

### Pass 2 LLM Output — nodes[] + edges[]

The LLM returns concept instances in `nodes[]` and relationship instances in `edges[]`. Edges are direct — they have `from`, `to`, `type` (the property name from the schema), and `attributes` (edge-level metadata).

```json
{
  "nodes": [
    {
      "id": "person-alice",
      "type": "SoftwareEngineer",
      "attributes": {
        "name":                  { "value": "Alice",            "confidence": 0.99 },
        "email":                 { "value": "alice@acme.com",   "confidence": 0.97 },
        "seniority":             { "value": "senior",           "confidence": 0.95 },
        "programming_languages": { "value": ["Python", "Rust"], "confidence": 0.98 },
        "birth_date":            { "value": null,               "confidence": 0.0  },
        "description":           { "value": null,               "confidence": 0.0  }
      }
    },
    {
      "id": "org-acme-corp",
      "type": "Organization",
      "attributes": {
        "name":         { "value": "Acme Corp", "confidence": 0.99 },
        "industry":     { "value": null,         "confidence": 0.0  },
        "founded_date": { "value": null,          "confidence": 0.0  },
        "description":  { "value": null,          "confidence": 0.0  }
      }
    }
  ],
  "edges": [
    {
      "id": "edge-001",
      "type": "works_at",
      "from": "person-alice",
      "to":   "org-acme-corp",
      "confidence": 0.96,
      "attributes": {
        "role":       { "value": "engineer", "confidence": 0.91 },
        "start_date": { "value": null,        "confidence": 0.0  },
        "end_date":   { "value": null,        "confidence": 0.0  }
      }
    }
  ]
}
```

### Assembler Output — edge_metadata.json (sidecar)

After deduplication, all edges are written to the sidecar keyed by edge ID:

```json
{
  "edge-001": {
    "type": "works_at", "from": "person-alice", "to": "org-acme-corp",
    "confidence": 0.96,
    "attributes": { "role": {"value": "engineer", "confidence": 0.91},
                    "start_date": {"value": null, "confidence": 0.0},
                    "end_date": {"value": null, "confidence": 0.0} },
    "source_files": ["team.md"]
  }
}
```

### Assembler Output — edges.jsonl (flat, from sidecar)

```jsonl
{"id":"edge-001","type":"works_at","from":"person-alice","to":"org-acme-corp","confidence":0.96,"source_files":["team.md"],"attributes":{"role":{"value":"engineer","confidence":0.91},"start_date":{"value":null,"confidence":0.0},"end_date":{"value":null,"confidence":0.0}}}
```

### Key Design Points

- Inherited attributes (`name`, `email` from `Person`) are extracted cleanly — the LLM never sees the word "inheritance"
- Missing attributes get `null` + `confidence: 0.0` — never silently dropped
- Relationships are direct edges in `edges[]` — no intermediate Employment node
- Edge metadata (role, start_date, confidence) lives in `edge_metadata.json` — not in the Turtle file
- `edges.jsonl` is produced by the assembler from the sidecar — always a derived artifact

### What the Taxonomy Enables Downstream

| Query | How the graph answers it |
|---|---|
| "Who works at Acme Corp?" | Traverse all `works_at` edges pointing to `org-acme-corp` |
| "List all People at Acme" | Match nodes where `type` is `Person` or any subtype — catches `SoftwareEngineer` via taxonomy |
| "What did we confidently extract?" | Filter all nodes/edges/attributes where `confidence >= 0.85` |
| "What do we know about Alice?" | Fetch `person-alice` node + all edges where `from` or `to` = `person-alice` |
| "Who are the senior engineers?" | Match `type=SoftwareEngineer` AND `seniority.value="senior"` |

---

## RDF/OWL Compatibility

### The Core Problem

Standard RDF/OWL treats relationships as binary predicates: `(subject, predicate, object)`. Edges have no identity and cannot hold properties. This means confidence scores, role, start_date, and other edge-level metadata cannot live directly in RDF triples.

### Chosen Solution — Standard RDFS Properties + Edge Metadata Sidecar

Relationship types become `rdf:Property` predicates in the schema (`works_at`, `depends_on`). `knowledge_graph.ttl` emits clean binary triples. Edge metadata lives separately in `intermediate/edge_metadata.json`.

```
# Direct binary triple in knowledge_graph.ttl:
data:Alice  ex:works_at  data:AcmeCorp .

# Edge metadata in edge_metadata.json:
{ "edge-001": { "type": "works_at", "confidence": 0.96, "attributes": { "role": "engineer" } } }
```

This replaces the earlier "intermediate node pattern" (which modeled `Employment` as an OWL class). Standard RDFS tooling works without any workarounds.

### knowledge_graph.ttl — Standard RDFS Format

Two clearly separated sections following the canonical RDFS pattern:

```turtle
# Namespace URIs and prefix labels are configurable via pipeline_config.yaml → pipeline.export.*
@prefix rdf:  <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix ex:   <http://mykg.local/schema/> .   # pipeline.export.schema_prefix_label / schema_namespace
@prefix data: <http://mykg.local/data/> .     # pipeline.export.data_prefix_label / data_namespace

# ==========================================
# 1. THE RDFS SCHEMA (The Blueprint)
# ==========================================

# Define Classes
ex:Person           rdf:type rdfs:Class .
ex:SoftwareEngineer rdf:type rdfs:Class .
ex:Organization     rdf:type rdfs:Class .

# Create Class Hierarchy
ex:SoftwareEngineer rdfs:subClassOf ex:Person .

# Define Properties and Constraints
ex:name rdf:type rdf:Property ;
    rdfs:domain ex:Person ;        # Persons have a name
    rdfs:range rdfs:Literal .      # The value is a literal (string)

ex:email rdf:type rdf:Property ;
    rdfs:domain ex:Person ;        # Only persons have email
    rdfs:range rdfs:Literal .      # The value is a literal (string)

ex:works_at rdf:type rdf:Property ;
    rdfs:domain ex:Person ;        # Subject must be a Person (or subtype)
    rdfs:range ex:Organization .   # Object must be an Organization

# ==========================================
# 2. THE RDF INSTANCE DATA (The Facts)
# ==========================================

# Define Entities
data:Alice    rdf:type ex:SoftwareEngineer .
data:AcmeCorp rdf:type ex:Organization .

# Use Properties to Link Entities
data:Alice    ex:name    "Alice" .
data:Alice    ex:email   "alice@acme.com" .
data:AcmeCorp ex:name    "Acme Corp" .
data:Alice    ex:works_at data:AcmeCorp .
```

No metadata in the Turtle file. No blank nodes, no reification, no RDF-star. Pure RDFS.

### What This Unlocks

| Capability | Available |
|---|---|
| Standard RDF toolchain compatible | Yes — any SPARQL endpoint, Protégé, reasoner |
| SPARQL queries (simple) | Yes — `?person ex:works_at ?org` |
| Concept taxonomy (is-a hierarchy) | Yes — `rdfs:subClassOf` chain |
| Edge metadata (confidence, role) | Yes — in `edge_metadata.json` sidecar |
| Neo4j / NetworkX property graph | Yes — `edges.jsonl` assembled from sidecar |
| OWL property chain reasoning | Yes — `ex:works_at` exists as a direct property |

---

## Output Files & Materialized Views

The pipeline produces two categories of files: **intermediate JSON files** saved between passes for debugging and resumability, and **final output files** in two formats — a single combined Turtle file for RDF/OWL consumers, and JSONL files for property graph consumers (Neo4j, NetworkX).

### Intermediate Files (JSON)

Saved in `intermediate/` — all JSON, all inspectable or editable between runs.

| File | When written | Contents |
|---|---|---|
| `intermediate/base_schema_parsed.json` | Step 1 (only if `--base-schema` given) | Locked classes + properties parsed from user-supplied TTL |
| `intermediate/thesaurus_parsed.json` | Step 1 (only if `--thesaurus` given) | SKOS thesaurus metadata — source, term count, relations used |
| `intermediate/schema.json` | After Pass 1 | Induced RDFS schema: `concepts[]` + `properties[]` — pipeline source of truth |
| `intermediate/schema.ttl` | After Pass 1 | TBox-only RDFS — validated by Step 3b; load in Protégé for review |
| `intermediate/schema_validation_errors.json` | After Step 3b (failure only) | rdflib syntax + semantic validation errors; absent if schema is valid |
| `intermediate/flattened_schema.json` | Before Pass 2 | Per-concept flattened attribute lists used in extraction prompts |
| `intermediate/raw_extractions.json` | After Pass 2, before assembly | Raw `nodes[]` + `edges[]` per source file, undeduped |
| `intermediate/edge_metadata.json` | After assembly | Deduplicated edge records with full attributes + confidence, keyed by edge ID |
| `intermediate/merge_log.json` | After assembly | Record of deduplication decisions — which nodes/edges merged and why |

### Final Output Files

Saved in `output/`.

| File | Format | Contents | Source of truth |
|---|---|---|---|
| `output/knowledge_graph.ttl` | Turtle (RDFS) | RDFS schema (TBox) + concept instances + direct object property triples | Yes (RDF consumers) |
| `output/knowledge_graph_validation.json` | JSON | TBox + ABox validation results from Step 12b — always written | Advisory |
| `output/nodes.jsonl` | JSONL | Concept instances with full attributes + confidence (no relationship nodes) | Yes (graph DB consumers) |
| `output/edges.jsonl` | JSONL | Flat edge records assembled from `edge_metadata.json` sidecar | Derived from sidecar |
| `output/networkx_output/knowledge_graph.graphml` | GraphML | Full node/edge attributes — yEd, Gephi, Cytoscape | Derived (Step 12c) |
| `output/networkx_output/knowledge_graph.gexf` | GEXF | Gephi native; richest metadata support | Derived (Step 12c) |
| `output/networkx_output/knowledge_graph.json` | JSON node-link | D3.js, Sigma.js, web visualizers | Derived (Step 12c) |
| `output/networkx_output/knowledge_graph.gml` | GML | Human-readable; most graph tools | Derived (Step 12c) |
| `output/networkx_output/knowledge_graph.net` | Pajek | String attributes only (numeric confidence dropped) | Derived (Step 12c) |
| `output/networkx_output/edges_nx.txt` | Edge list | Plain text; attributes as key=value pairs | Derived (Step 12c) |
| `output/networkx_output/adjacency.txt` | Adjacency list | Topology only | Derived (Step 12c) |

NetworkX outputs are enabled by default. Toggle via `pipeline_config.yaml → pipeline.export.networkx_enabled`. Node/edge attributes are flattened to GML-safe scalars (`attr_<name>_value` / `attr_<name>_confidence`); `source_files` lists are pipe-joined.

---

### knowledge_graph.ttl — Pure RDFS File

A single self-contained file with two sections. No metadata in the Turtle file — confidence scores and edge attributes live in `edge_metadata.json` only.

See the full example in the **RDF/OWL Compatibility** section above.

---

### nodes.jsonl — Concept Instances

Contains all concept instances (Person, Organization, SoftwareEngineer, etc.) with full attributes and confidence scores. No relationship nodes. See the full concrete example below.

---

### edges.jsonl — Flat Edge Records for Graph DBs

Assembled from `intermediate/edge_metadata.json`. Each record is a flat, joinable edge for Neo4j importers and visualizers. See the full concrete example below.

---

### Concrete Example — Alice/Acme Corp Scenario

**`output/nodes.jsonl`** — one JSON object per line, all concept instances:

```jsonl
{"id":"person-alice-smith","type":"SoftwareEngineer","aliases":["Alice","A. Smith"],"attributes":{"name":{"value":"Alice Smith","confidence":0.99},"email":{"value":"alice@acme.com","confidence":0.97},"seniority":{"value":"senior","confidence":0.95},"programming_languages":{"value":["Python","Rust"],"confidence":0.98},"birth_date":{"value":null,"confidence":0.0},"description":{"value":null,"confidence":0.0}},"source_files":["team.md"],"confidence":0.97}
{"id":"org-acme-corp","type":"Organization","attributes":{"name":{"value":"Acme Corp","confidence":0.99},"industry":{"value":null,"confidence":0.0},"founded_date":{"value":null,"confidence":0.0},"description":{"value":null,"confidence":0.0}},"source_files":["team.md"],"confidence":0.99}
```

Notes:
- `aliases` is a flat list of original surface-form strings resolved to this canonical node by the name normalization step (D29). The field is absent when normalization is disabled.
- In `knowledge_graph.ttl`, aliases appear as `skos:altLabel` triples: `data:person-alice-smith skos:altLabel "Alice" .`

**`output/edges.jsonl`** — one JSON object per line, flat edge records joined from triples + sidecar:

```jsonl
{"id":"edge-001","type":"works_at","from":"person-alice","to":"org-acme-corp","confidence":0.96,"source_files":["team.md"],"attributes":{"role":{"value":"engineer","confidence":0.91},"start_date":{"value":null,"confidence":0.0},"end_date":{"value":null,"confidence":0.0}}}
```

Notes:
- `nodes.jsonl` has no relationship nodes — every line is a concept instance.
- `edges.jsonl` keeps `attributes` as a nested object (preserving per-attribute confidence). If a Neo4j import needs flat top-level fields, the assembler can optionally emit a flat version as a flag — easy to add without changing the canonical format.
- Both files carry `source_files[]` for provenance — which Markdown files contributed to this node/edge after deduplication.
- `confidence` at the top level is the overall node/edge confidence (mean or max across all contributing extractions, configurable).

---

### The One Rule

`edges.jsonl` and the object property triples in `knowledge_graph.ttl` are always **regenerated** from `intermediate/edge_metadata.json` — never edited directly.

---

### Session-Based Run Isolation

Every `mykg extract-graph` invocation creates (or resumes) an isolated session folder:

```
sessions/
  2026-05-17T21-33-19/      ← UTC timestamp
    input/                  ← archived copy of all input .md files (authoritative on resume)
    intermediate/           ← all pipeline state (schema, extractions, sidecar, …)
    output/                 ← final artifacts (nodes.jsonl, edges.jsonl, knowledge_graph.ttl, …)
    run.log                 ← session log (rotated, never silently lost)
```

```bash
# New run — auto-creates sessions/<timestamp>/
uv run mykg extract-graph input_files/ --log-file run.log --verbose

# Resume an existing session (intermediate/ preserved, input/ refreshed)
uv run mykg extract-graph input_files/ --session 2026-05-17T21-33-19 --log-file run.log --verbose

# Legacy explicit dirs — bypasses session management entirely
uv run mykg extract-graph input_files/ --output-dir output --intermediate-dir intermediate
```

**Key contract:** `--session <name>` sets `intermediate/` and `output/` to the named session's subdirectories. The `input/` archive inside the session root is the authoritative input source on resume — if the original directory is gone, the pipeline still works. `--output-dir`/`--intermediate-dir` bypass all of this.

---

### Pass 2 File-Granularity Resumability

Pass 2 processes up to hundreds of files via a `ThreadPoolExecutor`. Each file's extraction result is written into `raw_extractions.json` and `chunk_node_index.json` **immediately when it completes** — not batched at the end. A `raw_extractions.done` sentinel is written only when all files finish.

On any restart (quota expiry, crash, manual kill):

1. The pipeline loads the existing partial `raw_extractions.json`.
2. Files already present in it are **skipped** — no re-extraction, no LLM cost.
3. Only the remaining files are submitted to the worker pool.
4. The log shows: `Step 6 — N file(s) already done, M remaining`.

This means a 288-file corpus interrupted at file 200 resumes at file 201 — not file 1.

**Schema restart safety:** when a `SchemaUpdatedError` fires (automated Re-entry A), both `raw_extractions.json` and `chunk_node_index.json` are deleted before the restart so stale extractions from the old schema cannot accumulate.

---

### Log File Management

Each session writes to `<session_root>/run.log`. Rules:

- If `--log-file` is omitted: log goes to `<session_root>/run.log` automatically.
- If `--log-file run.log` (relative): redirected to `<session_root>/run.log`.
- If `--log-file /absolute/path/run.log`: used as-is, not redirected.
- Rotation: `RotatingFileHandler` governed by `pipeline_config.yaml → pipeline.logging.max_bytes` (default 10 MB) and `backup_count` (default 3). Old logs roll to `run.log.1` … `run.log.N` — never silently discarded.

---

### Tool Compatibility Summary

| Tool | Role | Input file |
|---|---|---|
| **Neo4j / Kuzu / Memgraph** | Graph database | `nodes.jsonl` + `edges.jsonl` |
| **NetworkX** (Python) | In-memory graph processing | `networkx_output/knowledge_graph.graphml` or `nodes.jsonl` + `edges.jsonl` |
| **Gephi** | Graph visualization + layout | `networkx_output/knowledge_graph.gexf` (native) or `.graphml` |
| **yEd / Cytoscape** | Graph visualization | `networkx_output/knowledge_graph.graphml` |
| **D3.js / Sigma.js** | Web graph visualization | `networkx_output/knowledge_graph.json` |
| **Pajek** | Network analysis | `networkx_output/knowledge_graph.net` |
| **Protégé** | Schema authoring + taxonomy visualization | `knowledge_graph.ttl` |
| **SPARQL endpoint** (Fuseki, GraphDB, Stardog) | RDF query layer | `knowledge_graph.ttl` |
| **LLM context builder** | RAG / reasoning over graph | `nodes.jsonl` + `edges.jsonl` |

---

### Query Examples

**Cypher (Neo4j) — find high-confidence employment relationships:**
```cypher
MATCH (p:Person)-[r:works_at]->(o:Organization)
WHERE r.confidence > 0.8
RETURN p.name, r.role, o.name
```

**SPARQL — one-hop traversal (knowledge_graph.ttl):**
```sparql
SELECT ?person ?org WHERE {
  ?person  ex:works_at  ?org .
}
```

**SPARQL — subclass query (finds SoftwareEngineer via rdfs:subClassOf chain):**
```sparql
SELECT ?person WHERE {
  ?person rdf:type/rdfs:subClassOf* ex:Person .
}
```

---

## Prompt Engineering

The main risks in Pass 1 are: mixing object properties into `concepts[]` or adding a `Relationship` class. The main risks in Pass 2 are: using display names instead of node IDs in `from`/`to`, omitting required attributes, inventing edge types not in the schema.

---

### Pass 1 Prompt — Schema Induction

The Pass 1 prompt must teach the LLM to output `concepts[]` (RDFS classes with datatype attributes) and `properties[]` (RDFS object properties linking classes), not a flat list or a `relations` array.

**Pass 1 system prompt fragment:**

```
OUTPUT FORMAT
=============
Return a single JSON object with exactly two keys: "concepts" and "properties".
Do NOT return any other keys (no "relations", no "edges", no "graph").

"concepts" — RDFS classes. Each entry has:
  - "type": PascalCase class name (e.g. "Person", "Organization")
  - "parent": name of the parent class, or null for root classes
  - "attributes": list of snake_case datatype attribute names OWN to this class
    (do NOT repeat attributes from parent classes here)

"properties" — RDFS object properties that LINK two classes. Each entry has:
  - "name": snake_case predicate (e.g. "works_at", "depends_on")
  - "domain": the subject class name (must appear in concepts[])
  - "range": the object class name (must appear in concepts[])
  - "attributes": edge-level metadata fields to capture per relationship instance
    (e.g. ["role", "start_date", "end_date"])

RULES
=====
- Do NOT add a "Relationship" class. Relationships are entries in properties[], not classes.
- "domain" and "range" must be class names that appear in concepts[].
- Root classes have "parent": null. Every non-root class must name a parent that exists in concepts[].
- Datatype attributes (strings, numbers, dates) belong in concepts[].attributes.
- Object links between entities (who works where, what depends on what) belong in properties[].

EXAMPLE OUTPUT
==============
{
  "concepts": [
    {"type": "Person",           "parent": null,     "attributes": ["name", "email", "birth_date"]},
    {"type": "SoftwareEngineer", "parent": "Person", "attributes": ["programming_languages", "seniority"]},
    {"type": "Organization",     "parent": null,     "attributes": ["name", "industry"]}
  ],
  "properties": [
    {
      "name": "works_at",
      "domain": "Person",
      "range": "Organization",
      "attributes": ["role", "start_date", "end_date"]
    }
  ]
}
```

---

### Pass 2 Prompt — Instance Extraction

**Pass 2 system prompt fragment:**

```
OUTPUT FORMAT
=============
Return a single JSON object with exactly two keys: "nodes" and "edges".

"nodes" — one entry per entity instance. Each entry has:
  - "id": kebab-case slug derived from type and name, e.g. "person-alice", "org-acme-corp"
    Format: <type-prefix>-<name-slug> where type-prefix is the lowercased class name
  - "type": exact class name from the schema (e.g. "SoftwareEngineer", "Organization")
  - "confidence": float 0.0–1.0 representing overall extraction confidence for this node
  - "attributes": object with one key per schema attribute for this class (including
    inherited attributes). Each value is {"value": <extracted or null>, "confidence": <float>}.
    Never omit an attribute — use {"value": null, "confidence": 0.0} if not found.

"edges" — one entry per relationship instance. Each entry has:
  - "id": sequential identifier, e.g. "edge-001", "edge-002"
  - "type": exact property name from the schema's properties[] (e.g. "works_at")
  - "from": node ID of the subject — must be an "id" value from nodes[] above
  - "to": node ID of the object — must be an "id" value from nodes[] above
  - "confidence": float 0.0–1.0 for this relationship instance
  - "attributes": object with one key per edge attribute defined in the schema for
    this property. Each value is {"value": <extracted or null>, "confidence": <float>}.
    Never omit an attribute — use {"value": null, "confidence": 0.0} if not found.

RULES
=====
- "from" and "to" must be node IDs from nodes[] in this response — not display names.
- "type" in edges must exactly match a property name from properties[]. Do not invent types.
- Every attribute defined in the schema for a class or property must appear in the output.
- All confidence values are floats between 0.0 and 1.0.
- Include ALL entities and relationships mentioned in the document, even if confidence is low.

EXAMPLE OUTPUT
==============
{
  "nodes": [
    {
      "id": "person-alice",
      "type": "SoftwareEngineer",
      "confidence": 0.97,
      "attributes": {
        "name":                  {"value": "Alice",            "confidence": 0.99},
        "description":           {"value": null,               "confidence": 0.0},
        "email":                 {"value": "alice@acme.com",   "confidence": 0.97},
        "birth_date":            {"value": null,               "confidence": 0.0},
        "programming_languages": {"value": ["Python", "Rust"], "confidence": 0.98},
        "seniority":             {"value": "senior",           "confidence": 0.95}
      }
    },
    {
      "id": "org-acme-corp",
      "type": "Organization",
      "confidence": 0.99,
      "attributes": {
        "name":         {"value": "Acme Corp", "confidence": 0.99},
        "description":  {"value": null,         "confidence": 0.0},
        "industry":     {"value": null,         "confidence": 0.0}
      }
    }
  ],
  "edges": [
    {
      "id": "edge-001",
      "type": "works_at",
      "from": "person-alice",
      "to": "org-acme-corp",
      "confidence": 0.96,
      "attributes": {
        "role":       {"value": "engineer", "confidence": 0.91},
        "start_date": {"value": null,       "confidence": 0.0},
        "end_date":   {"value": null,       "confidence": 0.0}
      }
    }
  ]
}
```

---

### Validation — Rejecting Malformed LLM Output

After each Pass 2 LLM call, the assembler validates before accepting the output:

| Check | Expected | Reject if |
|---|---|---|
| Top-level keys | `{ "nodes": [...], "edges": [...] }` | Unknown top-level keys present |
| `type` of each node | Matches a concept name in schema | Unknown type |
| `type` of each edge | Matches a property name in schema | Unknown property name |
| `from`/`to` values | Node IDs present in `nodes[]` | Free-text names or unknown IDs |
| Missing attributes | Present as `{ "value": null, "confidence": 0.0 }` | Attribute omitted entirely |

On validation failure: log the raw output to `intermediate/raw_extractions.json`, emit a warning, and optionally retry with an error-correction prompt.

**Error-correction prompt fragment (retry):**

```
Your previous response contained an error:
  {error_description}

Common mistakes:
- Using a display name in "from"/"to" instead of a node ID —
  use "person-alice" not "Alice"
- Using an edge "type" not in the schema — only use property names from properties[]
- Omitting required attributes — include all schema attributes, use null if unknown

Please re-extract the document with these corrections.
```

---

## Entity Name Normalization — Handling Surface Form Variation

### The Problem

The current deduplication key for nodes is `stable_id = <type>-<name-slug>`, where the name slug is derived from the lowercased, whitespace-normalized `name` attribute. This means `"Alice Smith"` and `"Alice"` produce different IDs (`person-alice-smith` vs `person-alice`) and are never merged, even when they refer to the same entity. Variation arises both within a single file (same person mentioned by first name vs full name) and across files (different documents using different surface forms).

### Four Options

---

#### Option A — Alias Field on Nodes (per-node, LLM-provided)

The Pass 2 prompt is extended to ask the LLM to emit an optional `aliases` list on each node containing all surface forms seen for that entity within the document.

```json
{
  "id": "person-alice-smith",
  "type": "Person",
  "attributes": { "name": {"value": "Alice Smith", "confidence": 0.99}, ... },
  "aliases": ["Alice", "A. Smith"]
}
```

After `assign_stable_ids`, the assembler builds a global alias index: `alias_slug → canonical_stable_id`. Any node whose computed stable ID matches an alias slug is redirected to the canonical ID before deduplication runs. All redirections are logged to `merge_log.json`.

**Handles:** within-file variation reliably (LLM sees both forms in context). Cross-file variation only if the same file happens to mention both forms.

**Trade-offs:**

| Pro | Con |
|---|---|
| No extra LLM calls | Only catches variation the LLM can see within a single file |
| Fully auditable — every alias resolution logged | Prompt change needed; LLM may omit aliases inconsistently |
| No new dependencies | Does not handle cross-file divergence |
| Aliases survive re-entry at Step 7 | |

---

#### Option B — LLM Normalization Pass (post-Pass-2, pre-assembly) — Recommended

After Pass 2 completes and all raw extractions are written to `intermediate/raw_extractions.json`, a new Step 6b runs a single additional LLM call. It receives all distinct node names grouped by type (not the full document text) and returns a canonical name mapping.

```
INPUT to LLM (Step 6b):
{
  "Person": ["Alice Smith", "Alice", "A. Smith", "Bob Johnson", "Bob"]
}

LLM OUTPUT:
{
  "Alice": "Alice Smith",
  "A. Smith": "Alice Smith",
  "Bob": "Bob Johnson"
}
```

The assembler applies this map before computing stable IDs: any name that appears as a key is replaced by its canonical value before slugging. The map is written to `intermediate/name_normalization.json` for audit.

**Handles:** both within-file and cross-file variation because the LLM sees all distinct names across all files at once, grouped by type.

**Trade-offs:**

| Pro | Con |
|---|---|
| Handles cross-file variation reliably | One extra LLM call (fast — names only, no full text) |
| Does not change Pass 2 prompt or output format | New pipeline step between Pass 2 and assembly |
| LLM sees full name inventory per type — best context for disambiguation | LLM may still merge incorrectly (e.g. two different people named "Alice") |
| Fully auditable — map written to `intermediate/name_normalization.json` | |
| Composes cleanly with Option A (alias hints can be passed as context) | |

**New intermediate file:**

```json
// intermediate/name_normalization.json
{
  "Person": {
    "Alice": "Alice Smith",
    "A. Smith": "Alice Smith",
    "Bob": "Bob Johnson"
  },
  "Organization": {
    "Acme": "Acme Corp"
  }
}
```

**Re-run guide addition:** Re-entry C (assembly errors) can now also re-enter at Step 6b — edit `name_normalization.json` and re-run from Step 7.

---

#### Option C — Embedding Similarity Clustering

After stable ID assignment, nodes of the same type are clustered by cosine similarity of their name embeddings above a configurable threshold. Nodes in the same cluster are merged under the highest-confidence name.

**Handles:** variation at any granularity, including typos and abbreviations.

**Trade-offs:**

| Pro | Con |
|---|---|
| Most robust — catches any surface-form variation | Adds embedding model dependency (new external call or local model) |
| No prompt changes | Adds latency |
| | Threshold is a tunable that can cause false merges (two different people with similar names) |
| | Harder to audit — similarity score is less interpretable than a name map |

---

#### Option D — Combine A + B

Pass 2 emits aliases (Option A) for within-file variation. Step 6b (Option B) uses those aliases as additional context hints when building the normalization map for cross-file variation.

**Handles:** all variation. Alias hints in the normalization prompt reduce ambiguity (e.g. "Alice Smith" document already says aliases: ["Alice"] → normalization pass has stronger signal).

**Trade-offs:** most robust but most moving parts. Suitable upgrade path after Option B is working.

---

### Side-by-Side Comparison

| Dimension | A: Aliases | B: Normalization Pass | C: Embeddings | D: A + B |
|---|---|---|---|---|
| **Within-file variation** | Yes | Yes | Yes | Yes |
| **Cross-file variation** | Partial | Yes | Yes | Yes |
| **Extra LLM calls** | None | One (fast) | None | One (fast) |
| **New dependency** | None | None | Embedding model | None |
| **Auditability** | merge_log.json | name_normalization.json | similarity scores | Both |
| **Prompt changes** | Yes (Pass 2) | No | No | Yes (Pass 2) |
| **False merge risk** | Low | Medium (LLM may conflate) | Medium (threshold sensitivity) | Low |
| **Implementation complexity** | Low | Low | Medium | Medium |

### Decision

**Option B — LLM Normalization Pass** is the recommended starting point. It handles both within-file and cross-file variation without changing the established Pass 2 prompt format, produces a clean auditable artifact, and adds only one fast LLM call (names only, no full document text). Option D is the natural upgrade path once Option B is in place.

---

## Aliases on Output Nodes vs Edges

### Decision: aliases on nodes only — not on edges

Aliases are carried through to the final output on **nodes only**. Edges do not get an `aliases` field.

**Why nodes have aliases:** A node represents a real-world named entity (`Person`, `Organization`, etc.) that can be referred to by different surface forms across documents — "Alice", "Alice Smith", "A. Smith" all name the same person. Aliases record these variant forms so downstream consumers (search, RAG, round-trip extraction) can find the canonical node even when querying by a non-canonical name.

**Why edges do not have aliases:** An edge is identified by a structural triple `(type, from_id, to_id)` — it is not a named thing with alternative names. The relationship "Alice works at Acme Corp" has no meaningful alternative label. The only scenario that resembles edge aliasing — when two files use different relationship type names (e.g. `works_at` vs `employed_by`) for the same pair of nodes — is a schema-level synonym problem, already handled by the Pass 1 `synonym_match` mechanism in `schema_merge.py`. That collapses duplicate relationship types at schema induction time before any instance extraction runs. Carrying aliases on individual edge instances would add schema complexity and output surface area with no use case.

**`aliases` field specification on nodes:**
- Top-level field on the node dict, sibling to `attributes` — never inside `attributes`
- Flat `list[str]` of original surface-form strings as they appeared in source documents
- Canonical name excluded from its own aliases list
- Deduplicated across source files; lexicographically sorted for deterministic output
- Field absent (not `[]`) when the `normalize_names` step is disabled (`NORMALIZE_NAMES_ENABLED=false`)
- Source: derived from `name_normalization.json["mappings"]` at assembly time (inverted from `{alias→canonical}` to `{canonical→[aliases]}`)
- Present in both `intermediate/nodes.json` (for re-entry) and `output/nodes.jsonl` (final output)

**In `knowledge_graph.ttl`:** aliases are emitted as `skos:altLabel` triples in the ABox, one per alias per node. The `@prefix skos:` declaration is emitted conditionally (only when any node has non-empty aliases). `skos:altLabel` is not declared in the TBox — it is exempted from the ABox validator's `undeclared_predicate` check via a configurable external-namespace whitelist (`TTL_NAMESPACE_SKOS` in `pipeline_config.yaml → pipeline.export`).

---

## Orphan-Connection Pass — Design History

> **Note:** For the authoritative current implementation, see CLAUDE.md sections D30, D33, D34. The v1 section below is preserved for historical reference; the full v2 specification follows it.

### Orphan Pass Algorithm Versions

> ⚠️ **The following section describes the v1 implementation (per-pair confirmation), superseded in 2026-05. See the [Orphan-Connection Pass v2 (Current)](#orphan-connection-pass-v2-current--chunk-level-batch-confirmation) section below for the current implementation.**

#### Historical: Per-Pair Candidate Confirmation (v1, superseded 2026-05-19)

Stage 1 (`orphan_score`) scored co-occurring node pairs by normalized co-occurrence count, filtered by schema type-pair compatibility (only domain/range-matching pairs kept), and kept top-k per orphan via `ORPHAN_TOP_K_PER_ORPHAN`. Stage 2 (`orphan_connect`) made one LLM call per `(orphan, candidate)` pair with a 400–1600 char excerpt from the shared chunk.

**Why it was replaced:**
- The schema type-pair filter caused false schema-gap orphans when an orphan's type had no compatible schema property for any co-occurring peer type — even when the LLM could have found a connection from the raw text. This triggered unnecessary schema-gap restarts (Re-entry A).
- Per-pair LLM calls were expensive: a single run produced 91 LLM calls for the orphan pass alone.
- Blank-response chunks (where `_extract_chunk` returned `None`) left orphan nodes permanently invisible because no `chunk_node_index` entry was written. These were indistinguishable from genuine singletons.

#### Adopted: Chunk-Level Batch Confirmation (v2, 2026-05-19)

Stage 1 groups orphans by source chunk (no type-pair filter). Blank-response orphans are identified via `failed_chunks.json` + string search and routed through the same mechanism. Stage 2 makes one LLM call per `OrphanChunkGroup` with the full chunk text. See D33 and D34 in CLAUDE.md for full specification.

**Trade-off:** Larger prompt per call (~1000 tokens vs ~400-char excerpt), but total call count drops significantly. The LLM has better evidence and the type-pair filter bug is eliminated. Old `score_orphan_candidates` and `confirm_orphan_edges` functions are preserved in `orphan_connector.py` for backwards compatibility.

---

### Orphan-Connection Pass v2 (Current) — Chunk-Level Batch Confirmation

An **orphan node** is a node in `intermediate/nodes.json` whose stable ID appears as neither `from` nor `to` in any entry in `intermediate/edge_metadata.json` after `step_assemble` completes. Orphans are legitimate (singleton entities are real) but degrade traversal, visualization, and reasoning quality.

**Efficiency gain:** v1 produced ~91 LLM calls per run (one per `(orphan, candidate)` pair); v2 produces roughly one call per source chunk — ~10 in smaller test runs, ~34 in a 288-file run (vs ~90 pair-based). Prompt size per call increases from ~400 chars to ~1000 tokens, but total call count drops significantly.

#### Stage 1 — `orphan_score` (`is_llm_step=False`)

`score_orphan_candidates_v2()` in `src/mykg/orphan_connector.py`:

1. Identifies all orphan nodes (nodes with no edge endpoints in `edge_metadata.json`)
2. Builds an inverted index from `chunk_node_index.json`: `{node_id → [chunk_keys]}`
3. For each orphan, finds the chunk(s) it appeared in
4. Groups all orphans by chunk key → one `OrphanChunkGroup` per `(filename, chunk_idx)`
5. Each group records: `orphan_ids`, `connected_ids` (other nodes from same chunk), `is_blank_response`
6. For blank-response orphans (absent from `chunk_node_index.json`): cross-references `failed_chunks.json` and string-searches the raw chunk text from `file_manifest.json` to identify the source chunk; flags the node with `extraction_quality: "blank_response"`, `blank_chunk_file`, and `blank_chunk_idx`
7. Writes `intermediate/orphan_candidates.json` as `{"groups": [...], "schema_gap_orphans": [...]}`

No schema type-pair filter — removed in v2 because it was causing false schema-gap orphans when an orphan's type had no compatible schema property for any co-occurring peer type, even when the raw text contained evidence of a connection.

Config keys:
- `orphan_pass.blank_recovery_enabled` — whether blank-response detection is active (default `true`)
- `orphan_pass.connected_sample_size` — max connected nodes included in the Stage 2 prompt (default 20)

#### Stage 2 — `orphan_connect` (`is_llm_step=True`)

`confirm_orphan_chunk_groups()` in `src/mykg/orphan_connector.py`:

1. For each `OrphanChunkGroup`, makes one LLM call with:
   - Full chunk text excerpt — configured via `orphan_pass.excerpt_window` and `orphan_pass.excerpt_context` (character counts, not tokens)
   - All orphan node IDs and display names
   - A sample of connected nodes (`connected_sample_size`)
   - All schema properties
2. LLM returns a JSON array of edges
3. Each edge is validated (type must be in schema; from/to must be known node IDs); invalid edges are dropped
4. Updates `extraction_quality` on blank-response nodes:
   - `blank_response → blank_recovered` (≥1 edge confirmed)
   - `blank_response → blank_unresolved` (no edges found)
5. Confirmed edges carry `"method": "orphan_inferred"`
6. Merges confirmed edges into `intermediate/edge_metadata.json`
7. Writes `intermediate/orphan_connections.json` and `intermediate/orphan_log.json`

#### Blank-Response Orphan Recovery (D33)

When `_extract_chunk` returns `None` during Pass 2 (blank or unparseable LLM response after all retries), pass2 records `{filename, chunk_idx, reason: "blank_response"}` to `intermediate/failed_chunks.json`. In `orphan_score`, any orphan whose stable ID is absent from `chunk_node_index.json` is cross-referenced against `failed_chunks.json`. If a match is found, the node is flagged with `extraction_quality: "blank_response"` and routed through `orphan_connect` for recovery. After Stage 2:

- `blank_recovered` — ≥1 edge was confirmed for the node
- `blank_unresolved` — no edges found; node remains in all final outputs with the flag set (epistemically distinct from genuine singletons where the `extraction_quality` field is absent)

#### Re-entry Points

| Command | Effect |
|---|---|
| `--from-step orphan_score` | Reruns both Stage 1 and Stage 2 |
| `--from-step orphan_connect` | Reruns Stage 2 only; reuses `orphan_candidates.json` from Stage 1 |

#### Config Keys

| Key | Default | Description |
|---|---|---|
| `orphan_pass.excerpt_window` | 400 | Character window around orphan mention used as LLM context in Stage 2 |
| `orphan_pass.excerpt_context` | 150 | Characters of surrounding context added around the window |
| `orphan_pass.blank_recovery_enabled` | `true` | Enable/disable blank-response orphan detection |
| `orphan_pass.connected_sample_size` | 20 | Max connected nodes included in the chunk recovery prompt |

For the schema-gap feedback loop and surgical re-extraction triggered when orphans remain unconnected after Stage 2, see [Option E: Schema-Gap Loop and Surgical Re-extraction](#schema-gap-loop-and-surgical-re-extraction).

---

## Pass 1: Three-Stage Schema Induction

After all batch LLM calls complete, Pass 1 runs three sequential algorithmic and LLM stages before writing the final `intermediate/schema.json`:

### Stage 1: Parallel Batch LLM Calls → Raw Proposals

`run_pass1()` in `src/mykg/pass1.py` dispatches one LLM call per batch via `ThreadPoolExecutor(max_workers=pass1.max_workers)`. Each worker returns a `{concepts, properties}` proposal dict (or `None` on parse failure). Results are collected via `as_completed()`, sorted by batch index for determinism, and `None` results are filtered out. If all batches fail, a `RuntimeError` halts the pipeline immediately.

Config keys:
- `pass1.max_workers` (default 4) — parallel LLM workers
- `pass1.batch_token_target` — max tokens per batch
- `pass1.per_file_batching` (default false) — when true, chunks from different files are never mixed

### Stage 2: Algorithmic Merge

`merge_proposals()` in `src/mykg/schema_merge.py` unions all batch results:
- Seeded with locked classes/properties from `--base-schema` (if provided)
- Deduplicates concepts by `synonym_match(a, b)` (exact → normalised → SKOS thesaurus)
- Unions attribute lists per surviving concept/property
- Rejects any concept named "Relationship" (Invariant 5)
- Writes `intermediate/schema.json` and appends `pass1_merge` delta to `schema_history/`

### Stage 3: Harmonization LLM Call

`harmonize_schema()` in `src/mykg/schema_merge.py` makes one LLM call that sees both the merged schema and all raw batch proposals. This allows the LLM to detect semantic near-duplicates that exact-match missed — for example "MilitaryUnit" and "ArmyUnit" proposed by different batches. The function:
- Sends the full merged schema and full raw proposals without truncation
- Uses the adapter's default max_tokens and timeout from the llm: profile block
- Returns the original schema unchanged if the response is unparseable
- Appends `schema_harmonize` delta to `schema_history/`

**Why this matters:** The algorithmic merge catches formatting differences (PascalCase vs snake_case) and SKOS synonyms. The harmonization LLM catches semantic near-duplicates that have no lexical overlap — cases the human reviewer would otherwise have to catch manually.

### Stage 4: Quality Review LLM Call

`review_schema_quality()` in `src/mykg/schema_merge.py` makes one LLM call to address structural and quality issues:
- **Bare concepts** — any concept with no attributes receives at least a "name" attribute
- **Narrow domains/ranges** — overly specific property domain/range is broadened to the most general compatible parent
- **Singleton types** — named-entity concept types (e.g. "FourthAirForce", "ColonelSmith") are removed; the LLM is instructed to extract them as instances of a general class instead
- **Ambiguous property names** — overly generic names are made more specific (e.g. "concerns" → "subject_of")
- **Inheritance depth** — subclasses with no own attributes and no exclusive properties are collapsed into their parent
- Appends `schema_quality` delta to `schema_history/`

**Why this matters:** Without quality review, Pass 1 can produce concept proliferation (dozens of near-identical named-entity types), bare concepts with no attributes, and properties with ranges so narrow they exclude most instances.

### Schema History Tracking

Every stage that writes `schema.json` calls `schema_history.write_schema(schema, intermediate_dir, trigger)` instead of writing directly. This records a numbered delta file `intermediate/schema_history/<seq>_<trigger>.json` with:
- Which concepts and properties were added and removed
- Running totals
- UTC timestamp and trigger label

Trigger labels: `pass1_merge`, `schema_harmonize`, `schema_quality`, `schema_validate`, `schema_gap`, `schema_gap_correct`.

---

## Option E: Chunk-Level Orphan Pass (Current Implementation)

### The Problem with Option A (Per-Pair LLM Calls)

The original orphan-connection design made one LLM call per `(orphan, candidate)` pair. For N orphans each with K candidates, this is N×K LLM calls. In a real test run with 36 orphan nodes and average 2.5 candidates each, this produced ~90 LLM calls — each with only a 400-char excerpt as context.

Additional problems:
- The schema type-pair filter (only domain/range-compatible pairs were kept) caused false schema-gap orphans when an orphan's type had no compatible property for any co-occurring peer type — even when the raw text contained evidence of a connection.
- Blank-response chunks (where Pass 2 `_extract_chunk` returned `None`) left orphan nodes invisible because no `chunk_node_index` entry was written for them.

### Option E Design: Group by Source Chunk, One LLM Call per Group

Instead of iterating over candidate pairs, Option E groups all orphan nodes by their source chunk. For each unique `(filename, chunk_idx)` group, one LLM call is made with the full chunk text as context.

**Stage 1 — `orphan_score` (`is_llm_step=False`):**

`score_orphan_candidates_v2()` in `src/mykg/orphan_connector.py`:
1. Identifies all orphan nodes (nodes with no edge endpoints in `edge_metadata.json`)
2. Builds an inverted index from `chunk_node_index.json`: `{node_id → [chunk_keys]}`
3. For each orphan, finds the chunk(s) it appeared in
4. Groups all orphans by chunk key → one `OrphanChunkGroup` per `(filename, chunk_idx)`
5. Each group records: `orphan_ids`, `connected_ids` (other nodes from same chunk), `is_blank_response`
6. For blank-response orphans (absent from `chunk_node_index.json`): cross-references `failed_chunks.json` and string-searches the raw chunk text from `file_manifest.json` to identify the source chunk; flags the node with `extraction_quality: "blank_response"`
7. Writes `intermediate/orphan_candidates.json` as `{"groups": [...], "schema_gap_orphans": [...]}`

Config keys:
- `orphan_pass.blank_recovery_enabled` — whether blank-response detection is active
- `orphan_pass.connected_sample_size` — max connected nodes included in the Stage 2 prompt

**Stage 2 — `orphan_connect` (`is_llm_step=True`):**

`confirm_orphan_chunk_groups()` in `src/mykg/orphan_connector.py`:
1. For each `OrphanChunkGroup`, makes one LLM call with:
   - Full chunk text excerpt — configured via `orphan_pass.excerpt_window` and `orphan_pass.excerpt_context` (character counts, not tokens)
   - All orphan node IDs and display names
   - A sample of connected nodes (`connected_sample_size`)
   - All schema properties
2. LLM returns a JSON array of edges
3. Each edge is validated (type must be in schema; from/to must be known node IDs); invalid edges are dropped
4. Updates `extraction_quality` on blank-response nodes: `blank_response → blank_recovered` (≥1 edge confirmed) or `blank_response → blank_unresolved` (no edges)
5. Confirmed edges carry `"method": "orphan_inferred"`
6. Merges confirmed edges into `intermediate/edge_metadata.json`
7. Writes `intermediate/orphan_connections.json` and `intermediate/orphan_log.json`

**Performance:** In a test run with 288 source files, the chunk-level approach processed 36 chunk groups in ~34 LLM calls vs ~90 pair-based calls. Total prompt tokens per call increased, but total calls dropped by ~62%.

### Schema-Gap Loop and Surgical Re-extraction

When `orphan_connect` determines that some orphans have no schema-compatible edges, it calls `propose_schema_additions()` to ask the LLM to propose new RDFS properties. If net-new properties are accepted:
1. `schema_history.write_schema()` appends a `schema_gap` delta
2. `step_orphan_connect` raises `SchemaUpdatedError(new_property_names, gap_orphans=...)`
3. The orchestrator catches this and populates `ctx.schema_hints` with per-orphan data: `orphan_id`, `orphan_type`, `orphan_name`, `new_properties`, `shared_chunks`
4. Instead of deleting shard directories, the orchestrator invalidates only step outputs (`_SCHEMA_RESTART_INVALIDATE`) — shards are preserved
5. Pass 2 receives `reextract_chunks` dict and `prior_extractions` from shards; only the specific chunks in `schema_hints.shared_chunks` are re-extracted (surgical re-extraction, D37)
6. New edges from re-extracted chunks are merged back into existing shards

The restart count is capped at `orphan_pass.schema_max_restarts` (default 2 for openrouter-free, 1 for claude-cli).

The same chunk-targeting mechanism is used by `merge-graphs` surgical re-extraction (D38). When the merged schema introduces new properties absent from a source session, `_build_targeted_reextract_chunks()` in `merger.py` walks `chunk_node_index` to find chunks containing nodes whose types match the domain or range of each new property, then passes only those chunks to `run_pass2()` via `reextract_chunks`. The `surgical_top_k_chunks_per_property` config key (default 0 = no cap) bounds the chunk count per property by co-occurrence score — the same bounded-cost philosophy as `top_k_per_orphan`.
