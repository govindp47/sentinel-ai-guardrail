# 11_EXECUTION_PLAN.md

# SentinelAI Guardrail — Execution Plan

---

## Overview

This document defines the phased development execution plan from project initialization through production deployment. Each phase is a shippable increment. No phase begins until the previous phase's exit criteria are met.

**Engineering assumptions:**

- Solo developer or small team (1–2 engineers).
- 4–6 focused hours per day available for development.
- Ollama is available on the development machine.
- All Phase 1 deliverables target the free hosting deployment (Fly.io or Render).

**Effort estimates** use the following scale:

- S (Small): ≤ 1 day
- M (Medium): 2–3 days
- L (Large): 4–5 days
- XL (Extra Large): 6–8 days

---

## Phase 1 — MVP Core Pipeline

**Goal:** A working public playground demonstrating the end-to-end guardrail pipeline. Every stage executes, produces visible output, and is free to use with a local model.

**Duration Estimate:** 3–4 weeks

---

### 1.1 Project Scaffold and Infrastructure

**Scope:**

- Initialize monorepo structure (`backend/`, `frontend/`, `sdk/`, `docker/`).
- Set up `pyproject.toml` with all dependencies pinned. Generate `uv.lock`.
- Initialize Alembic. Write `0001_initial_schema.py` migration covering all 10 tables from the schema document.
- Set up pre-commit hooks (Ruff, mypy, ESLint).
- Write `docker-compose.dev.yml` and `docker-compose.yml`.
- Write `Dockerfile.backend` (all 5 stages).
- Create `.env.example`.
- GitHub Actions CI: `lint-backend`, `lint-frontend`, `test-unit` (empty test suite, passes immediately).

**Dependencies:** None.

**Complexity:** M

**Engineering Effort:** 3 days

**Risks:**

- Dependency version conflicts between `sentence-transformers`, `faiss-cpu`, and `detoxify`. Mitigation: pin to tested combination from the start.
- Docker image size unexpectedly large. Mitigation: multi-stage build with model preloading stage verified early.

**Exit Criteria:**

- `docker compose up` starts all services without errors.
- `alembic upgrade head` creates all tables with correct schema.
- `pre-commit run --all-files` passes.
- `pytest tests/` runs (0 tests, 0 failures).

---

### 1.2 Domain Models and Pure Engine Layer

**Scope:**

- Implement all Pydantic domain models: `Claim`, `Evidence`, `ClaimVerificationResult`, `SafetyFilterResult`, `ConfidenceScore`, `GuardrailDecision`, `PipelineContext`, `PolicySnapshot`.
- Implement `InjectionDetector` (all block/flag patterns).
- Implement `PIIDetector` (6 pattern types + masking).
- Implement `PolicyFilter` (restricted category check).
- Implement `RiskScorer` (weighted aggregation).
- Implement `ConfidenceScoringEngine` (4-signal weighted computation).
- Implement `GuardrailDecisionEngine` (priority-ordered rule evaluation).
- Write unit tests for all engines. Target: 95% coverage on domain layer.

**Dependencies:** 1.1 (project scaffold).

**Complexity:** L

**Engineering Effort:** 5 days

**Risks:**

- PII regex patterns produce false positives on technical content (e.g., API keys detected in code snippets). Mitigation: tune pattern specificity with test cases; document known false positive scenarios.
- Decision engine edge cases around threshold boundary values (score == threshold exactly). Mitigation: explicit test cases for boundary conditions.

**Exit Criteria:**

- All domain unit tests pass.
- `mypy src/sentinel/domain/` reports zero errors.
- `pytest tests/unit/domain/` achieves ≥ 95% line coverage.
- `GuardrailDecisionEngine` passes the safety-filter-override test and threshold-boundary tests.

---

### 1.3 Infrastructure Adapters

**Scope:**

