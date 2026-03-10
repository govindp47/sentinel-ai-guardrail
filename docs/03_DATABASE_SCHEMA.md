# 03_DATABASE_SCHEMA.md

# SentinelAI Guardrail — Database Schema

---

## 1. Schema Philosophy

The schema is designed around three concerns:

1. **Request audit immutability.** Every guardrail request and its full pipeline result is written once and never mutated. Updates to derived fields (retry outcomes, final decision) are handled by inserting child records or updating a status column on the parent row within a single transaction — never by overwriting historical pipeline data.

2. **Session scoping for MVP.** All request records carry a `session_id` (a client-generated UUID stored in browser `sessionStorage`). In MVP, records are not exposed across sessions. The schema is session-aware from day one so that cross-session persistence (Phase 3) is an index addition and query change, not a schema migration.

3. **Separation of hot and cold data.** The `analytics_counters` table is updated atomically per request and serves the dashboard without scanning the `requests` table. The `requests` and `audit_*` tables are append-only and serve the Request Explorer. These two access patterns never interfere.

---

## 2. Text-Based ER Diagram

```
┌───────────────────────────┐
│         sessions          │
│───────────────────────────│
│ PK  id (UUID)             │
│     created_at            │
│     policy_snapshot_id FK─┼──────────────────────────────┐
└─────────────┬─────────────┘                              │
              │ 1:N                                        │
┌─────────────▼─────────────┐                              │
│         requests          │                              │
│───────────────────────────│                              │
│ PK  id (UUID)             │                              │
│ FK  session_id            │                              │
│ FK  policy_snapshot_id ───┼──────────────────────────────┤
│     prompt_hash           │                              │
│     prompt_masked_text    │                              │
│     model_provider        │                              │
│     model_name            │                              │
│ FK  kb_document_set_id    │                              │
│     status                │                              │
│     retry_count           │                              │
│     total_latency_ms      │                              │
│     tokens_in             │                              │
│     tokens_out            │                              │
│     risk_score            │                              │
│     confidence_score      │                              │
│     confidence_label      │                              │
│     guardrail_decision    │                              │
│     decision_reason       │                              │
│     final_response_text   │                              │
│     pii_detected          │                              │
│     created_at            │                              │
└──┬──────────┬─────────────┘                              │
   │          │                                            │
   │ 1:N      │ 1:N                                        │
   │          │                                            │
┌──▼──────────┴────────────┐  ┌───────────────────────┐   │
│     pipeline_traces      │  │    request_claims     │   │
│──────────────────────────│  │───────────────────────│   │
│ PK  id (UUID)            │  │ PK  id (UUID)         │   │
│ FK  request_id           │  │ FK  request_id        │   │
│     attempt_number       │  │     claim_text        │   │
│     stage_name           │  │     claim_index       │   │
│     stage_status         │  │     verification_status│  │
│     stage_latency_ms     │  │     justification     │   │
│     stage_metadata_json  │  │     confidence_contribution│
│     created_at           │  │     created_at        │   │
└──────────────────────────┘  └────────────┬──────────┘   │
                                           │ 1:N          │
                              ┌────────────▼──────────┐   │
                              │   claim_evidence      │   │
                              │───────────────────────│   │
                              │ PK  id (UUID)         │   │
                              │ FK  claim_id          │   │
                              │ FK  kb_chunk_id       │   │
                              │     relevance_score   │   │
                              │     rank              │   │
                              │     created_at        │   │
                              └───────────────────────┘   │
                                                          │
┌─────────────────────────────────────────────────────────▼──┐
│                     policy_snapshots                        │
│─────────────────────────────────────────────────────────────│
│ PK  id (UUID)                                               │
│ FK  session_id                                              │
│     accept_threshold      (int, 0-100)                      │
│     warn_threshold        (int, 0-100)                      │
│     block_threshold       (int, 0-100)                      │
│     max_retries           (int)                             │
│     restricted_categories (JSON array of strings)           │
│     allowed_topics        (JSON array of strings)           │
│     fallback_priority     (JSON ordered array)              │
│     module_flags          (JSON: {injection: bool, ...})    │
│     created_at                                              │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│           kb_documents                  │
│─────────────────────────────────────────│
│ PK  id (UUID)                           │
│ FK  session_id                          │
│     filename                            │
│     file_size_bytes                     │
│     mime_type                           │
│     storage_path                        │
│     status                              │
│     chunk_count                         │
│     error_message                       │
│     created_at                          │
│     indexed_at                          │
└──────────────┬──────────────────────────┘
               │ 1:N
┌──────────────▼──────────────────────────┐
│             kb_chunks                   │
│─────────────────────────────────────────│
│ PK  id (UUID)                           │
│ FK  document_id                         │
│     chunk_index           (int)         │
│     chunk_text                          │
│     chunk_char_start      (int)         │
│     chunk_char_end        (int)         │
│     faiss_vector_id       (int)         │
│     created_at                          │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│         analytics_counters              │
│─────────────────────────────────────────│
│ PK  id (UUID)                           │
│     session_id                          │
│     date_bucket           (DATE)        │
│     model_provider                      │
│     model_name                          │
│     total_requests        (int)         │
│     total_accepted        (int)         │
│     total_warned          (int)         │
│     total_retried         (int)         │
│     total_blocked         (int)         │
│     total_hallucinations_detected (int) │
│     total_safety_triggered(int)         │
│     sum_confidence_score  (int)         │
│     sum_latency_ms        (bigint)      │
│     sum_tokens_in         (bigint)      │
│     sum_tokens_out        (bigint)      │
│     updated_at                          │
└─────────────────────────────────────────┘

┌──────────────────────────────────────────┐
│         safety_filter_results            │
│──────────────────────────────────────────│
│ PK  id (UUID)                            │
│ FK  request_id                           │
│     filter_name                          │
│     result          (clean|flagged)      │
│     score           (float)              │
│     created_at                           │
└──────────────────────────────────────────┘
```

