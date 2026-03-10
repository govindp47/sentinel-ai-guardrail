# 02_TECH_DECISIONS.md

# SentinelAI Guardrail — Technology Decisions

---

## Decision Index

| # | Decision Area | Selected |
|---|---|---|
| TD-01 | Primary Backend Language | Python 3.12 |
| TD-02 | Backend Web Framework | FastAPI |
| TD-03 | Frontend Language & Framework | TypeScript + React (Vite) |
| TD-04 | Architecture Pattern | Clean Architecture + Pipeline Pattern |
| TD-05 | Dependency Injection | Manual constructor injection via container |
| TD-06 | Primary Database | SQLite (MVP) / PostgreSQL (production) |
| TD-07 | ORM / Query Layer | SQLAlchemy 2.x (async) + Alembic |
| TD-08 | Vector Store | FAISS (MVP) / ChromaDB (scale) |
| TD-09 | Embedding Model | sentence-transformers (all-MiniLM-L6-v2 or BGE-small) |
| TD-10 | Local LLM Runtime | Ollama |
| TD-11 | Serialization | Pydantic v2 |
| TD-12 | Background Processing | asyncio native task queue |
| TD-13 | Real-Time Communication | WebSocket (FastAPI native) |
| TD-14 | Reverse Proxy / Gateway | Caddy |
| TD-15 | Logging Framework | structlog |
| TD-16 | Monitoring Strategy | Prometheus + Grafana (Phase 3) |
| TD-17 | CI/CD | GitHub Actions |
| TD-18 | Code Quality | Ruff + mypy + pre-commit |
| TD-19 | Testing Framework | pytest + pytest-asyncio + Playwright |
| TD-20 | Containerization | Docker + Docker Compose |
| TD-21 | Safety Classification | detoxify (local model) |
| TD-22 | Frontend State Management | Zustand |

---

## TD-01 — Primary Backend Language: Python 3.12

**Selected:** Python 3.12

**Alternatives Considered:**

- Node.js (TypeScript): Strong async runtime; however, the ML/AI ecosystem (SentenceTransformers, FAISS, detoxify, Ollama clients) is Python-native. Using Node.js would require spawning Python subprocesses for AI components, introducing IPC overhead and deployment complexity.
- Go: Excellent performance and concurrency model; however, lacks mature ML library bindings. FAISS does not have a production-grade Go client. Custom inference integration would require CGo or subprocess management.
- Rust: Maximum performance, but zero AI/ML library support without FFI. Untenable for a pipeline that depends on Python-native AI tooling.

**Trade-offs:**

- Python is slower than Go/Rust for CPU-bound work, but the primary latency source is LLM inference (seconds), not Python overhead (milliseconds). This trade-off is immaterial to UX.
- Python's GIL means true thread-level parallelism requires multiprocessing. Addressed by using `ProcessPoolExecutor` for CPU-bound stages and `asyncio` for I/O-bound stages.
- Python 3.12 specifically: significant performance improvements over 3.10/3.11 (per-interpreter GIL groundwork, faster startup, optimized bytecode). Minimum version enforced via `pyproject.toml`.

**Justification:** The AI/ML ecosystem gravity is decisive. Every core dependency (SentenceTransformers, FAISS, detoxify, Ollama Python client, OpenAI SDK) is Python-native. Python 3.12 with asyncio provides adequate concurrency for the I/O-bound pipeline, and subprocess isolation handles CPU-bound AI work.

---

## TD-02 — Backend Web Framework: FastAPI

**Selected:** FastAPI 0.115+

**Alternatives Considered:**

- Django REST Framework: Mature but heavyweight. ORM coupling is opinionated, and async support (via ASGI) is a late addition. Sync-first design adds friction for async pipeline operations.
- Flask + Quart: Flask is sync-first; Quart adds async but lacks automatic schema generation, dependency injection, and OpenAPI support out of the box.
- Litestar: Strong async-first framework with comparable features to FastAPI. Smaller community and fewer third-party integrations than FastAPI.
- Starlette (raw): FastAPI is built on Starlette; using raw Starlette saves one dependency layer but requires manually implementing what FastAPI provides (schema validation, OpenAPI generation, dependency injection).