- Implement `SQLAlchemy` ORM models for all 10 database tables.
- Implement `RequestRepository`, `SessionRepository`, `KBRepository`, `AnalyticsRepository`, `PolicyRepository`.
- Implement `FAISSStore` (IndexIDMap, add, remove_ids, query, persist, load).
- Implement `SentenceTransformerAdapter` (embed, embed_batch, LRU cache).
- Implement `OllamaAdapter` (complete, health_check, retry with backoff).
- Implement `OpenAIAdapter` (complete, error mapping).
- Implement `DetoxifyClassifier` (load, predict, ProcessPoolExecutor dispatch).
- Implement `TextChunker` (sliding window with sentence boundary detection).
- Implement `LocalFileStorage` (save, delete, sanitize_filename).
- Write integration tests for each adapter.

**Dependencies:** 1.2 (domain models define the interfaces adapters must implement).

**Complexity:** XL

**Engineering Effort:** 7 days

**Risks:**

- FAISS `IndexIDMap.remove_ids` behavior may differ between FAISS versions. Mitigation: integration test for remove + query sequence pinned against `faiss-cpu==1.8.0`.
- detoxify in ProcessPoolExecutor: model weights must be serializable or reloaded in worker process. Mitigation: load model inside the worker function, not before `ProcessPoolExecutor` is created.
- Async SQLAlchemy session lifecycle: forgetting `await session.commit()` after writes. Mitigation: repository base class wraps all mutations in explicit commit.

**Exit Criteria:**

- `pytest tests/integration/db/` and `pytest tests/integration/infrastructure/` pass.
- `pytest tests/migration/` passes (all tables created, indexes verified, constraints enforced).
- FAISS add + remove + query round-trip test passes.
- Embedding adapter returns vectors of correct dimension (384 for MiniLM).

---

### 1.4 Application Layer and Pipeline Orchestrator

**Scope:**

- Implement `ApplicationContainer` (all adapter wiring, `initialize()`, `shutdown()`).
- Implement `GuardrailPipelineOrchestrator` (full stage sequence, short-circuit, retry loop, trace construction).
- Implement `HallucinationDetectionEngine` (`ClaimExtractor`, `ClaimVerifier`).
- Implement `KnowledgeRetrievalLayer` (embed claim → FAISS query → DB chunk lookup → Evidence).
- Implement `OutputSafetyFilter` (detoxify + harmful instruction patterns, asyncio.gather).
- Implement `FallbackStrategyEngine` (all 4 strategies).
- Implement `SubmitPromptUseCase` (orchestrates prompt masking → pipeline → audit persist).
- Implement `AuditService` (construct AuditRecord from PipelineContext → write all DB rows in a single transaction).
- Implement background indexing worker (`IndexDocumentJob`, `kb_indexing_worker` coroutine).
- Write consistency tests (pipeline determinism, score invariants, audit immutability).

**Dependencies:** 1.2, 1.3.

**Complexity:** XL

**Engineering Effort:** 8 days

**Risks:**

- Claim extraction JSON parse failures from the LLM are frequent during development (model not following the JSON-only instruction reliably). Mitigation: implement the regex fallback and the empty-list fallback from day one; test both paths.
- asyncio.gather for safety filter + hallucination detection: uncaught exception in one task cancels the other. Mitigation: wrap each task with `asyncio.shield` or handle individual task exceptions before gather.
- ProcessPoolExecutor and asyncio interaction: calling `run_in_executor` from an async context correctly. Mitigation: use `loop.run_in_executor(process_pool, sync_fn, *args)` pattern; test with a real ProcessPoolExecutor in integration tests.
- Audit transaction rollback: if any part of the multi-table write fails, partial data must not be committed. Mitigation: all audit writes are wrapped in a single `async with session.begin()` block.

**Exit Criteria:**

- `pytest tests/consistency/` passes (determinism, immutability, score invariants).
- A full pipeline execution via Python (not HTTP) produces a `GuardrailResponse` with all fields populated.
- Background indexer processes a test document and updates `kb_documents.status` to `ready`.
- The orchestrator correctly short-circuits on a blocked prompt (no LLM call is made).

---

### 1.5 FastAPI REST API and WebSocket

**Scope:**