---

## 3. Complete Entity Definitions

### 3.1 `sessions`

Represents a browser session. Created on first request from a new session ID.

```sql
CREATE TABLE sessions (
    id                  TEXT        PRIMARY KEY,          -- UUID, client-generated
    policy_snapshot_id  TEXT        REFERENCES policy_snapshots(id) ON DELETE SET NULL,
    created_at          DATETIME    NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    last_active_at      DATETIME    NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);

CREATE INDEX idx_sessions_created_at ON sessions(created_at);
```

**Notes:**

- `id` is a UUID generated by the browser at session start and sent as a header (`X-Session-ID`) on every request.
- `policy_snapshot_id` points to the most recently saved policy for this session. NULL until the user saves a policy.
- `last_active_at` is updated on every request for future session expiry mechanisms.

---

### 3.2 `policy_snapshots`

Immutable snapshots of the policy configuration at the time a request was processed. Every request records the exact policy that governed it.

```sql
CREATE TABLE policy_snapshots (
    id                      TEXT        PRIMARY KEY,       -- UUID
    session_id              TEXT        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    accept_threshold        INTEGER     NOT NULL DEFAULT 70
                                        CHECK (accept_threshold BETWEEN 0 AND 100),
    warn_threshold          INTEGER     NOT NULL DEFAULT 40
                                        CHECK (warn_threshold BETWEEN 0 AND 100),
    block_threshold         INTEGER     NOT NULL DEFAULT 0
                                        CHECK (block_threshold BETWEEN 0 AND 100),
    max_retries             INTEGER     NOT NULL DEFAULT 2
                                        CHECK (max_retries BETWEEN 0 AND 5),
    restricted_categories   TEXT        NOT NULL DEFAULT '[]',  -- JSON array
    allowed_topics          TEXT        NOT NULL DEFAULT '[]',  -- JSON array
    fallback_priority       TEXT        NOT NULL DEFAULT '["retry_prompt","retry_lower_temp","rag_augmentation","alternate_model"]',
    module_flags            TEXT        NOT NULL DEFAULT '{"injection_detection":true,"pii_detection":true,"policy_filter":true,"hallucination_detection":true,"safety_filters":true}',
    created_at              DATETIME    NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);

CREATE INDEX idx_policy_snapshots_session ON policy_snapshots(session_id, created_at DESC);
```

**Integrity rule:** `block_threshold < warn_threshold < accept_threshold` is enforced at the application layer (Policy Configuration save validation) and as a SQLite CHECK constraint pair:

```sql
CHECK (block_threshold < warn_threshold),
CHECK (warn_threshold < accept_threshold)
```

---

### 3.3 `requests`

The central fact table. One row per top-level guardrail request (retries are represented in `pipeline_traces`, not as separate request rows).

```sql
CREATE TABLE requests (
    id                      TEXT        PRIMARY KEY,       -- UUID, server-generated
    session_id              TEXT        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    policy_snapshot_id      TEXT        NOT NULL REFERENCES policy_snapshots(id),
    kb_document_set_id      TEXT,                         -- NULL if no KB selected; future: FK to kb_sets
    prompt_hash             TEXT        NOT NULL,          -- SHA-256 of original prompt text
    prompt_masked_text      TEXT        NOT NULL,          -- PII-masked version; stored for audit display
    pii_detected            INTEGER     NOT NULL DEFAULT 0 CHECK (pii_detected IN (0, 1)),
    pii_types_detected      TEXT        NOT NULL DEFAULT '[]',  -- JSON array of PII type strings
    model_provider          TEXT        NOT NULL CHECK (model_provider IN ('ollama', 'openai')),
    model_name              TEXT        NOT NULL,
    status                  TEXT        NOT NULL DEFAULT 'pending'
                                        CHECK (status IN ('pending','processing','completed','failed','blocked')),
    retry_count             INTEGER     NOT NULL DEFAULT 0,
    total_latency_ms        INTEGER,
    tokens_in               INTEGER,
    tokens_out              INTEGER,
    risk_score              INTEGER     CHECK (risk_score BETWEEN 0 AND 100),
    confidence_score        INTEGER     CHECK (confidence_score BETWEEN 0 AND 100),
    confidence_label        TEXT        CHECK (confidence_label IN ('high','medium','low')),
    confidence_signal_breakdown TEXT,                     -- JSON: {evidence_similarity: 0.8, ...}
    guardrail_decision      TEXT        CHECK (guardrail_decision IN (
                                            'accept','accept_with_warning','retry_prompt',
                                            'retry_alternate_model','trigger_rag','block')),
    decision_reason         TEXT,
    decision_triggered_rule TEXT,
    final_response_text     TEXT,                         -- NULL if blocked
    block_reason            TEXT,                         -- NULL if not blocked
    fallback_strategy_used  TEXT,                         -- NULL if no fallback triggered
    created_at              DATETIME    NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    completed_at            DATETIME
);

CREATE INDEX idx_requests_session        ON requests(session_id, created_at DESC);
CREATE INDEX idx_requests_status         ON requests(status);
CREATE INDEX idx_requests_decision       ON requests(guardrail_decision);
CREATE INDEX idx_requests_confidence     ON requests(confidence_score);
CREATE INDEX idx_requests_model          ON requests(model_provider, model_name);
CREATE INDEX idx_requests_created        ON requests(created_at DESC);
CREATE INDEX idx_requests_prompt_hash    ON requests(prompt_hash);   -- for duplicate detection
```