**Trade-offs:**

- FastAPI's automatic OpenAPI/JSON Schema generation from Pydantic models produces the developer API documentation surface at zero additional cost.
- FastAPI's dependency injection system (`Depends`) is used for session management, policy resolution, and repository injection.
- FastAPI does not enforce a project structure, so Clean Architecture boundaries must be enforced by team convention and linting rules.

**Justification:** FastAPI is the dominant async Python web framework for API-first services. Its Pydantic integration, automatic OpenAPI docs, and native WebSocket support cover all three surfaces required (REST API, WebSocket progress, API docs) without additional libraries.

---

## TD-03 — Frontend Language & Framework: TypeScript + React (Vite)

**Selected:** TypeScript 5.x + React 18 + Vite 5

**Alternatives Considered:**

- Next.js: Server-side rendering adds complexity without benefit for a client-only playground. SSR would require careful hydration handling for interactive pipeline components.
- Vue 3: Comparable capability to React. React is selected for broader ecosystem familiarity and the availability of component libraries (shadcn/ui, Radix UI) that accelerate the complex UI requirements (trace viewer, confidence charts, drag-and-drop policy config).
- Svelte/SvelteKit: Excellent for small apps; ecosystem for data visualization (Recharts, Victory) is less mature than React's.
- Vanilla TS + Web Components: Maximum control but requires building all UI primitives from scratch. The complexity of the analytics dashboard and trace viewer makes this impractical within scope.

**Trade-offs:**

- Vite provides near-instant hot module replacement in development, critical for rapid iteration on complex UI panels.
- React 18's concurrent features are not required for MVP but allow incremental adoption of `useTransition` for pipeline result rendering in the future.
- TypeScript adds upfront type definition cost but eliminates a class of runtime errors, particularly important for the complex nested state of pipeline results.

**Justification:** React + TypeScript + Vite is the industry standard for complex interactive SPAs. The rich ecosystem (Recharts for analytics, TanStack Query for data fetching, Zustand for state, Radix UI for accessible primitives) directly addresses the component complexity of this product.

---

## TD-04 — Architecture Pattern: Clean Architecture + Pipeline Pattern

**Selected:** Clean Architecture (layered) with an explicit Pipeline Pattern for the guardrail execution.

**Alternatives Considered:**

- Hexagonal Architecture (Ports and Adapters): Conceptually equivalent to Clean Architecture; the naming is different but the dependency inversion rule is identical. Clean Architecture terminology (Use Cases, Entities) maps more naturally to the domain language of this system.
- Service Layer (flat): Simpler to implement initially but results in business logic leaking into infrastructure adapters as the system grows. The guardrail pipeline stages have non-trivial business rules that must be isolated from LLM provider specifics.
- Microservices: Each pipeline stage as a separate service. Introduces network latency (50–100ms per stage) across ~7 stages, adding 350–700ms to pipeline latency before any LLM call. Operationally complex for a single-developer MVP. Monolith-first is correct here.
- CQRS + Event Sourcing: Adds significant complexity without clear benefit at MVP scale. The audit trail requirement is fulfilled by a simpler append-only audit log model.

**Pipeline Pattern specifics:**

- The `GuardrailPipelineOrchestrator` executes stages as a sequential chain.
- Each stage is a class implementing a `PipelineStage` protocol with a standard `execute(context: PipelineContext) -> StageResult` interface.
- `PipelineContext` is a mutable data class passed through all stages; each stage reads its inputs from the context and writes its outputs back to it. This avoids complex parameter threading.
- Short-circuit termination: If any stage returns a `BLOCK` terminal result, the orchestrator halts execution and builds the final response from the accumulated context.

**Justification:** The pipeline pattern is the natural representation of the sequential, composable guardrail stages described in the PRD. Clean Architecture ensures that swapping LLM providers, vector stores, or safety classifiers (all likely to evolve) does not require changes to the domain logic.