- Implement all middleware (CORS, Request ID, Session ID, Logging, API Key Stripping).
- Implement all error handlers (12 exception → HTTP code mappings).
- Implement all 6 router files (`guardrail`, `analytics`, `requests`, `kb`, `policy`, `health`).
- Implement WebSocket handler and `EventBus` (per-request `asyncio.Queue`, pipeline stage → WebSocket push).
- Integrate WebSocket events into `GuardrailPipelineOrchestrator` (emit stage events after each stage).
- Write API integration tests for all critical routes (empty prompt 422, missing session 400, injection → block, PII replay 403, OpenAI without key 400).

**Dependencies:** 1.4.

**Complexity:** L

**Engineering Effort:** 5 days

**Risks:**

- WebSocket race condition: the browser subscribes to `/ws/{request_id}` but the request_id is only known after the HTTP POST returns. The WS connection must be pre-established or the event bus must buffer events. Mitigation: event bus buffers the last 20 events per request_id for 30 seconds; late subscribers receive buffered events immediately on connect.
- Session ID middleware must be tested for malformed UUID handling (no crash, clean 400 response). Mitigation: explicit integration test with 10 invalid session ID formats.

**Exit Criteria:**

- `pytest tests/integration/api/` passes (all 9+ test scenarios).
- `POST /v1/guardrail/submit` with a real local model completes end-to-end and returns all required fields.
- WebSocket events are received by the client during a pipeline run (verified via Playwright test).
- `GET /health/ready` returns 200 with `ollama: "ok"` when Ollama is running.

---

### 1.6 React Frontend — Playground

**Scope:**

- Initialize Vite + TypeScript + React project.
- Configure Tailwind CSS with custom color tokens.
- Set up React Router v6 with all 6 routes.
- Implement Zustand store (all 5 slices).
- Implement all shared components (`Tooltip`, `StatusBadge`, `EmptyState`, `LoadingSpinner`, `ErrorBoundary`, `PrivacyNotice`).
- Implement Playground page: `PromptInput`, `ModelSelector`, `ApiKeyField`, `KbSelector`, `GuardrailToggles`, `ResponsePanel`, `ConfidenceBadge`, `DecisionLabel`, `PipelineProgressIndicator`.
- Implement `GuardrailAnalysisPanel`: `ClaimsList`, `EvidenceList`, `VerificationResults`, `SignalBreakdownChart`.
- Implement `ExecutionTraceViewer`: `TraceStageRow`, `TraceStageDetail`.
- Implement `usePipelineSubmit` and `usePipelineProgress` hooks.
- Apply all `data-testid` attributes required for E2E tests.
- Add all `TERM_DEFINITIONS` tooltips.

**Dependencies:** 1.5 (API must be available for integration).

**Complexity:** XL

**Engineering Effort:** 8 days

**Risks:**

- WebSocket reconnection complexity: if the pipeline completes before the WebSocket connects (fast Ollama), all events are missed. Mitigation: event bus buffering (implemented in 1.5); WS client replays buffered events on connect.
- Claim-to-evidence linking (clicking a claim filters evidence) requires careful state coordination between `ClaimsList` and `EvidenceList`. Mitigation: `selectedClaimIndex` in the Zustand playground slice drives both components.
- Confidence badge color accessibility: green/yellow/red must pass contrast ratio check against the dark background. Mitigation: validate color pairs in the design system definition; add text labels regardless.

**Exit Criteria:**

- A first-time user can submit a prompt and receive a response with confidence badge, decision label, and analysis panel populated.
- The Execution Trace Viewer expands/collapses per stage.
- Blocked prompt shows the block state (no response text, red alert with reason).
- API key field clears after submission.
- All `TERM_DEFINITIONS` tooltips are present and display on hover.
- `npm run type-check` reports zero errors.

---

### 1.7 Knowledge Base Management UI

**Scope:**

- Implement `KnowledgeBasePage`: `DocumentUploader`, `DocumentList`, `DocumentStatusBadge`, `ChunkingPreview`.
- Connect to `/v1/kb/documents` API endpoints.
- Implement KB selector in Playground (`KbSelector` dropdown fed from `/v1/kb/documents`).
- WebSocket event handling for `kb_status` updates (live status badge updates during indexing).