**Soft delete:** Requests are never deleted in MVP (session-scoped; expire with session). No `deleted_at` column required.

**PII masking rule:** The original prompt text is never written to the database. The application layer runs PII detection first; if PII is detected, the masked version is stored in `prompt_masked_text`. The `prompt_hash` is the SHA-256 of the *original* text (for duplicate detection) and is stored before masking.

---

### 3.4 `pipeline_traces`

One row per pipeline stage per attempt (including retries). Enables full step-by-step trace reconstruction.

```sql
CREATE TABLE pipeline_traces (
    id                  TEXT        PRIMARY KEY,       -- UUID
    request_id          TEXT        NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    attempt_number      INTEGER     NOT NULL DEFAULT 1, -- 1 = original, 2+ = retries
    stage_order         INTEGER     NOT NULL,           -- 1-11, matches PRD stage sequence
    stage_name          TEXT        NOT NULL CHECK (stage_name IN (
                                        'prompt_received',
                                        'prompt_validation',
                                        'llm_generation',
                                        'claim_extraction',
                                        'evidence_retrieval',
                                        'claim_verification',
                                        'safety_filter_checks',
                                        'confidence_score_calculation',
                                        'guardrail_decision',
                                        'fallback_executed',
                                        'final_response_returned'
                                    )),
    stage_status        TEXT        NOT NULL CHECK (stage_status IN (
                                        'passed','flagged','failed','skipped','not_reached','in_progress'
                                    )),
    stage_latency_ms    INTEGER,
    stage_metadata      TEXT        NOT NULL DEFAULT '{}',  -- JSON: stage-specific detail
    created_at          DATETIME    NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);

CREATE INDEX idx_traces_request         ON pipeline_traces(request_id, attempt_number, stage_order);
CREATE UNIQUE INDEX idx_traces_unique   ON pipeline_traces(request_id, attempt_number, stage_name);
```

**`stage_metadata` JSON examples per stage:**

| Stage | Metadata Shape |
|---|---|
| `prompt_validation` | `{"injection_result":"pass","pii_result":"flag","pii_types":["email"],"policy_result":"pass","risk_score":22}` |
| `llm_generation` | `{"model":"mistral","tokens_in":312,"tokens_out":187,"latency_ms":8432}` |
| `claim_extraction` | `{"claim_count":4,"claims":["Paris is the capital of France",...]}` |
| `evidence_retrieval` | `{"chunks_retrieved":5,"top_similarity":0.91}` |
| `claim_verification` | `{"supported":3,"unsupported":1,"contradicted":0}` |
| `safety_filter_checks` | `{"triggered":[],"scores":{"toxicity":0.01,"hate_speech":0.02}}` |
| `confidence_score_calculation` | `{"score":78,"label":"high","breakdown":{"evidence_similarity":0.88,"claim_ratio":0.75,"safety_penalty":0}}` |
| `guardrail_decision` | `{"decision":"accept","reason":"all_signals_positive","triggered_rule":null}` |
| `fallback_executed` | `{"strategy":"retry_prompt","attempt":2}` |

---

### 3.5 `request_claims`

One row per factual claim extracted from the LLM response.

```sql
CREATE TABLE request_claims (
    id                          TEXT        PRIMARY KEY,
    request_id                  TEXT        NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    attempt_number              INTEGER     NOT NULL DEFAULT 1,
    claim_index                 INTEGER     NOT NULL,   -- order of extraction, 0-based
    claim_text                  TEXT        NOT NULL,
    verification_status         TEXT        NOT NULL CHECK (verification_status IN (
                                                'supported','unsupported','contradicted','unverified'
                                            )),
    justification               TEXT,
    confidence_contribution     REAL,                   -- this claim's weighted contribution to overall score
    created_at                  DATETIME    NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);

CREATE INDEX idx_claims_request ON request_claims(request_id, attempt_number, claim_index);
```

---

### 3.6 `claim_evidence`

One row per evidence chunk retrieved for a claim.