---

## TD-05 — Dependency Injection: Manual Constructor Injection via Container

**Selected:** Manual dependency injection via a lightweight application container class.

**Alternatives Considered:**

- `dependency-injector` (Python library): Feature-complete IoC container with declarative wiring. Adds a non-trivial learning curve and configuration overhead. Appropriate for larger teams.
- FastAPI `Depends()` for everything: Works well for HTTP-layer dependencies (database sessions, current policy) but becomes awkward for injecting deep domain dependencies (e.g., embedding adapter into the hallucination engine into the orchestrator).
- `punq` or `lagom`: Lightweight IoC containers. Viable alternatives, but add a dependency for functionality achievable with a simple container class.

**Implementation:**

```python
class ApplicationContainer:
    def __init__(self, config: AppConfig):
        # Infrastructure
        self.db_session_factory = create_session_factory(config.database_url)
        self.vector_store = FAISSVectorStore(config.faiss_index_dir)
        self.embedding_adapter = SentenceTransformerAdapter(config.embedding_model)
        self.ollama_adapter = OllamaAdapter(config.ollama_base_url)

        # Domain engines (depend on infrastructure via interfaces)
        self.knowledge_retrieval = KnowledgeRetrievalLayer(
            self.vector_store, self.embedding_adapter
        )
        self.hallucination_engine = HallucinationDetectionEngine(
            self.knowledge_retrieval
        )
        self.orchestrator = GuardrailPipelineOrchestrator(
            llm_execution=LLMExecutionLayer(self.ollama_adapter),
            hallucination_engine=self.hallucination_engine,
            # ... etc
        )
```

FastAPI's `Depends()` is used at the router layer to inject the container (singleton, created at startup) into route handlers.

**Justification:** Manual injection provides full control and zero magic. For a codebase of this size (single repo, small team), a purpose-built container class is more transparent and debuggable than a framework IoC container.

---

## TD-06 — Primary Database: SQLite (MVP) / PostgreSQL (Production)

**Selected:** SQLite via SQLAlchemy async (aiosqlite driver) for MVP. PostgreSQL via asyncpg for production deployments.

**Alternatives Considered:**

- PostgreSQL from day one: Correct long-term choice but adds operational complexity to the free hosting MVP deployment (requires a PostgreSQL server process or managed service). Free hosting tiers on Render/Railway include PostgreSQL, so this transition cost is low.
- MongoDB: Document model is flexible but the relational structure of requests, claims, evidence, and audit records benefits from foreign key integrity enforcement. A document DB would require application-level join logic.
- DuckDB: Excellent for analytical queries, but lacks row-level transaction support needed for request audit writes. Would require a separate OLTP database alongside it.

**Trade-offs:**

- SQLite does not support concurrent writes from multiple processes. This is acceptable for single-worker MVP but requires migration to PostgreSQL before adding Gunicorn workers.
- The SQLAlchemy abstraction layer means the migration from SQLite to PostgreSQL requires only a connection string change and driver swap, not query rewrites (avoiding SQLite-specific SQL constructs).

**Migration path trigger:** Switch to PostgreSQL when any of these conditions are met: (1) multiple Gunicorn workers, (2) persistent cross-session storage requirement, (3) concurrent user load causes write contention.

**Justification:** SQLite's zero-configuration deployment is critical for the free hosting MVP target. The SQLAlchemy abstraction ensures the PostgreSQL upgrade path is a configuration change, not a refactor.

---

## TD-07 — ORM / Query Layer: SQLAlchemy 2.x (async) + Alembic

**Selected:** SQLAlchemy 2.x with async session support (`AsyncSession`) + Alembic for migrations.

**Alternatives Considered:**