**Dependencies:** 1.6 (frontend scaffold in place).

**Complexity:** M

**Engineering Effort:** 3 days

**Risks:**

- Large file upload UX: progress indication for the multipart upload (not just indexing). Mitigation: use `XMLHttpRequest` with `onprogress` event (Axios supports this); show upload progress bar separate from indexing progress.

**Exit Criteria:**

- User can upload a TXT or PDF document and see it transition from Pending → Indexing → Ready.
- User can submit a guardrail request with the indexed KB selected.
- Evidence retrieved from the KB appears in the Guardrail Analysis Panel.

---

### 1.8 Initial Deployment and Public Access

**Scope:**

- Configure Fly.io (or Render) deployment.
- Write production `docker-compose.yml`.
- Set up GitHub Actions `deploy.yml` workflow.
- Configure Caddy with production domain and TLS.
- Write `scripts/backup.py` and configure daily cron.
- Write `scripts/validate_restore.py`.
- Add privacy notice footer to the playground.
- Perform manual smoke test of all Phase 1 features on the production deployment.

**Dependencies:** 1.1–1.7.

**Complexity:** M

**Engineering Effort:** 3 days

**Risks:**

- Free hosting RAM constraints (512MB on Render free tier): Python process + SentenceTransformer (~500MB) + detoxify (~250MB) exceeds 512MB. Mitigation: use Fly.io (1GB RAM available) or reduce model size (use `paraphrase-MiniLM-L3-v2` at 60MB instead of `all-MiniLM-L6-v2` at 91MB). Ollama model (4GB+) requires a separate paid instance on most platforms.
- Ollama unavailability on free hosting: see Render constraint in deployment document. Mitigation: UI clearly communicates "local model unavailable; use OpenAI" in the playground banner.
- Cold start latency > 90s on first request: user sees blank loading screen. Mitigation: warming-up banner implemented in 1.5; polling `/health/ready`.

**Exit Criteria:**

- `https://sentinel.example.com` is publicly accessible.
- HTTPS is enforced (HTTP → HTTPS redirect).
- A guardrail request completes end-to-end on the production deployment.
- `GET /health/ready` returns 200.
- Privacy notice is visible in the playground footer.
- Backup script runs and produces a valid backup with passing integrity verification.

**Phase 1 Total Estimate:** 42 days (~8–9 weeks at 5 hours/day solo)

---

## Phase 2 — Analytics, Exploration, and Developer Surface

**Goal:** Add the Analytics Dashboard, Request Explorer, Policy Configuration, Fallback Strategy Engine, and the developer SDK. Make the system observable and configurable.

**Duration Estimate:** 3–4 weeks

---

### 2.1 Analytics Dashboard

**Scope:**

- Implement `AnalyticsDashboardPage` with all 5 charts using Recharts.
- Implement `GET /v1/analytics` backend endpoint with time range filtering.
- Implement `SummaryMetricsRow`, `HallucinationRateChart`, `DecisionDistributionChart`, `ConfidenceHistogram`, `LatencyLineChart`, `TokenUsageChart`.
- Empty state with instructional copy.
- Time range selector (All Time / Last 100 / Last 24h).

**Dependencies:** Phase 1 complete.

**Complexity:** M

**Engineering Effort:** 4 days

**Exit Criteria:**

- Dashboard shows data after 5+ requests submitted in Playground.
- Charts render correctly with single-model data (no comparison column shown when only one model used).
- Empty state shows with instructional copy when no requests exist.
- Time range filter changes chart data correctly.

---

### 2.2 Request Explorer and Audit Detail

**Scope:**

- Implement `RequestExplorerPage` (list + detail split-panel).
- Implement `RequestList`, `RequestListItem`, `RequestDetailPanel`, `ReplayButton`.
- Implement `GET /v1/requests` (paginated, filtered) and `GET /v1/requests/{id}` backend endpoints.
- Implement `POST /v1/requests/{id}/replay` (creates new request from stored masked prompt).
- Implement deep-link: `/requests/{id}` pre-selects the request.
- PII-masked records: replay button disabled; tooltip explains why.