```sql
CREATE TABLE claim_evidence (
    id                  TEXT        PRIMARY KEY,
    claim_id            TEXT        NOT NULL REFERENCES request_claims(id) ON DELETE CASCADE,
    kb_chunk_id         TEXT        NOT NULL REFERENCES kb_chunks(id) ON DELETE SET NULL,
    relevance_score     REAL        NOT NULL CHECK (relevance_score BETWEEN 0.0 AND 1.0),
    rank                INTEGER     NOT NULL,           -- 1 = most relevant
    created_at          DATETIME    NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);

CREATE INDEX idx_evidence_claim ON claim_evidence(claim_id, rank);
```

---

### 3.7 `safety_filter_results`

One row per safety filter per request attempt.

```sql
CREATE TABLE safety_filter_results (
    id              TEXT        PRIMARY KEY,
    request_id      TEXT        NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    attempt_number  INTEGER     NOT NULL DEFAULT 1,
    filter_name     TEXT        NOT NULL CHECK (filter_name IN (
                                    'toxicity','hate_speech','harmful_instruction',
                                    'severe_toxicity','obscene','threat','insult',
                                    'identity_attack','sexual_explicit'
                                )),
    result          TEXT        NOT NULL CHECK (result IN ('clean','flagged')),
    score           REAL        NOT NULL CHECK (score BETWEEN 0.0 AND 1.0),
    created_at      DATETIME    NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);

CREATE INDEX idx_safety_request ON safety_filter_results(request_id, attempt_number);
```

---

### 3.8 `kb_documents`

Tracks uploaded knowledge base documents.

```sql
CREATE TABLE kb_documents (
    id                  TEXT        PRIMARY KEY,
    session_id          TEXT        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    filename            TEXT        NOT NULL,
    original_filename   TEXT        NOT NULL,
    file_size_bytes     INTEGER     NOT NULL,
    mime_type           TEXT        NOT NULL,
    storage_path        TEXT        NOT NULL UNIQUE,    -- path on local filesystem
    status              TEXT        NOT NULL DEFAULT 'pending'
                                    CHECK (status IN ('pending','indexing','ready','failed')),
    chunk_count         INTEGER     NOT NULL DEFAULT 0,
    chunk_size          INTEGER     NOT NULL DEFAULT 512,   -- characters per chunk
    chunk_overlap       INTEGER     NOT NULL DEFAULT 64,    -- character overlap between chunks
    error_message       TEXT,
    created_at          DATETIME    NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    indexed_at          DATETIME
);

CREATE INDEX idx_kb_docs_session ON kb_documents(session_id, created_at DESC);
CREATE INDEX idx_kb_docs_status  ON kb_documents(status);
```

---

### 3.9 `kb_chunks`

One row per text chunk derived from a document.

```sql
CREATE TABLE kb_chunks (
    id                  TEXT        PRIMARY KEY,
    document_id         TEXT        NOT NULL REFERENCES kb_documents(id) ON DELETE CASCADE,
    chunk_index         INTEGER     NOT NULL,
    chunk_text          TEXT        NOT NULL,
    chunk_char_start    INTEGER     NOT NULL,
    chunk_char_end      INTEGER     NOT NULL,
    faiss_vector_id     INTEGER,                        -- FAISS internal sequential ID; NULL until indexed
    token_count         INTEGER,                        -- approximate token count of this chunk
    created_at          DATETIME    NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);

CREATE INDEX idx_chunks_document        ON kb_chunks(document_id, chunk_index);
CREATE INDEX idx_chunks_faiss_id        ON kb_chunks(faiss_vector_id);  -- for FAISS ID → chunk reverse lookup
```

---

### 3.10 `analytics_counters`

Pre-aggregated counters updated atomically after each request. Keyed on (session, date, model) for flexible filtering.

```sql
CREATE TABLE analytics_counters (
    id                          TEXT        PRIMARY KEY,
    session_id                  TEXT        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    date_bucket                 TEXT        NOT NULL,   -- ISO date string: '2024-03-15'
    model_provider              TEXT        NOT NULL,
    model_name                  TEXT        NOT NULL,
    total_requests              INTEGER     NOT NULL DEFAULT 0,
    total_accepted              INTEGER     NOT NULL DEFAULT 0,
    total_warned                INTEGER     NOT NULL DEFAULT 0,
    total_retried               INTEGER     NOT NULL DEFAULT 0,
    total_blocked               INTEGER     NOT NULL DEFAULT 0,
    total_hallucinations_detected INTEGER   NOT NULL DEFAULT 0,  -- requests with ≥1 unsupported/contradicted claim
    total_safety_triggered      INTEGER     NOT NULL DEFAULT 0,
    sum_confidence_score        INTEGER     NOT NULL DEFAULT 0,
    sum_latency_ms              INTEGER     NOT NULL DEFAULT 0,
    sum_tokens_in               INTEGER     NOT NULL DEFAULT 0,
    sum_tokens_out              INTEGER     NOT NULL DEFAULT 0,
    updated_at                  DATETIME    NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);

CREATE UNIQUE INDEX idx_analytics_key ON analytics_counters(session_id, date_bucket, model_provider, model_name);
CREATE INDEX idx_analytics_session    ON analytics_counters(session_id, date_bucket DESC);
```