- Tortoise ORM: Async-first, Django-ORM-like API. Less battle-tested than SQLAlchemy for complex relationships. Alembic integration requires a bridge library.
- Databases (encode/databases): Lightweight async query library. No ORM; all queries are raw SQL. Acceptable for simple schemas but adds friction for relationship navigation in audit queries.
- Piccolo ORM: Modern async ORM with built-in migrations. Smaller community and ecosystem than SQLAlchemy.
- Raw SQL with aiosqlite: Maximum control but requires manual migration management and relationship handling.

**Trade-offs:**

- SQLAlchemy 2.x async mode requires careful session lifecycle management (no implicit session state). Sessions must be explicitly committed and closed.
- Alembic auto-generate creates migration scripts from model definitions, but these require human review before applying — documented in the migration workflow.

**Justification:** SQLAlchemy is the most mature Python ORM with the broadest database driver support (critical for the SQLite→PostgreSQL transition) and the most comprehensive tooling ecosystem. Alembic provides version-controlled, reviewable migration scripts.

---

## TD-08 — Vector Store: FAISS (MVP) / ChromaDB (Scale)

**Selected:** FAISS (in-process, CPU mode) for MVP.

**Alternatives Considered:**

- ChromaDB: HTTP server mode supports multi-process access; embedding generation is optionally delegated to the server. Slightly higher operational complexity (separate process) than FAISS.
- Qdrant: Production-grade vector database with filtering, payload storage, and a native Python client. Excellent choice for Phase 3 but introduces an additional containerized service dependency.
- pgvector (PostgreSQL extension): Keeps all data in one database. Simplifies operations but limits vector search to PostgreSQL deployments (incompatible with SQLite MVP).
- Pinecone (managed): Eliminates operational burden but introduces cost and external dependency. Incompatible with the "no API cost required" product goal.
- Weaviate: Feature-rich but heavyweight (JVM + several GB RAM) for an MVP on free hosting.

**FAISS specifics:**

- Index type: `IndexFlatL2` for MVP (exact search, no approximation error). Switch to `IndexHNSWFlat` when KB size exceeds ~50k chunks.
- Persistence: Index serialized to `{index_dir}/{kb_id}.faiss`. Chunk metadata (text, document reference, chunk index) stored in the SQL database, keyed by the FAISS internal ID (a sequential integer).
- FAISS ID → Chunk ID mapping stored in a separate `{kb_id}_id_map.json` file alongside the index.

**Scale trigger:** Switch to ChromaDB or Qdrant when: (1) multi-process deployment is required, (2) KB size exceeds 100k chunks (FAISS flat search latency degrades), or (3) cross-session persistent KB sharing is required.

**Justification:** FAISS requires zero additional services, has no memory overhead beyond the index itself, and provides microsecond query latency for the expected MVP KB sizes (hundreds to low thousands of chunks). It is the correct zero-dependency choice for the free hosting deployment target.

---

## TD-09 — Embedding Model: sentence-transformers

**Selected:** `sentence-transformers` library with `all-MiniLM-L6-v2` as default (or `BAAI/bge-small-en-v1.5` for higher accuracy).

**Alternatives Considered:**

- OpenAI `text-embedding-ada-002` / `text-embedding-3-small`: High quality but requires an API key and incurs per-token cost. Incompatible with the "no API cost required" goal.
- Ollama embedding endpoints: Some Ollama models expose embedding APIs. Quality varies by model; less standardized than SentenceTransformers. Adds a runtime dependency on Ollama being available even for embedding (claim: embedding should work even if local LLM is unavailable).
- Cohere embeddings: External API, incurs cost.
- FastEmbed (Qdrant): Lightweight alternative to SentenceTransformers with ONNX runtime. Faster inference but smaller model selection.

**Model selection rationale:**

- `all-MiniLM-L6-v2`: 22M parameters, 384-dim vectors, ~80ms per sentence on CPU. Well-suited for semantic similarity tasks. Downloads once, cached locally.
- `BAAI/bge-small-en-v1.5`: 33M parameters, 384-dim vectors, higher benchmark scores on retrieval tasks. Recommended if accuracy is prioritized over inference speed.

**Trade-offs:**