**Dependencies:** 2.1 (analytics counters confirm request data is flowing).

**Complexity:** M

**Engineering Effort:** 4 days

**Exit Criteria:**

- User can search for a request by ID and view the full audit record.
- Execution trace in the detail view is identical to the trace shown in the Playground.
- Replay creates a new request and navigates to Playground with the result.
- PII-masked records disable the replay button.
- Filter by decision type returns only requests with that decision.

---

### 2.3 Full Fallback Strategy Engine

**Scope:**

- Complete `FallbackStrategyEngine` with all 4 strategies (Phase 1 may have partial implementation).
- Implement retry loop tracking (`strategies_attempted` set on `PipelineContext`).
- Implement `MAX_RETRIES_EXCEEDED` block decision.
- Add retry trace blocks to the `ExecutionTraceViewer` (labeled "Retry Attempt N").
- Integration tests: retry exhaustion → block, RAG augmentation skipped when no KB, alternate model switch.

**Dependencies:** 2.2.

**Complexity:** M

**Engineering Effort:** 3 days

**Exit Criteria:**

- Configuring `max_retries=2` with a low confidence threshold causes the pipeline to attempt 2 retries before blocking.
- The trace viewer shows 3 trace blocks (original + 2 retries) when max retries are exhausted.
- RAG strategy is skipped gracefully when no KB is active.

---

### 2.4 Policy Configuration UI and Backend

**Scope:**

- Implement `PolicyConfigPage` with `ThresholdSliders`, `CategoryToggles`, `FallbackPriorityList` (drag-and-drop via @dnd-kit), `ModuleToggles`.
- Implement `GET /v1/policy` and `PUT /v1/policy` backend endpoints.
- Implement `PolicySnapshot` creation and session association.
- Unsaved changes indicator and save confirmation.
- Apply saved policy to pipeline: `SubmitPromptUseCase` reads current session policy before pipeline execution.
- Validation: `block < warn < accept` enforced on save.

**Dependencies:** 2.3.

**Complexity:** M

**Engineering Effort:** 4 days

**Exit Criteria:**

- Changing the accept threshold to 95 causes previously-accepted responses to be warned.
- Changing the accept threshold to 0 causes all responses to be accepted.
- The drag-and-drop fallback priority list reorders correctly and persists after save.
- Validation error is shown when `warn >= accept` threshold values are configured.
- Policy changes take effect on the next request (not retroactively).

---

### 2.5 Vector Search Preview in KB Management

**Scope:**

- Implement `VectorSearchPreview` component.
- Implement `POST /v1/kb/search` endpoint.
- Add model comparison toggle to Analytics Dashboard.
- Add claim-to-evidence linking (clicking a claim in analysis panel highlights its evidence).

**Dependencies:** 2.4.

**Complexity:** S

**Engineering Effort:** 2 days

**Exit Criteria:**

- User can enter a test query in KB Management and see top-5 matching chunks with relevance scores.
- Clicking a claim in the Analysis Panel filters the evidence list to that claim's evidence only.

---

### 2.6 Developer SDK (Python)

**Scope:**

- Implement `sentinel_sdk/client.py` (sync `SentinelClient`).
- Implement `sentinel_sdk/async_client.py` (`AsyncSentinelClient`).
- Implement `sentinel_sdk/models.py` (typed response models matching API schema).
- Implement `sentinel_sdk/exceptions.py` (error hierarchy).
- Write SDK README with 5 usage examples.
- Write SDK unit tests (mock HTTP; verify error mapping).
- Package as installable Python package (`pip install sentinel-sdk`).

**Dependencies:** 2.5 (API surface is stable).

**Complexity:** M

**Engineering Effort:** 3 days

**Exit Criteria:**

- `pip install -e sdk/python` installs without errors.
- A developer can submit a prompt via the SDK in 5 lines of Python.
- All SDK error types are correctly raised for corresponding HTTP error codes.
- SDK README example is copy-pasteable and works against the running API.

---

### 2.7 Phase 2 Testing and Deployment