**Update pattern (INSERT OR REPLACE / UPSERT):**

```sql
INSERT INTO analytics_counters
    (id, session_id, date_bucket, model_provider, model_name,
     total_requests, total_accepted, total_blocked, sum_confidence_score, sum_latency_ms,
     sum_tokens_in, sum_tokens_out, updated_at)
VALUES
    (:new_id, :session_id, :date, :provider, :model,
     1, :accepted, :blocked, :confidence, :latency,
     :tokens_in, :tokens_out, CURRENT_TIMESTAMP)
ON CONFLICT(session_id, date_bucket, model_provider, model_name) DO UPDATE SET
    total_requests              = total_requests + 1,
    total_accepted              = total_accepted + excluded.total_accepted,
    total_blocked               = total_blocked + excluded.total_blocked,
    sum_confidence_score        = sum_confidence_score + excluded.sum_confidence_score,
    sum_latency_ms              = sum_latency_ms + excluded.sum_latency_ms,
    sum_tokens_in               = sum_tokens_in + excluded.sum_tokens_in,
    sum_tokens_out              = sum_tokens_out + excluded.sum_tokens_out,
    updated_at                  = CURRENT_TIMESTAMP;
```

---

## 4. Critical Queries

### 4.1 Request Explorer — List Requests (paginated, filtered)

```sql
SELECT
    r.id,
    r.created_at,
    r.model_provider,
    r.model_name,
    r.confidence_score,
    r.confidence_label,
    r.guardrail_decision,
    r.status,
    r.pii_detected
FROM requests r
WHERE r.session_id = :session_id
  AND (:decision_filter IS NULL OR r.guardrail_decision = :decision_filter)
  AND (:model_filter IS NULL OR r.model_name = :model_filter)
  AND (:min_confidence IS NULL OR r.confidence_score >= :min_confidence)
  AND (:max_confidence IS NULL OR r.confidence_score <= :max_confidence)
ORDER BY r.created_at DESC
LIMIT :page_size OFFSET :offset;
```

### 4.2 Request Detail — Full Audit Record

```sql
-- Request row
SELECT * FROM requests WHERE id = :request_id AND session_id = :session_id;

-- Pipeline trace (all attempts, ordered)
SELECT * FROM pipeline_traces
WHERE request_id = :request_id
ORDER BY attempt_number, stage_order;

-- Claims with evidence
SELECT
    rc.id AS claim_id,
    rc.claim_index,
    rc.claim_text,
    rc.verification_status,
    rc.justification,
    rc.confidence_contribution,
    ce.rank,
    ce.relevance_score,
    kc.chunk_text,
    kc.chunk_index,
    kd.original_filename
FROM request_claims rc
LEFT JOIN claim_evidence ce ON ce.claim_id = rc.id
LEFT JOIN kb_chunks kc ON kc.id = ce.kb_chunk_id
LEFT JOIN kb_documents kd ON kd.id = kc.document_id
WHERE rc.request_id = :request_id AND rc.attempt_number = :attempt_number
ORDER BY rc.claim_index, ce.rank;

-- Safety filter results
SELECT * FROM safety_filter_results
WHERE request_id = :request_id
ORDER BY attempt_number, filter_name;
```

### 4.3 Analytics Dashboard — Aggregate by Model

```sql
SELECT
    model_provider,
    model_name,
    SUM(total_requests)                                             AS requests,
    SUM(total_accepted)                                             AS accepted,
    SUM(total_warned)                                               AS warned,
    SUM(total_blocked)                                              AS blocked,
    SUM(total_hallucinations_detected)                              AS hallucinations,
    SUM(total_safety_triggered)                                     AS safety_triggers,
    ROUND(SUM(sum_confidence_score) * 1.0 / NULLIF(SUM(total_requests), 0), 1) AS avg_confidence,
    ROUND(SUM(sum_latency_ms) * 1.0 / NULLIF(SUM(total_requests), 0), 0)       AS avg_latency_ms,
    SUM(sum_tokens_in)                                              AS total_tokens_in,
    SUM(sum_tokens_out)                                             AS total_tokens_out
FROM analytics_counters
WHERE session_id = :session_id
  AND (:date_from IS NULL OR date_bucket >= :date_from)
GROUP BY model_provider, model_name
ORDER BY requests DESC;
```

### 4.4 Knowledge Base — Chunk Retrieval by FAISS IDs

After FAISS returns a list of `faiss_vector_id` values, the application fetches chunk metadata:

```sql
SELECT
    kc.id,
    kc.faiss_vector_id,
    kc.chunk_text,
    kc.chunk_index,
    kd.original_filename,
    kd.id AS document_id
FROM kb_chunks kc
JOIN kb_documents kd ON kd.id = kc.document_id
WHERE kc.faiss_vector_id IN (:faiss_ids)
  AND kd.session_id = :session_id
  AND kd.status = 'ready';
```

---

## 5. Migration Strategy

### 5.1 Migration Tooling

All migrations are managed by **Alembic** with auto-generated scripts reviewed before application.

Directory structure:

```
alembic/
    env.py
    script.py.mako
    versions/
        0001_initial_schema.py
        0002_add_kb_document_sets.py    (Phase 3)
        0003_add_export_audit_flag.py   (Phase 3)
```

### 5.2 Migration Rules

1. **Additive-only in production.** Migrations add columns (with defaults) or add indexes. Destructive operations (DROP COLUMN, ALTER TYPE) are performed only via a two-phase migration: first add the new structure, deploy, then remove the old structure in a follow-up migration.
2. **All new columns must have DEFAULT values** to avoid locking issues on large tables (relevant when migrating to PostgreSQL with data).
3. **Index creation is CONCURRENT on PostgreSQL** (`CREATE INDEX CONCURRENTLY`). Alembic's `op.create_index` call includes `postgresql_concurrently=True` for all new indexes post-MVP.
4. **Each migration file is atomic.** A migration that adds a table and populates it from an existing table wraps both operations in a single transaction.

### 5.3 SQLite → PostgreSQL Migration

When migrating an existing deployment from SQLite to PostgreSQL:

1. Export SQLite data to JSON using a migration script (`scripts/export_sqlite.py`).
2. Provision PostgreSQL and run Alembic migrations to create the schema.
3. Import JSON data using a bulk insert script (`scripts/import_postgres.py`).
4. Verify row counts and key integrity post-import.
5. Switch application `DATABASE_URL` environment variable.
6. Rebuild FAISS indexes from `kb_chunks` table (or migrate the `.faiss` files directly, as FAISS index format is database-independent).

### 5.4 Versioning Strategy

Migration files are named `{4-digit-sequence}_{descriptive_slug}.py`. The sequence number is the single source of truth for migration ordering. Branch migration conflicts are resolved by renumbering the higher branch's migration to the next available sequence number.

---

## 6. Audit Trail Model

The audit trail for a request is reconstructed from four tables:

| Table | Contribution |
|---|---|
| `requests` | Top-level request metadata, scores, decision, final response |
| `pipeline_traces` | Step-by-step stage results with metadata, per attempt |
| `request_claims` | Extracted claims and their verification status |
| `claim_evidence` | Evidence chunks retrieved per claim with relevance scores |
| `safety_filter_results` | Per-filter scores and results |

**Immutability guarantee:** Once a request reaches `status = completed`, `blocked`, or `failed`, no rows are updated or deleted in any of these tables. Retries append new `pipeline_traces` rows with `attempt_number > 1`.

**Replay behavior:** The "Replay Request" action reads `requests.prompt_hash` and looks up the original masked prompt. It creates a *new* `requests` row with a new `id` and `created_at`. The original record is not modified. The new request includes a `replayed_from_request_id` column (TEXT, NULL by default, added in the initial schema for forward compatibility).

---

## 7. Integrity Invariant List

These invariants are enforced at the application layer; the database constraints enforce a subset.

| # | Invariant | Enforcement |
|---|---|---|
| I-01 | `block_threshold < warn_threshold < accept_threshold` in every `policy_snapshots` row | Application + DB CHECK constraints |
| I-02 | `requests.policy_snapshot_id` always references the snapshot active at the time of the request | Application: snapshot is written before the request row |
| I-03 | A `request_claims` row is never written without a corresponding `pipeline_traces` row for `claim_verification` | Application: claims are persisted in the same transaction as the verification trace stage |
| I-04 | `kb_chunks.faiss_vector_id` is unique within a document's KB session | Application: FAISS assigns sequential IDs; the ID map is written atomically with the DB row |
| I-05 | `analytics_counters` is updated in the same database transaction as the `requests` row status update | Application: wrapped in a single SQLAlchemy transaction |
| I-06 | Prompt text is never written to any database column | Application: PII masking occurs before any database write; enforced by code review |
| I-07 | OpenAI API key is never written to any database column or log | Application: key exists only in the request-scoped Python dict; logging middleware strips it |
| I-08 | A request with `pii_detected = 1` never has a replay action enabled | Application: replay endpoint checks `pii_detected` and returns 403 |
| I-09 | `pipeline_traces` rows for a given `(request_id, attempt_number)` cover a contiguous sequence of `stage_order` values starting from 1 | Application: orchestrator writes all reached stages; unstarted stages are written as `not_reached` in the finalization step |
| I-10 | `analytics_counters` values are non-negative | DB CHECK constraints (`>= 0`) on all counter columns |

---

## 8. Soft Delete Strategy

Soft delete is not applicable to the core request audit tables (requests are never deleted by users in MVP; they expire with the session). The following applies:

- **`kb_documents`:** Documents are hard-deleted when the user removes them from the UI. Before deletion, all associated `kb_chunks` rows are deleted (cascade), the FAISS index is rebuilt for the session's KB (or the vectors are removed using FAISS's `IDMap` remove operation), and the file is deleted from disk. A `deleted_at` column is added to `kb_documents` in Phase 3 to support soft delete with undo.
- **`sessions`:** Sessions are never explicitly deleted. A background cleanup job (Phase 3) can purge sessions and their cascaded request data older than a configurable retention window.

---