- Local embedding models add ~300–500MB to the deployment image size (model weights).
- First-request embedding generation triggers model loading (~2s cold start). Mitigated by loading the model eagerly at application startup.

**Justification:** Local embedding eliminates API cost and external dependency. `sentence-transformers` is the most mature Python embedding library with a broad model catalog. The selected models provide adequate retrieval quality for claim-evidence matching at sub-100ms latency on CPU.

---

## TD-10 — Local LLM Runtime: Ollama

**Selected:** Ollama

**Alternatives Considered:**

- llama.cpp (direct): Maximum control and performance. No HTTP server abstraction — requires direct Python bindings (`llama-cpp-python`). Embedding into the FastAPI process risks OOM crashes affecting the web server. Running as a subprocess adds process management complexity.
- vLLM: Production-grade inference server with PagedAttention and high throughput. Requires CUDA GPU; does not run on CPU-only free hosting. Eliminated.
- LM Studio: Desktop application; no programmatic API suitable for server deployment. Eliminated.
- Hugging Face Inference API: External API with rate limits and cost. Incompatible with "no API cost required" goal.
- LocalAI: OpenAI-compatible local inference server. Viable alternative to Ollama. Smaller community, less polished model management tooling.

**Trade-offs:**

- Ollama runs as a separate process; if it crashes, the backend must handle `ConnectionRefusedError` gracefully (covered in failure recovery model).
- Ollama's model management CLI (`ollama pull`, `ollama list`) is the mechanism for pre-loading models at deployment time.
- Ollama exposes an OpenAI-compatible API (`/v1/chat/completions`), enabling the same `openai` Python SDK client to be used for both Ollama and OpenAI with only the base URL swapped. This significantly simplifies the `LLMExecutionLayer` adapter implementation.

**Justification:** Ollama is the de-facto standard for local LLM deployment. OpenAI API compatibility eliminates the need for a separate HTTP client for local inference. Its model management tooling is production-ready and well-documented.

---

## TD-11 — Serialization: Pydantic v2

**Selected:** Pydantic v2

**Alternatives Considered:**

- Pydantic v1: Incompatible with FastAPI 0.100+ defaults. Legacy API.
- marshmallow: Mature but verbose schema definition. No Rust-backed validation; slower than Pydantic v2.
- attrs + cattrs: High-performance, but less ergonomic for nested model definitions compared to Pydantic.
- dataclasses (stdlib): No built-in validation or serialization. Requires additional libraries.

**Trade-offs:**

- Pydantic v2 (Rust-backed core) is 5–50x faster than v1 for validation. For a pipeline processing potentially large claim lists, this matters.
- Pydantic v2's strict mode catches type coercion bugs at model boundaries — enforced on all domain model classes.

**Justification:** Pydantic v2 is the native serialization layer of FastAPI. Using it consistently for API schemas, domain models, and configuration objects eliminates cross-layer serialization friction.

---

## TD-12 — Background Processing: asyncio Native Task Queue

**Selected:** `asyncio.Queue` with a single background coroutine consumer (implemented using `asyncio.create_task` at startup).

**Alternatives Considered:**

- Celery + Redis: Production-grade distributed task queue. Requires Redis broker and a separate Celery worker process. Over-engineered for the single background task type (KB indexing) in the MVP.
- ARQ (async Redis queue): Lightweight async task queue. Requires Redis. Same operational overhead concern as Celery for MVP scope.
- `concurrent.futures.ThreadPoolExecutor`: Threading is simpler than multiprocessing for I/O-bound background work. However, embedding generation is CPU-bound and will be GIL-limited under threading.
- Huey: Simple task queue with Redis or SQLite as broker. SQLite broker is viable; adds another dependency library.

**Implementation:**

```python
# startup
indexing_queue: asyncio.Queue[IndexDocumentJob] = asyncio.Queue(maxsize=100)
asyncio.create_task(kb_indexing_worker(indexing_queue))

async def kb_indexing_worker(queue: asyncio.Queue):
    while True:
        job = await queue.get()
        try:
            await run_in_executor(process_pool, index_document, job)
        except Exception as e:
            await mark_document_failed(job.document_id, str(e))
        finally:
            queue.task_done()
```

