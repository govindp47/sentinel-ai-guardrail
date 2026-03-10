# 01_SYSTEM_ARCHITECTURE.md

# SentinelAI Guardrail — System Architecture

---

## 1. High-Level Architecture Diagram

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT TIER                                         │
│                                                                                  │
│  ┌──────────────────────────┐       ┌───────────────────────────────────────┐   │
│  │   Browser (React SPA)    │       │   Developer Application (SDK/REST)    │   │
│  │  - Playground UI         │       │  - REST API consumer                  │   │
│  │  - Analytics Dashboard   │       │  - Python/JS SDK                      │   │
│  │  - Request Explorer      │       └─────────────────┬─────────────────────┘   │
│  │  - KB Management         │                         │                         │
│  │  - Policy Config         │                         │                         │
│  └────────────┬─────────────┘                         │                         │
└───────────────┼───────────────────────────────────────┼─────────────────────────┘
                │  HTTPS / WebSocket                    │  HTTPS REST
                ▼                                       ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                              API GATEWAY / REVERSE PROXY                         │
│                          (Caddy or Nginx — TLS termination,                      │
│                           rate limiting, request ID injection)                   │
└──────────────────────────────┬───────────────────────────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────────────────────────┐
│                         FASTAPI APPLICATION SERVER                               │
│                                                                                  │
│  ┌─────────────────────────────────────────────────────────────────────────┐    │
│  │                        GUARDRAIL PIPELINE ORCHESTRATOR                  │    │
│  │                                                                         │    │
│  │  [1] PromptValidationEngine                                             │    │
│  │       └─ InjectionDetector → PIIDetector → PolicyFilter → RiskScorer   │    │
│  │                                                                         │    │
│  │  [2] LLMExecutionLayer                                                  │    │
│  │       └─ ModelRouter → LocalAdapter (Ollama) | OpenAIAdapter            │    │
│  │                                                                         │    │
│  │  [3] HallucinationDetectionEngine                                       │    │
│  │       └─ ClaimExtractor → KnowledgeRetrievalLayer → ClaimVerifier      │    │
│  │                                                                         │    │
│  │  [4] OutputSafetyFilter                                                 │    │
│  │       └─ ToxicityFilter → HateSpeechFilter → HarmfulInstructionFilter  │    │
│  │                                                                         │    │
│  │  [5] ConfidenceScoringEngine                                            │    │
│  │       └─ SignalAggregator → ScoreNormalizer → LabelClassifier          │    │
│  │                                                                         │    │
│  │  [6] GuardrailDecisionEngine                                            │    │
│  │       └─ PolicyEvaluator → DecisionRouter                              │    │
│  │                                                                         │    │
│  │  [7] FallbackStrategyEngine                                             │    │
│  │       └─ StrategySelector → RetryCoordinator                           │    │
│  └─────────────────────────────────────────────────────────────────────────┘    │
│                                                                                  │
│  ┌──────────────────────┐  ┌───────────────────────┐  ┌──────────────────────┐ │
│  │   REST API Router    │  │  WebSocket Handler    │  │  Background Workers  │ │
│  │  /v1/guardrail       │  │  (pipeline progress   │  │  - KB Indexer        │ │
│  │  /v1/kb              │  │   streaming)          │  │  - Audit Flusher     │ │
│  │  /v1/analytics       │  └───────────────────────┘  └──────────────────────┘ │
│  │  /v1/policy          │                                                       │
│  └──────────────────────┘                                                       │
└────────────────────────────┬─────────────────────────────────────────────────────┘
                             │
        ┌────────────────────┼──────────────────────────┐
        ▼                    ▼                           ▼