**Scope:**

- Add integration tests for all new API endpoints.
- Add E2E tests for Analytics Dashboard, Request Explorer, Policy Config, KB vector search.
- Add failure injection tests for retry exhaustion and RAG strategy skip.
- Update `deploy.yml` to include Phase 2 features.
- Perform production deployment.

**Dependencies:** 2.1–2.6.

**Complexity:** M

**Engineering Effort:** 3 days

**Exit Criteria:**

- All Phase 2 tests pass in CI.
- Production deployment includes Phase 2 features.
- SDK README link is added to the playground API docs screen.

**Phase 2 Total Estimate:** 23 days (~5 weeks at 5 hours/day solo)

---

## Phase 3 — Advanced Capabilities and Production Hardening

**Goal:** Add configurable API-level policy, Prometheus metrics, multi-KB support, export, and session cleanup. Harden for sustained production use.

**Duration Estimate:** 3–4 weeks

---

### 3.1 API-Level Policy Override

**Scope:**

- Extend `/v1/guardrail/submit` to accept `policy_overrides` in the request body.
- `policy_overrides` merges with the session policy (per-request overrides).
- Document in API reference.
- Add SDK support for `policy_overrides` parameter.

**Complexity:** S | **Effort:** 2 days

---

### 3.2 Prometheus Metrics Endpoint

**Scope:**

- Activate `/metrics` endpoint (gated by `ENABLE_METRICS=true` env var).
- Implement all counters/gauges/histograms defined in the monitoring section.
- Verify Prometheus scrape config works with the endpoint.
- Write Grafana dashboard JSON for the 5 key panels.

**Complexity:** M | **Effort:** 3 days

---

### 3.3 Export Audit Records

**Scope:**

- Add `GET /v1/requests/export?format=csv|json` endpoint.
- Export all requests for the session (or filtered by date range).
- Frontend: "Export" button in Request Explorer.
- PII-masked fields are exported as masked.

**Complexity:** S | **Effort:** 2 days

---

### 3.4 Session Cleanup Background Job

**Scope:**

- Implement `session_cleanup_worker` coroutine (runs daily).
- Deletes sessions older than `SESSION_RETENTION_DAYS` (default: 7).
- Cascades to all session-scoped data (requests, KB docs, files).
- Logs cleanup statistics (sessions deleted, files removed, bytes freed).

**Complexity:** S | **Effort:** 2 days

---

### 3.5 S3 Backup Upload

**Scope:**

- Add S3 upload step to `scripts/backup.py` (activated by `S3_BACKUP_BUCKET` env var).
- Add boto3 dependency.
- Verify backup round-trip: upload → download → verify.

**Complexity:** S | **Effort:** 1 day

---

### 3.6 PostgreSQL Migration and Multi-Worker Deployment

**Scope:**

- Test and validate SQLite → PostgreSQL migration procedure (export + import scripts).
- Update `docker-compose.yml` to optionally include a PostgreSQL service.
- Verify `alembic upgrade head` works against PostgreSQL.
- Update Gunicorn worker count to 4 (requires PostgreSQL; SQLite does not support concurrent writes from 4 workers).
- Switch FAISS to ChromaDB HTTP mode for multi-worker deployments (optional; gated by `VECTOR_STORE_BACKEND=chroma` env var).

**Complexity:** L | **Effort:** 5 days

---

### 3.7 Pre-loaded Demo Knowledge Bases

**Scope:**

- Create 2–3 pre-loaded KB options: general facts (Wikipedia excerpts), scientific claims, news events.
- KB documents are bundled with the application as static files.
- The KB Management UI offers "Load Demo KB" buttons.
- These KBs are session-independent (shared, read-only indexes).

**Complexity:** M | **Effort:** 3 days

---

### 3.8 Human Review Escalation Flag

**Scope:**

- Add `escalated_for_review` boolean column to `requests` table (migration).
- When all retry strategies are exhausted and the decision is `block`, set `escalated_for_review = true`.
- Request Explorer: filter by "Needs Review"; escalated requests are visually highlighted.
- `GET /v1/requests?needs_review=true` filter.