CPU-bound indexing (embedding generation) is offloaded to a `ProcessPoolExecutor` within the worker coroutine.

**Scale trigger:** Migrate to ARQ or Celery when: (1) indexing jobs must survive application restarts, (2) multiple worker processes are needed, (3) job retry policies require a durable queue.

**Justification:** In-process asyncio queue requires zero additional infrastructure, is trivially observable (queue depth as a metric), and is entirely sufficient for the expected KB indexing workload in the MVP (one document at a time, infrequent).

---

## TD-13 — Real-Time Communication: WebSocket (FastAPI Native)

**Selected:** WebSocket via FastAPI's native WebSocket support (Starlette WebSocket).

**Alternatives Considered:**

- Server-Sent Events (SSE): Simpler than WebSocket (HTTP/1.1 compatible, no upgrade handshake). Unidirectional (server → client), which is sufficient for pipeline progress. However, FastAPI SSE support requires third-party library (`sse-starlette`); WebSocket is native.
- Long polling: Maximum compatibility; no persistent connection required. Adds latency (polling interval) and server load (repeated HTTP requests during pipeline execution).
- WebTransport (HTTP/3): Too experimental; no mainstream browser support maturity.

**Trade-offs:**

- WebSocket requires connection management (client reconnection on disconnect, ping/keepalive). Implemented with a simple client-side reconnect loop.
- WebSocket connections require sticky session routing in multi-worker deployments (addressed in scaling section).

**Protocol:** A simple JSON message format per pipeline stage event:

```json
{
  "request_id": "req_abc123",
  "event": "stage_complete",
  "stage": "prompt_validation",
  "status": "passed",
  "metadata": { "risk_score": 12 },
  "timestamp_ms": 1710000000000
}
```

**Justification:** Native FastAPI WebSocket support requires no additional library. The bidirectional nature allows future client → server interactions (e.g., cancelling a request in progress) without a protocol change.

---

## TD-14 — Reverse Proxy / Gateway: Caddy

**Selected:** Caddy 2

**Alternatives Considered:**

- Nginx: Battle-tested; verbose configuration syntax; requires manual TLS certificate management (or certbot integration). Caddy automates HTTPS via Let's Encrypt by default.
- Traefik: Docker-native; automatic service discovery. Overhead for a single-service deployment.
- AWS API Gateway / Cloudflare: External managed services. Adds cost and external dependency. Incompatible with free self-hosted deployment goal.
- Direct Uvicorn exposure: No TLS, no rate limiting, no static asset serving. Not suitable for production.

**Trade-offs:**

- Caddy's automatic HTTPS is critical for free hosting deployments (no manual certificate management).
- Caddy's Caddyfile syntax is significantly more concise than Nginx config for equivalent functionality.
- Caddy has lower throughput than Nginx under extreme load, but for this application, the LLM inference latency (10–20s) means the reverse proxy is never the bottleneck.

**Justification:** Caddy's zero-configuration HTTPS is the decisive advantage for a deployment targeting free hosting platforms. The Caddyfile for this application is fewer than 20 lines.

---

## TD-15 — Logging Framework: structlog

**Selected:** `structlog` 24.x

**Alternatives Considered:**

- Python stdlib `logging`: Unstructured text output by default. Structured JSON output requires custom formatters. No context variable support.
- `loguru`: Cleaner API than stdlib logging; structured output via `serialize=True`. Less powerful context binding than structlog.
- `python-json-logger`: Adds JSON formatting to stdlib logging. Lightweight but limited compared to structlog's context chain and processor pipeline.

**Configuration:**

```python
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,   # inject request_id from context
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.JSONRenderer(),        # stdout as JSON
    ],
    wrapper_class=structlog.BoundLogger,
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)
```

`structlog.contextvars` binds `request_id` and `session_id` to the async context at request entry, making them available on every log line within that request without explicit threading.