## 9. Full DDL (SQLite)

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA synchronous = NORMAL;

CREATE TABLE sessions (
    id                  TEXT        PRIMARY KEY,
    policy_snapshot_id  TEXT        REFERENCES policy_snapshots(id) ON DELETE SET NULL,
    created_at          DATETIME    NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    last_active_at      DATETIME    NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);

CREATE TABLE policy_snapshots (
    id                      TEXT    PRIMARY KEY,
    session_id              TEXT    NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    accept_threshold        INTEGER NOT NULL DEFAULT 70  CHECK (accept_threshold  BETWEEN 0 AND 100),
    warn_threshold          INTEGER NOT NULL DEFAULT 40  CHECK (warn_threshold    BETWEEN 0 AND 100),
    block_threshold         INTEGER NOT NULL DEFAULT 0   CHECK (block_threshold   BETWEEN 0 AND 100),
    max_retries             INTEGER NOT NULL DEFAULT 2   CHECK (max_retries        BETWEEN 0 AND 5),
    restricted_categories   TEXT    NOT NULL DEFAULT '[]',
    allowed_topics          TEXT    NOT NULL DEFAULT '[]',
    fallback_priority       TEXT    NOT NULL DEFAULT '["retry_prompt","retry_lower_temp","rag_augmentation","alternate_model"]',
    module_flags            TEXT    NOT NULL DEFAULT '{"injection_detection":true,"pii_detection":true,"policy_filter":true,"hallucination_detection":true,"safety_filters":true}',
    created_at              DATETIME NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    CHECK (block_threshold < warn_threshold),
    CHECK (warn_threshold  < accept_threshold)
);

CREATE TABLE kb_documents (
    id                  TEXT        PRIMARY KEY,
    session_id          TEXT        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    filename            TEXT        NOT NULL,
    original_filename   TEXT        NOT NULL,
    file_size_bytes     INTEGER     NOT NULL,
    mime_type           TEXT        NOT NULL,
    storage_path        TEXT        NOT NULL UNIQUE,
    status              TEXT        NOT NULL DEFAULT 'pending'
                                    CHECK (status IN ('pending','indexing','ready','failed')),
    chunk_count         INTEGER     NOT NULL DEFAULT 0,
    chunk_size          INTEGER     NOT NULL DEFAULT 512,
    chunk_overlap       INTEGER     NOT NULL DEFAULT 64,
    error_message       TEXT,
    created_at          DATETIME    NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    indexed_at          DATETIME
);

CREATE TABLE kb_chunks (
    id                  TEXT        PRIMARY KEY,
    document_id         TEXT        NOT NULL REFERENCES kb_documents(id) ON DELETE CASCADE,
    chunk_index         INTEGER     NOT NULL,
    chunk_text          TEXT        NOT NULL,
    chunk_char_start    INTEGER     NOT NULL,
    chunk_char_end      INTEGER     NOT NULL,
    faiss_vector_id     INTEGER,
    token_count         INTEGER,
    created_at          DATETIME    NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    UNIQUE (document_id, chunk_index)
);

CREATE TABLE requests (
    id                          TEXT        PRIMARY KEY,
    session_id                  TEXT        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    policy_snapshot_id          TEXT        NOT NULL REFERENCES policy_snapshots(id),
    kb_document_set_id          TEXT,
    replayed_from_request_id    TEXT        REFERENCES requests(id) ON DELETE SET NULL,
    prompt_hash                 TEXT        NOT NULL,
    prompt_masked_text          TEXT        NOT NULL,
    pii_detected                INTEGER     NOT NULL DEFAULT 0 CHECK (pii_detected IN (0, 1)),
    pii_types_detected          TEXT        NOT NULL DEFAULT '[]',
    model_provider              TEXT        NOT NULL CHECK (model_provider IN ('ollama','openai')),
    model_name                  TEXT        NOT NULL,
    status                      TEXT        NOT NULL DEFAULT 'pending'
                                            CHECK (status IN ('pending','processing','completed','failed','blocked')),
    retry_count                 INTEGER     NOT NULL DEFAULT 0,
    total_latency_ms            INTEGER,
    tokens_in                   INTEGER,
    tokens_out                  INTEGER,
    risk_score                  INTEGER     CHECK (risk_score BETWEEN 0 AND 100),
    confidence_score            INTEGER     CHECK (confidence_score BETWEEN 0 AND 100),
    confidence_label            TEXT        CHECK (confidence_label IN ('high','medium','low')),
    confidence_signal_breakdown TEXT,
    guardrail_decision          TEXT        CHECK (guardrail_decision IN (
                                                'accept','accept_with_warning','retry_prompt',
                                                'retry_alternate_model','trigger_rag','block')),
    decision_reason             TEXT,
    decision_triggered_rule     TEXT,
    final_response_text         TEXT,
    block_reason                TEXT,
    fallback_strategy_used      TEXT,
    created_at                  DATETIME    NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    completed_at                DATETIME
);