**Complexity:** S | **Effort:** 2 days

---

### 3.9 Phase 3 Testing and Deployment

**Scope:**

- Integration tests for all new endpoints.
- PostgreSQL-specific migration tests.
- Load test with Locust against Phase 3 deployment.
- Production deployment with Phase 3 features.

**Complexity:** M | **Effort:** 3 days

**Phase 3 Total Estimate:** 23 days (~5 weeks at 5 hours/day solo)

---

## Summary Timeline

| Phase | Features | Duration | Cumulative |
|---|---|---|---|
| Phase 1 | Core pipeline, Playground, KB Management, Deployment | 8–9 weeks | 8–9 weeks |
| Phase 2 | Analytics, Explorer, Policy Config, Fallback Engine, SDK | 4–5 weeks | 13–14 weeks |
| Phase 3 | API policy, Metrics, Export, PostgreSQL, Demo KBs | 4–5 weeks | 17–19 weeks |

---

## Risk Register

| Risk | Probability | Impact | Mitigation | Owner |
|---|---|---|---|---|
| Local LLM unavailable on free hosting | High | High | Document OpenAI fallback; make UI graceful when Ollama is absent | Platform setup |
| detoxify + sentence-transformers RAM > hosting limit | Medium | High | Profile memory usage early; switch to smaller models if needed | 1.1 scaffold |
| Claim extraction produces inconsistent JSON | High | Medium | JSON fallback + empty-list fallback implemented from day one | 1.4 orchestrator |
| FAISS index corruption on abnormal shutdown | Low | High | WAL-mode SQLite and FAISS persist are atomic per-operation; corruption detected by validate_restore | 1.3 adapters |
| Ollama cold start latency > 90s | Medium | Medium | Warming-up UI banner; pre-pull model in Dockerfile | 1.8 deployment |
| Frontend bundle size bloat from Recharts + d3 | Low | Low | Vite tree-shaking; code-split analytics dashboard route | 2.1 analytics |
| Session ID enumeration by attacker | Medium | Low | HTTPS enforced; session data is low-sensitivity; rate limiting limits enumeration speed | Security |
| OpenAI API key logged accidentally | Low | High | structlog processor strips all key-matching fields; tested explicitly | 1.5 API layer |
| Migration downgrade destroys data | Low | High | All migrations are additive-only; downgrade functions are no-ops for additive migrations | Migration rules |
| Phase 1 scope creep from UI polish | High | Medium | Implement functional UI first; defer visual polish to post-Phase 1 | Scope discipline |

---

## Technical Debt Register

Intentional technical shortcuts in the MVP that require future attention:

| Item | Introduced In | Remediation Phase | Description |
|---|---|---|---|
| SQLite WAL concurrent write limitation | Phase 1 | Phase 3 | Blocks multi-worker deployment; mitigated by single-worker MVP |
| FAISS in-process limits multi-worker FAISS sharing | Phase 1 | Phase 3 | Each worker has its own index copy; consistent only for reads |
| No response-level PII scanning | Phase 1 | Phase 3 | LLM response may contain PII from user's own KB documents |
| Harmful instruction filter is regex-only | Phase 1 | Phase 3 | Low recall vs. a fine-tuned classifier; supplement with LLM-based check |
| Claim extraction uses generative LLM | Phase 1 | Phase 3 | A fine-tuned NER model would be faster and more deterministic |
| Session data is never persisted cross-session | Phase 1 | Phase 3 | Users lose request history on tab close; requires auth to fix |
| Analytics counters are session-scoped only | Phase 1 | Phase 3 | No cross-session aggregate view; limits long-term trend analysis |
| `strategies_attempted` not persisted between app restarts | Phase 1 | Phase 2 | If the app restarts mid-retry, the retry state is lost; retry counter resets |
| No streaming LLM response to UI | Phase 1 | Phase 3 | User waits for full response before seeing any output |
| WebSocket event bus is in-process only | Phase 1 | Phase 3 | In multi-worker deployment, WS event from worker A not visible to worker B's WebSocket handler |

---