**Justification:** structlog's processor chain, async context variable support, and JSON output are purpose-built for structured logging in async Python services. The `merge_contextvars` processor eliminates manual `request_id` passing in every log call.

---

## TD-16 — Monitoring Strategy: Prometheus + Grafana (Phase 3)

**Selected:** `prometheus-fastapi-instrumentator` for automatic HTTP metrics; custom counters via `prometheus_client` for domain metrics.

**MVP approach:** Metrics counters are implemented in code from Phase 1 but the `/metrics` endpoint is only activated in Phase 3. In MVP, aggregate metrics are served from the `analytics` database table via the `/v1/analytics` API.

**Alternatives Considered:**

- Datadog APM: Excellent but paid. Incompatible with zero-cost MVP infrastructure goal.
- New Relic: Same cost concern.
- OpenTelemetry (OTLP) only: Vendor-neutral and correct for the long term. In MVP, adds complexity without a ready collector endpoint.

**Justification:** Prometheus is the standard for self-hosted metrics collection. Instrumenting from Phase 1 (with the endpoint gated) means Phase 3 activation is a config flag, not a code change.

---

## TD-17 — CI/CD: GitHub Actions

**Selected:** GitHub Actions

**Alternatives Considered:**

- GitLab CI: Equivalent capability; GitHub Actions is selected because the repository is assumed to be on GitHub.
- CircleCI: Mature; requires a separate account. No advantage over GitHub Actions for a GitHub-hosted repository.
- Jenkins: Self-hosted; significant operational overhead for a small team.

**Pipeline stages:**

1. `lint` — Ruff + mypy (< 60s)
2. `test` — pytest (unit + integration, < 3 min)
3. `build` — Docker image build + push to GHCR
4. `deploy` — SSH deploy or platform-specific deploy hook (Render/Railway/Fly.io)

**Justification:** GitHub Actions is zero-additional-cost for public repositories and tightly integrated with GitHub PRs and branch protection rules.

---

## TD-18 — Code Quality: Ruff + mypy + pre-commit

**Selected:** `ruff` (linting + formatting), `mypy` (static type checking), `pre-commit` (hook enforcement).

**Alternatives Considered:**

- `flake8` + `black` + `isort`: The traditional Python quality stack. Three separate tools replaced by Ruff alone. Ruff is 10–100x faster and covers all three.
- `pylint`: Comprehensive but slow and noisy. Generates too many false positives for async code patterns without extensive configuration.
- `pyright`: Microsoft's type checker; faster than mypy for large codebases. Both mypy and pyright are viable; mypy is selected for broader ecosystem compatibility (Pydantic, SQLAlchemy mypy plugins).

**mypy configuration:**

- `strict = true` enabled.
- Explicit `--disallow-untyped-defs`, `--disallow-incomplete-defs`.
- Pydantic mypy plugin enabled.
- SQLAlchemy mypy extension enabled.

**Justification:** Ruff eliminates the multi-tool Python linting setup. mypy strict mode catches type errors that would otherwise surface as runtime bugs in the async pipeline. pre-commit ensures these checks run before every commit, not just in CI.

---

## TD-19 — Testing Framework: pytest + pytest-asyncio + Playwright

**Selected:** `pytest` + `pytest-asyncio` (async test support) + `Playwright` (E2E browser testing).

**Alternatives Considered:**

- `unittest`: Built-in but verbose. No native async support. pytest is strictly superior.
- `Hypothesis` (property-based testing): Valuable for the confidence scoring engine and validation logic. Added as a Phase 2 enhancement, not MVP.
- Cypress: JavaScript E2E testing framework. Playwright is selected because it supports Python (allowing test code in the same language as the backend), and provides better parallel test execution.

**Justification:** pytest is the standard Python testing framework. pytest-asyncio supports testing async FastAPI route handlers and pipeline stages without synchronous wrappers. Playwright enables automated E2E testing of the React playground.

---