CREATE TABLE pipeline_traces (
    id                  TEXT        PRIMARY KEY,
    request_id          TEXT        NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    attempt_number      INTEGER     NOT NULL DEFAULT 1,
    stage_order         INTEGER     NOT NULL,
    stage_name          TEXT        NOT NULL,
    stage_status        TEXT        NOT NULL,
    stage_latency_ms    INTEGER,
    stage_metadata      TEXT        NOT NULL DEFAULT '{}',
    created_at          DATETIME    NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    UNIQUE (request_id, attempt_number, stage_name)
);

CREATE TABLE request_claims (
    id                      TEXT        PRIMARY KEY,
    request_id              TEXT        NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    attempt_number          INTEGER     NOT NULL DEFAULT 1,
    claim_index             INTEGER     NOT NULL,
    claim_text              TEXT        NOT NULL,
    verification_status     TEXT        NOT NULL CHECK (verification_status IN ('supported','unsupported','contradicted','unverified')),
    justification           TEXT,
    confidence_contribution REAL,
    created_at              DATETIME    NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);

CREATE TABLE claim_evidence (
    id                  TEXT        PRIMARY KEY,
    claim_id            TEXT        NOT NULL REFERENCES request_claims(id) ON DELETE CASCADE,
    kb_chunk_id         TEXT        REFERENCES kb_chunks(id) ON DELETE SET NULL,
    relevance_score     REAL        NOT NULL CHECK (relevance_score BETWEEN 0.0 AND 1.0),
    rank                INTEGER     NOT NULL,
    created_at          DATETIME    NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);

CREATE TABLE safety_filter_results (
    id              TEXT        PRIMARY KEY,
    request_id      TEXT        NOT NULL REFERENCES requests(id) ON DELETE CASCADE,
    attempt_number  INTEGER     NOT NULL DEFAULT 1,
    filter_name     TEXT        NOT NULL,
    result          TEXT        NOT NULL CHECK (result IN ('clean','flagged')),
    score           REAL        NOT NULL CHECK (score BETWEEN 0.0 AND 1.0),
    created_at      DATETIME    NOT NULL DEFAULT (CURRENT_TIMESTAMP)
);

CREATE TABLE analytics_counters (
    id                              TEXT        PRIMARY KEY,
    session_id                      TEXT        NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
    date_bucket                     TEXT        NOT NULL,
    model_provider                  TEXT        NOT NULL,
    model_name                      TEXT        NOT NULL,
    total_requests                  INTEGER     NOT NULL DEFAULT 0 CHECK (total_requests >= 0),
    total_accepted                  INTEGER     NOT NULL DEFAULT 0 CHECK (total_accepted >= 0),
    total_warned                    INTEGER     NOT NULL DEFAULT 0 CHECK (total_warned >= 0),
    total_retried                   INTEGER     NOT NULL DEFAULT 0 CHECK (total_retried >= 0),
    total_blocked                   INTEGER     NOT NULL DEFAULT 0 CHECK (total_blocked >= 0),
    total_hallucinations_detected   INTEGER     NOT NULL DEFAULT 0 CHECK (total_hallucinations_detected >= 0),
    total_safety_triggered          INTEGER     NOT NULL DEFAULT 0 CHECK (total_safety_triggered >= 0),
    sum_confidence_score            INTEGER     NOT NULL DEFAULT 0,
    sum_latency_ms                  INTEGER     NOT NULL DEFAULT 0,
    sum_tokens_in                   INTEGER     NOT NULL DEFAULT 0,
    sum_tokens_out                  INTEGER     NOT NULL DEFAULT 0,
    updated_at                      DATETIME    NOT NULL DEFAULT (CURRENT_TIMESTAMP),
    UNIQUE (session_id, date_bucket, model_provider, model_name)
);

-- Indexes
CREATE INDEX idx_sessions_created_at        ON sessions(created_at);
CREATE INDEX idx_policy_snapshots_session   ON policy_snapshots(session_id, created_at DESC);
CREATE INDEX idx_kb_docs_session            ON kb_documents(session_id, created_at DESC);
CREATE INDEX idx_kb_docs_status             ON kb_documents(status);
CREATE INDEX idx_chunks_document            ON kb_chunks(document_id, chunk_index);
CREATE INDEX idx_chunks_faiss_id            ON kb_chunks(faiss_vector_id);
CREATE INDEX idx_requests_session           ON requests(session_id, created_at DESC);
CREATE INDEX idx_requests_status            ON requests(status);
CREATE INDEX idx_requests_decision          ON requests(guardrail_decision);
CREATE INDEX idx_requests_confidence        ON requests(confidence_score);
CREATE INDEX idx_requests_model             ON requests(model_provider, model_name);
CREATE INDEX idx_requests_created           ON requests(created_at DESC);
CREATE INDEX idx_requests_prompt_hash       ON requests(prompt_hash);
CREATE INDEX idx_traces_request             ON pipeline_traces(request_id, attempt_number, stage_order);
CREATE INDEX idx_claims_request             ON request_claims(request_id, attempt_number, claim_index);
CREATE INDEX idx_evidence_claim             ON claim_evidence(claim_id, rank);
CREATE INDEX idx_safety_request             ON safety_filter_results(request_id, attempt_number);
CREATE INDEX idx_analytics_session          ON analytics_counters(session_id, date_bucket DESC);
```