## Performance Optimization Checklist

To be completed before each phase's production deployment:

- [ ] Profile memory usage of the running container under load (`docker stats`)
- [ ] Verify FAISS query latency is < 50ms P95 for the current KB size
- [ ] Verify embedding adapter LRU cache hit rate is > 50% in production logs
- [ ] Verify analytics counter UPSERT does not cause write contention (check SQLite WAL file size)
- [ ] Run `pytest tests/performance/ -m performance` and verify all benchmarks pass
- [ ] Verify Gunicorn worker count is appropriate for available RAM (1 worker per ~1.5GB RAM)
- [ ] Verify Caddy is serving static assets (frontend) directly (not proxied to the app)
- [ ] Verify LLM response token count is within budget (tokens_out ≤ 1024 in audit records)
- [ ] Check for any blocking I/O calls in async code paths (`asyncio.sleep(0)` yielding is not enough)
- [ ] Verify ProcessPoolExecutor worker count matches available CPU cores (default: 2)

---

## Concurrency Safety Checklist

To be verified during code review before each phase merge:

- [ ] All FAISS index write operations are protected by a per-KB `asyncio.Lock`
- [ ] Analytics counter updates use UPSERT (not read-modify-write) to avoid lost updates
- [ ] The indexing worker is a single serial coroutine (no parallel indexing jobs)
- [ ] WebSocket event queues are per-request (no shared queue across requests)
- [ ] `PipelineContext` is instantiated fresh per request (no shared mutable state)
- [ ] LRU caches are thread-safe (Python's `functools.lru_cache` is not async-safe; use `cachetools.LRUCache` with an `asyncio.Lock`)
- [ ] `ProcessPoolExecutor` tasks are stateless (no shared mutable state in worker functions)
- [ ] Database sessions are not shared between concurrent requests (each request gets its own session from the session factory)
- [ ] The FAISS index cache (in-memory dict of loaded indexes) is protected by a read lock when accessed from multiple coroutines

---

## Long-Term Evolution Strategy

### 12-Month Horizon

1. **Streaming responses (Month 4):** Token streaming from Ollama/OpenAI → WebSocket → UI. Guardrail results appended after streaming completes. Reduces perceived latency from 15–20s to time-to-first-token (~500ms).

2. **User accounts (Month 5):** JWT authentication, persistent request history, cross-session KB persistence. Session-scoped data model transitions to user-scoped.

3. **Claim extraction upgrade (Month 6):** Replace generative claim extraction with a fine-tuned NER model (spaCy or HuggingFace token classification). Faster, more deterministic, lower token cost.

4. **Multi-model parallel execution (Month 7):** Submit the same prompt to Ollama and OpenAI simultaneously; display side-by-side results. Enables direct hallucination rate comparison.

5. **Webhook support (Month 8):** Push guardrail decisions and audit events to a user-configured HTTPS endpoint. Enables integration with external systems (Slack alerts, incident management).

6. **Policy templates (Month 9):** Pre-built policy configurations for common domains (medical Q&A, legal review, customer support). Selectable in the Policy Configuration UI.

7. **Hallucination trend analysis (Month 10):** Per-topic hallucination pattern detection across sessions. Requires topic classification of prompts + long-term analytics storage.

8. **SDK language expansion (Month 12):** JavaScript/TypeScript SDK published to npm. Enables Node.js backend integrations.

### Architectural Evolution Triggers

| Trigger | Architectural Response |
|---|---|
| > 100 concurrent users | Migrate SQLite → PostgreSQL; add Redis for WebSocket pub/sub; horizontal Gunicorn scaling |
| > 1M KB chunks | Migrate FAISS flat search → HNSW index; evaluate Qdrant for production vector DB |
| > 10 requests/second sustained | Add a request queue (ARQ/Celery) to decouple HTTP response from pipeline execution |
| Regulatory compliance requirement | Add AES-256-GCM encryption at rest; implement data retention policies; GDPR deletion endpoints |
| LLM provider diversification | Abstract LLM adapter further; add Anthropic Claude and Mistral API adapters alongside Ollama/OpenAI |