## TD-20 — Containerization: Docker + Docker Compose

**Selected:** Docker with multi-stage builds + Docker Compose for local development and MVP deployment.

**Alternatives Considered:**

- Podman: Drop-in Docker replacement; compatible but requires developer environment reconfiguration.
- Kubernetes (Helm): Correct for scaled deployments but massively over-engineered for MVP single-instance deployment.
- Nix flakes: Reproducible environments; steep learning curve; not appropriate for a team that may include non-Nix developers.

**Compose services (MVP):**

```yaml
services:
  app:         # FastAPI + Uvicorn
  ollama:      # Local LLM runtime
  caddy:       # Reverse proxy
```

**Multi-stage Dockerfile:**

1. `base` — Python 3.12 slim + system dependencies
2. `builder` — pip install dependencies
3. `runtime` — copy installed packages + application code, no build tools

**Justification:** Docker Compose is the simplest way to run the multi-service MVP (FastAPI + Ollama + Caddy) with a single `docker compose up` command. Multi-stage builds minimize the production image size by excluding build-time dependencies.

---

## TD-21 — Safety Classification: detoxify

**Selected:** `detoxify` library (local model, Unitary AI)

**Alternatives Considered:**

- OpenAI Moderation API: High quality; free; however, requires an internet call and OpenAI account. Incompatible with fully offline operation.
- Perspective API (Google): Requires API key; external dependency; latency of a network call.
- Custom classifier (fine-tuned BERT): High accuracy for specific domains but requires training data and GPU. Out of scope.
- Rule-based keyword filtering: Fast but low recall (easily circumvented). Insufficient as the sole safety mechanism.
- `transformers` (HuggingFace) + custom model: Flexible but requires model selection and hosting. `detoxify` wraps this complexity.

**`detoxify` characteristics:**

- Runs entirely locally on CPU.
- Returns per-label scores: `toxicity`, `severe_toxicity`, `obscene`, `threat`, `insult`, `identity_attack`, `sexual_explicit`.
- Model size: ~250MB (multilingual model) or ~100MB (English-only).
- Inference latency: ~100–300ms on CPU for a typical response.

**Trade-offs:**

- `detoxify` does not detect harmful instructions (e.g., "how to synthesize explosives"). A separate rule-based check using pattern matching against a curated harmful instruction pattern list supplements detoxify for this category.
- The `HarmfulInstructionFilter` is implemented as a regex/pattern-match filter in Phase 1; upgraded to a small classifier in Phase 3.

**Justification:** `detoxify` provides production-quality toxicity and hate speech classification with zero external API dependency, meeting the "local, no API cost" product constraint.

---

## TD-22 — Frontend State Management: Zustand

**Selected:** Zustand 4.x

**Alternatives Considered:**

- Redux Toolkit: Industry standard for complex state; significant boilerplate for the relatively modest state requirements of this SPA (pipeline results, policy config, KB list, analytics data).
- React Context + useReducer: Built-in; no library dependency. Acceptable for simple state but causes unnecessary re-renders without careful `useMemo`/`useCallback` usage in the analytics dashboard with frequent updates.
- Jotai: Atomic state model; excellent for fine-grained reactivity. Smaller community than Zustand.
- TanStack Query (React Query): Optimal for server-state (API data fetching, caching, refetching). Used alongside Zustand: TanStack Query manages API data; Zustand manages client-only UI state (pipeline progress, active panel tab, policy draft changes).

**State slices:**

- `playgroundSlice`: Current prompt, model selection, KB selection, pipeline result, trace visibility.
- `policySlice`: Draft policy configuration, unsaved change indicator.
- `kbSlice`: Document list, indexing status.
- `analyticsSlice`: Cached dashboard data, time range filter selection.
- `sessionSlice`: Current session ID, WebSocket connection status.

**Justification:** Zustand's minimal API (no providers, no reducers, direct state mutation via Immer integration) is well-suited to the SPA's state complexity. It eliminates Redux boilerplate without sacrificing state isolation or DevTools support.