┌───────────────┐  ┌──────────────────────┐  ┌──────────────────────────────────┐
│  SQLite /     │  │  Vector Store        │  │  LLM Providers                   │
│  PostgreSQL   │  │  (FAISS or ChromaDB) │  │                                  │
│               │  │                      │  │  ┌────────────────────────────┐  │
│  - requests   │  │  - document chunks   │  │  │ Ollama (local)             │  │
│  - audit_logs │  │  - claim embeddings  │  │  │  - mistral / llama3 / phi3 │  │
│  - kb_docs    │  │                      │  │  └────────────────────────────┘  │
│  - kb_chunks  │  │                      │  │  ┌────────────────────────────┐  │
│  - policies   │  │                      │  │  │ OpenAI API (user-keyed)    │  │
│  - analytics  │  │                      │  │  │  - gpt-4o / gpt-4o-mini   │  │
└───────────────┘  └──────────────────────┘  │  └────────────────────────────┘  │
                                             └──────────────────────────────────┘
```

---

## 2. System Component Breakdown

### 2.1 Client Tier

**React SPA (Vite + TypeScript)**

- Single-page application served as static assets from the reverse proxy.
- Communicates with the backend exclusively via REST (`/v1/*`) and WebSocket for pipeline progress streaming.
- No server-side rendering required; the playground is interactive, not SEO-critical.
- State is managed in-memory per session; no cross-tab or cross-session synchronization.

**Developer SDK**

- Thin Python and JavaScript wrappers around the REST API.
- Exposes typed request/response models.
- Handles retry logic and structured error parsing client-side.

### 2.2 API Gateway / Reverse Proxy

**Caddy (preferred) or Nginx**

- TLS termination (HTTPS enforced).
- Injects `X-Request-ID` header on every inbound request if absent.
- Rate limiting at the IP level (configurable thresholds — see Open Questions Q3).
- Static asset serving for the SPA.
- Proxies `/v1/*` and `/ws/*` to the FastAPI application server.

### 2.3 FastAPI Application Server

The core backend process. Runs as a single Uvicorn ASGI process in MVP with Gunicorn workers for production scale.

Subsystems within the application server:

| Subsystem | Responsibility |
|---|---|
| REST API Router | HTTP endpoint definitions, request deserialization, response serialization |
| WebSocket Handler | Real-time pipeline stage progress push to the browser |
| Guardrail Pipeline Orchestrator | Sequential execution of all pipeline stages; manages stage results, trace construction, and retry coordination |
| PromptValidationEngine | Pre-LLM prompt analysis |
| LLMExecutionLayer | Model-agnostic LLM call abstraction |
| HallucinationDetectionEngine | Post-generation claim extraction and verification |
| KnowledgeRetrievalLayer | Embedding-based evidence retrieval from vector store |
| OutputSafetyFilter | Post-generation content safety analysis |
| ConfidenceScoringEngine | Multi-signal score aggregation |
| GuardrailDecisionEngine | Policy-driven final decision |
| FallbackStrategyEngine | Remediation execution on non-accept decisions |
| Background Workers | Asynchronous knowledge base indexing; non-blocking from the request path |
| Session Store | In-memory request audit records per session (backed by SQLite optionally) |

### 2.4 Persistence Tier

**SQLite (default) / PostgreSQL (production)**

- Stores request records, audit logs, knowledge base document metadata, policy configurations, and aggregate analytics counters.
- SQLite is sufficient for single-instance MVP deployment. PostgreSQL is the upgrade path for multi-instance or persistent deployments.
- Migration managed by Alembic.

**Vector Store (FAISS / ChromaDB)**

- Stores and indexes document chunk embeddings.
- FAISS: in-process, zero-dependency, flat file persistence. Suitable for single-instance deployments.
- ChromaDB: HTTP server mode available for separation of concerns. Selected if multi-process scaling is required.

### 2.5 LLM Providers

**Ollama (local)**

- Runs as a separate process on the same host or in a sidecar container.
- Exposes an OpenAI-compatible REST API at `http://localhost:11434`.
- Default model: configurable (e.g., `mistral`, `llama3`, `phi3`).

**OpenAI API**

- Accessed via the official `openai` Python library.
- API key is passed per-request from the user and is never written to any persistent store.

---

## 3. Clean Architecture Layers

```
┌─────────────────────────────────────────────┐
│           Presentation Layer                │
│  - REST API routers (FastAPI)               │
│  - WebSocket handlers                       │
│  - Request/Response Pydantic schemas        │
│  - Error response formatting                │
└──────────────────────┬──────────────────────┘
                       │ calls
┌──────────────────────▼──────────────────────┐
│           Application Layer                 │
│  - GuardrailPipelineOrchestrator            │
│  - Use case services (SubmitPromptUseCase,  │
│    IndexDocumentUseCase, etc.)              │
│  - Policy resolution                        │
│  - Trace construction                       │
└──────────────────────┬──────────────────────┘
                       │ calls
┌──────────────────────▼──────────────────────┐
│             Domain Layer                    │
│  - Pipeline stage engines (pure domain)     │
│  - GuardrailDecision value object           │
│  - ConfidenceScore value object             │
│  - Claim, Evidence domain models            │
│  - Policy domain model                      │
│  - Business rule enforcement                │
└──────────────────────┬──────────────────────┘
                       │ calls
┌──────────────────────▼──────────────────────┐
│         Infrastructure Layer                │
│  - OllamaAdapter, OpenAIAdapter             │
│  - FAISSVectorStore, ChromaVectorStore      │
│  - SQLiteRepository, PostgresRepository     │
│  - EmbeddingModelAdapter (SentenceTransf.)  │
│  - SafetyClassifierAdapter                  │
│  - FileStorage (document upload handling)   │
└─────────────────────────────────────────────┘
```

**Dependency rule:** Outer layers depend on inner layers. The domain layer has zero dependencies on infrastructure. Adapters implement interfaces defined in the domain/application layer.

---

## 4. Module Boundaries

| Module | Owned By | External Dependencies | Consumed By |
|---|---|---|---|
| `prompt_validation` | Domain | None (pure logic) | Orchestrator |
| `llm_execution` | Infrastructure | Ollama HTTP, OpenAI SDK | Orchestrator |
| `hallucination_detection` | Domain + Infra | EmbeddingAdapter, VectorStore | Orchestrator |
| `knowledge_retrieval` | Infrastructure | VectorStore, EmbeddingAdapter | HallucinationDetection |
| `output_safety` | Infrastructure | Safety classifier (local model or rule-based) | Orchestrator |
| `confidence_scoring` | Domain | None (pure computation) | Orchestrator |
| `guardrail_decision` | Domain | Policy model | Orchestrator |
| `fallback_strategy` | Application | LLMExecution, KnowledgeRetrieval | Orchestrator |
| `kb_management` | Application | FileStorage, VectorStore, EmbeddingAdapter | Background workers |
| `analytics` | Application | RequestRepository | API router |
| `policy_config` | Domain + Application | PolicyRepository | Orchestrator |
| `audit_trail` | Infrastructure | RequestRepository | Orchestrator, API router |

Each module exposes a single public interface class. Cross-module communication is via these interfaces only — no direct import of internal submodules across module boundaries.

---

## 5. Data Flow Lifecycle

### 5.1 Standard Request Lifecycle (No Retry)

```
Browser/SDK
    │
    ▼
POST /v1/guardrail/submit
    │
    ▼
[API Router] — deserialize GuardrailRequest → assign request_id → emit WebSocket event: "started"
    │
    ▼
[GuardrailPipelineOrchestrator.execute(request_id, prompt, model, kb_id, policy)]
    │
    ├─ Stage 1: PromptValidationEngine.validate(prompt, policy)
    │     ├─ InjectionDetector.check(prompt) → Result(pass|flag|block, detail)
    │     ├─ PIIDetector.check(prompt) → Result(pass|flag|block, pii_types[])
    │     ├─ PolicyFilter.check(prompt, policy.restricted_categories) → Result
    │     ├─ RiskScorer.score(results[]) → risk_score: int 0-100
    │     └─ emit WebSocket: stage_complete("prompt_validation", status, metadata)
    │     [IF any result == BLOCK → short-circuit: build_trace → return BlockedResponse]
    │
    ├─ Stage 2: LLMExecutionLayer.generate(prompt, model_config)
    │     ├─ ModelRouter.select(model_config) → adapter: OllamaAdapter | OpenAIAdapter
    │     ├─ adapter.complete(prompt, timeout=config.llm_timeout) → LLMResult(text, tokens_in, tokens_out, latency_ms)
    │     └─ emit WebSocket: stage_complete("llm_generation", status, token_counts)
    │     [IF failure → invoke FallbackStrategyEngine]
    │
    ├─ Stage 3: HallucinationDetectionEngine.analyze(llm_response_text, kb_id)
    │     ├─ ClaimExtractor.extract(text) → claims: Claim[]
    │     ├─ FOR each claim:
    │     │     ├─ KnowledgeRetrievalLayer.retrieve(claim.text, kb_id, top_k=5)
    │     │     │     → evidence: Evidence[]
    │     │     └─ ClaimVerifier.verify(claim, evidence[])
    │     │           → VerificationResult(status: supported|unsupported|contradicted, justification)
    │     └─ emit WebSocket: stage_complete("hallucination_detection", claim_count, verification_summary)
    │
    ├─ Stage 4: OutputSafetyFilter.analyze(llm_response_text)
    │     ├─ ToxicityFilter.check(text) → FilterResult(clean|flagged, score)
    │     ├─ HateSpeechFilter.check(text) → FilterResult
    │     ├─ HarmfulInstructionFilter.check(text) → FilterResult
    │     └─ emit WebSocket: stage_complete("safety_filters", triggered_filters[])
    │
    ├─ Stage 5: ConfidenceScoringEngine.compute(verification_results[], safety_results[], risk_score, model_meta)
    │     └─ → ConfidenceScore(value: 0-100, label: high|medium|low, signal_breakdown: {})
    │
    ├─ Stage 6: GuardrailDecisionEngine.decide(confidence_score, safety_results[], policy)
    │     └─ → GuardrailDecision(type: accept|warn|retry|block, reason, triggered_rule)
    │
    ├─ [IF decision == retry] → FallbackStrategyEngine.execute(strategy, ...) → re-enter Stage 2
    │
    └─ Stage 7: Build ExecutionTrace, AuditRecord → persist → return GuardrailResponse
```

### 5.2 Retry Lifecycle

When a retry decision is issued, the Orchestrator:

1. Increments `retry_count` (max: `policy.max_retries`, default 2).
2. Delegates to `FallbackStrategyEngine` which selects and applies the next strategy.
3. Re-enters the pipeline from Stage 2 (LLM generation) with the modified prompt or model.
4. The original trace cycle is preserved; a new trace cycle is appended labeled `Retry Attempt N`.
5. If `retry_count >= max_retries` and the decision is still non-accept, a `Block` with reason `MAX_RETRIES_EXCEEDED` is issued.

---

## 6. Concurrency Model

### Backend

- **ASGI event loop:** FastAPI runs on Uvicorn with asyncio. All I/O-bound operations (HTTP calls to Ollama/OpenAI, database reads/writes, vector store queries) are `async/await`.
- **CPU-bound work isolation:** Claim extraction, PII detection, and embedding generation are CPU-bound. These are dispatched to a `ProcessPoolExecutor` via `asyncio.run_in_executor` to avoid blocking the event loop.
- **Background indexing:** Document indexing jobs are submitted to an `asyncio.Queue` consumed by a dedicated background task coroutine. This decouples indexing from the request path entirely.
- **Per-request isolation:** Each request runs in its own coroutine context. No shared mutable state between requests. The pipeline orchestrator is instantiated fresh per request.
- **WebSocket connections:** Each browser session holds one WebSocket connection. Pipeline stage events are published to a per-request `asyncio.Queue` and consumed by the WebSocket writer coroutine.

### Worker processes (production)

- **Gunicorn + Uvicorn workers:** Multiple worker processes for horizontal CPU parallelism. Each process has its own in-process vector store instance (FAISS). PostgreSQL replaces SQLite in multi-process mode to share request records.
- **Session affinity:** WebSocket connections require session affinity (sticky routing at the proxy layer) in multi-worker deployments.

---

## 7. Failure Recovery Model

| Failure Scenario | Detection | Recovery |
|---|---|---|
| Ollama service down | HTTP connection refused / timeout | Return `LLM_UNAVAILABLE` error; suggest OpenAI fallback in UI. Do not retry indefinitely. |
| OpenAI API key invalid | HTTP 401 from OpenAI | Return `AUTH_ERROR` to client immediately; do not retry. |
| OpenAI API rate limit | HTTP 429 from OpenAI | Retry with exponential backoff up to 2 times; if still 429, return `PROVIDER_RATE_LIMITED`. |
| LLM returns empty response | Empty string / null content | Treat as generation failure; invoke FallbackStrategyEngine. |
| LLM timeout | `asyncio.TimeoutError` after `config.llm_timeout_seconds` | Issue timeout error; record in trace; invoke fallback if retry budget remains. |
| Vector store query failure | Exception from FAISS/Chroma | Log error; mark evidence retrieval as `FAILED`; all claims → `UNSUPPORTED`; continue pipeline. |
| Embedding model failure | Exception from SentenceTransformers | Log error; skip claim verification; note in trace; score from available signals only. |
| Database write failure | SQLAlchemy exception | Log error; attempt one retry; if failed, continue request processing but log audit flush failure separately. Do not block the response on audit persistence. |
| Pipeline crash (unhandled exception) | FastAPI exception handler | Return HTTP 500 with request_id; log full stack trace with request context. |
| Background indexing failure | Exception in indexing coroutine | Mark document status as `FAILED` in database; log error; allow user to retry via UI. |

---

## 8. Observability Strategy

### Structured Logging

- All log entries are structured JSON emitted to stdout.
- Every log line includes: `request_id`, `session_id`, `timestamp_utc`, `level`, `module`, `event`, and relevant metadata.
- Log levels: `DEBUG` (dev only), `INFO` (normal operations), `WARNING` (recoverable anomalies), `ERROR` (failures requiring attention).
- Sensitive fields (prompt text, API keys) are redacted from logs at the logging middleware layer before emission.

### Metrics

- Prometheus-compatible metrics exposed at `/metrics` (Phase 3, but instrumented from Phase 1 with counters/gauges behind a feature flag).
- Key counters: `guardrail_requests_total{decision, model}`, `pipeline_stage_latency_seconds{stage}`, `llm_tokens_total{model, direction}`, `hallucination_detected_total{model}`, `safety_filter_triggered_total{filter}`.

### Tracing

- OpenTelemetry spans wrap each pipeline stage. Trace context propagated via `X-Request-ID` header.
- In MVP: traces are logged as structured JSON. In Phase 3: export to Jaeger or OTLP-compatible collector.

### Health Endpoints

- `GET /health` — returns service health (HTTP 200 if up).
- `GET /health/ready` — readiness check: verifies database connectivity, vector store reachability, and Ollama availability.
- `GET /health/live` — liveness check: returns 200 if the process is alive (no deep checks).

### Analytics Counters

- The `analytics` table is updated atomically after each request completes using database-level upsert operations.
- Dashboard reads from the `analytics` table; it does not aggregate from raw `requests` table at query time.

---

## 9. Performance Strategy

### Latency Budget (Target: ≤ 30 seconds end-to-end for local model)

| Stage | Budget |
|---|---|
| Prompt validation | ≤ 500ms |
| LLM generation (local, Mistral 7B) | ≤ 20s |
| Claim extraction | ≤ 1s |
| Evidence retrieval (FAISS, top-5) | ≤ 200ms |
| Claim verification (per claim, LLM call) | ≤ 2s × claim_count (batched where possible) |
| Safety filtering | ≤ 500ms |
| Confidence scoring + decision | ≤ 100ms |
| Audit persistence | async, non-blocking |

### Optimization Tactics

- **Claim verification batching:** Multiple claims are batched into a single LLM prompt for verification rather than one call per claim, reducing token overhead.
- **Embedding cache:** Frequently queried claim embeddings are cached in an LRU cache (in-process, max 512 entries) keyed on claim text hash.
- **FAISS index pre-loading:** The active knowledge base FAISS index is loaded into memory on first access and held for the duration of the process. Index is reloaded only when the KB is updated.
- **Safety filter parallelism:** The three safety filters run concurrently via `asyncio.gather`.
- **Response streaming (Phase 3):** Token streaming from LLM → UI reduces perceived latency.

---

## 10. Scaling Considerations

### Vertical Scaling (MVP)

- Single-instance deployment on a machine with ≥ 8 GB RAM (required for local LLM model weights).
- FAISS in-process; SQLite for persistence.
- Gunicorn with 2–4 Uvicorn workers (CPU-limited by LLM inference).

### Horizontal Scaling (Phase 3+)

- Replace SQLite with PostgreSQL; replace FAISS (in-process) with ChromaDB (HTTP server) or Qdrant.
- Introduce Redis for WebSocket pub/sub to support cross-worker WebSocket routing.
- Sticky sessions at the proxy for WebSocket connections.
- LLM inference is the primary bottleneck; Ollama does not scale horizontally on a single host. Options: dedicated inference server (vLLM), or route all local inference through a single Ollama sidecar with a queue.

### Large Dataset Handling

- Knowledge bases are chunked at upload time; chunks are stored in the database and indexed incrementally in FAISS/Chroma.
- FAISS indexes are persisted to disk (`.faiss` files) and loaded on startup. Large KBs (>10k chunks) may require approximate nearest neighbor (HNSW or IVF) index types rather than flat search.
- Analytics aggregation is computed incrementally (counter updates per request) rather than on-demand full-table scans.

---

## 11. Background Job Architecture

### Knowledge Base Indexer

```
User uploads document
        │
        ▼
POST /v1/kb/documents → save raw file → insert kb_document record (status=PENDING)
        │
        ▼
IndexDocumentJob submitted to asyncio.Queue
        │
        ▼ (background coroutine)
DocumentChunker.chunk(document) → Chunk[]
        │
        ▼
EmbeddingAdapter.embed(chunks[]) → vectors[]
        │
        ▼
VectorStore.upsert(kb_id, chunk_ids, vectors)
        │
        ▼
Update kb_document.status = READY | FAILED
        │
        ▼
WebSocket push to client: kb_document_status_changed
```

**Failure handling:** If any step fails, the document is marked `FAILED`. The raw file is retained. The user can retry via the UI, which re-enqueues the job.

**Concurrency:** A single indexing worker coroutine processes jobs serially to prevent memory pressure from concurrent large embedding batches. Multiple documents are queued and processed in FIFO order.

---

## 12. Caching Strategy

| Cache Target | Mechanism | Eviction | Rationale |
|---|---|---|---|
| FAISS index per KB | In-process dict keyed on `kb_id` | LRU, max 3 indexes | FAISS index load from disk is slow (~500ms for medium KBs) |
| Claim embeddings | In-process LRU cache, max 512 entries, keyed on `sha256(claim_text)` | LRU | Avoid re-embedding repeated claims across requests |
| Analytics summary | In-process cache, TTL 10s | TTL | Prevent per-request database reads for the dashboard |
| Policy configuration | In-process cache per session_id | Session expiry | Avoid per-stage policy database reads |
| Safety filter model | Loaded once at startup, held in process memory | Never (process lifetime) | Model load is expensive (~2s) |

No distributed cache (Redis) is required in the MVP single-instance deployment.
