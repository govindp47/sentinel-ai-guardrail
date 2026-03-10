# 12_ENGINEERING_EXECUTION_PLAN.md

# SentinelAI Guardrail — Engineering Execution Plan

**Version:** 1.0  
**Status:** Active  
**Document Type:** Engineering Execution Plan  
**Audience:** Engineering

---

## Table of Contents

1. [Execution Principles](#1-execution-principles)
2. [Model Usage Strategy](#2-model-usage-strategy)
3. [Context Optimization Strategy](#3-context-optimization-strategy)
4. [Dependency Graph Overview](#4-dependency-graph-overview)
5. [Phased Engineering Plan](#5-phased-engineering-plan)
6. [Detailed Task Breakdown](#6-detailed-task-breakdown)

---

## 1. Execution Principles

These rules govern every task in this plan. They are not suggestions — treat them as invariants that must hold at every commit boundary.

---

### 1.1 Task Sizing

- Every task must represent **1–3 focused engineering sessions** (~2–6 hours of focused work).
- Tasks must affect **2–8 files** ideally. Tasks touching 10+ files are split.
- A single task must never span more than **one architectural layer** (database, domain, infrastructure, application, API, frontend).
- No task generates more than approximately **2,000 lines** of code including tests.

---

### 1.2 File Impact Limits

- **Database tasks:** touch only migration files, ORM models, and repository files.
- **Domain tasks:** touch only `domain/` modules and `tests/unit/domain/`.
- **Infrastructure tasks:** touch only `infrastructure/` adapters and `tests/integration/`.
- **Application tasks:** touch only `application/` services, use cases, container wiring.
- **API tasks:** touch only `api/` routers, middleware, schemas, and `tests/integration/api/`.
- **Frontend tasks:** touch only `frontend/src/` components, hooks, stores, and `tests/e2e/`.
- Cross-layer changes are only permitted in explicitly designated integration/wiring tasks.

---

### 1.3 Layer Isolation

The system's layer order is enforced strictly:

```
Database Models → Domain Models → Infrastructure Adapters
    → Application Services → API Layer → Frontend
```

No layer may import from the layer above it. Domain models must never import from infrastructure. Application services own the wiring. This is verified by `mypy` import discipline and enforced in code review.

---

### 1.4 Incremental Commits

Every task must be committable as a self-contained change:

- All tests pass at every commit point.
- No half-implemented abstractions are committed (stub with `raise NotImplementedError` only if the calling code never reaches it yet).
- Pre-commit hooks (`ruff`, `mypy`, `eslint`) must pass before every commit.
- Database migrations are irreversible by design (additive-only). A migration file committed to `main` is permanent.

---

### 1.5 Schema Migration Safety Rules

These rules apply to every Alembic migration:

1. **Additive only.** All migrations add columns, tables, or indexes. No column renames, type changes, or drops without a multi-phase migration pattern.
2. **Downgrade functions are no-ops** for additive migrations. Never write a downgrade that drops data.
3. **Never modify a committed migration file.** Create a new migration to correct mistakes.
4. **Every migration is tested** via `pytest tests/migration/` before merge.
5. **Constraints are verified** in the migration test suite (FKs, UNIQUEs, NOT NULLs).
6. **Column defaults are set in the migration**, not assumed from application logic.

---

### 1.6 Domain Logic Safety Rules

1. Domain engines are **pure functions**: no I/O, no database access, no HTTP calls, no logging inside engine methods.
2. All domain models are **frozen dataclasses or Pydantic models** with no mutable state.
3. `PipelineContext` is instantiated fresh per request — never reused.
4. All threshold comparisons are **strictly typed** (no implicit float coercions).
5. Every engine has **95%+ line coverage** from unit tests before it is wired to the application layer.
6. Engine boundary conditions (score == threshold, empty claim list, empty KB) are all covered by explicit test cases.

---

## 2. Model Usage Strategy

Two models are available for executing engineering tasks. Assignment is deterministic — it follows the rules below, not personal preference.

---

### Claude Sonnet (thinking)

Use for tasks that require multi-step reasoning, constraint satisfaction across modules, or correctness under ambiguity.

**Assigned to:**

- Architecture and interface design decisions
- Alembic migration correctness and constraint verification
- Domain engine algorithm implementation (scoring formulae, decision rule logic, PII detection patterns)
- Concurrency model design (asyncio + ProcessPoolExecutor interaction, FAISS lock strategy)
- Data consistency logic (audit transaction atomicity, FAISS + DB dual-write consistency)
- Pipeline orchestrator control flow (short-circuit, retry loop, stage error isolation)
- Security implementation (API key stripping middleware, input sanitization, rate limiting logic)
- Debugging non-obvious failures (incorrect confidence scores, FAISS remove_ids edge cases, WS race conditions)
- Schema design reviews before new migrations are written

---

### Claude Sonnet (fast)

Use for tasks where the structure is known and the work is primarily generative or mechanical.

**Assigned to:**

- Boilerplate scaffolding (project structure, pyproject.toml, Dockerfile stages)
- SQLAlchemy ORM model generation from the schema document
- Repository method implementations (CRUD patterns over defined schema)
- FastAPI route handlers (following defined request/response schemas)
- React component generation (following defined component specs from 05_APPLICATION_STRUCTURE.md)
- Zustand store slice implementations
- SDK model and client method generation
- Test file generation (unit and integration test stubs from acceptance criteria)
- Documentation and README generation
- Refactoring: rename, extract method, reorganize imports
- CI/CD YAML configuration files

---

### Model Assignment Decision Rule

```
IF the task requires:
    - Inventing an algorithm or decision rule    → thinking
    - Satisfying multiple interacting constraints → thinking
    - Debugging emergent behavior                → thinking
    - Concurrency correctness                    → thinking
    - Security-critical logic                    → thinking

ELSE IF the task requires:
    - Generating code from a known spec          → fast
    - Refactoring existing code                  → fast
    - Writing tests from acceptance criteria     → fast
    - Building UI components from a design spec  → fast
    - Scaffolding configuration                  → fast
```

---

## 3. Context Optimization Strategy

Context management is a first-class engineering concern. Loading unnecessary documents increases cost, degrades reasoning quality, and risks stale-document confusion.

---

### 3.1 When to Start a New Chat

Start a new chat at each of the following boundaries:

| Trigger | Reason |
|---|---|
| Moving from database layer to domain engine | Different subsystem; DB files are irrelevant to domain logic |
| Moving from domain engine to infrastructure adapters | Adapters need schema and domain interface — clean slate |
| Moving from infrastructure to application layer | Application context is a fresh wiring context |
| Moving from application layer to API layer | API files do not require domain internals |
| Moving from API to frontend | Entirely different technology stack |
| After any schema migration is merged to main | Migration context is settled; no need to carry it forward |
| After completing any full phase (Phase N → Phase N+1) | Phase boundary is the natural reset point |
| After 8–10 consecutive task executions in the same chat | Accumulated context degrades inference quality |
| After a complex debugging session is resolved | Contaminated context from the debugging trace |

---

### 3.2 Context Loading Rules by Subsystem

Load only what is needed. Never load the full blueprint in one context window.

| Subsystem | Load | Do NOT Load |
|---|---|---|
| Project Setup | `02_TECH_DECISIONS.md`, `10_DEPLOYMENT_WORKFLOW.md` | Schema, domain, frontend docs |
| Database Layer | `03_DATABASE_SCHEMA.md`, `02_TECH_DECISIONS.md` | Domain, application, frontend docs |
| Domain Engine | `04_DOMAIN_ENGINE_DESIGN.md`, `00_PRODUCT_SPECIFICATION.md` (pipeline stages section only) | Schema, infrastructure, API, frontend docs |
| Infrastructure Adapters | `03_DATABASE_SCHEMA.md`, `04_DOMAIN_ENGINE_DESIGN.md` (interfaces only), `02_TECH_DECISIONS.md` | Application, API, frontend docs |
| Application Layer | `04_DOMAIN_ENGINE_DESIGN.md`, `05_APPLICATION_STRUCTURE.md` (application section) | Frontend docs, deployment docs |
| API Layer | `05_APPLICATION_STRUCTURE.md` (API section), `07_SECURITY_MODEL.md` | Domain internals, deployment docs |
| Frontend | `05_APPLICATION_STRUCTURE.md` (frontend section), `00_PRODUCT_SPECIFICATION.md` (UX section) | Backend internals, schema docs |
| Automation/AI | `06_AUTOMATION_AND_AI_INTEGRATION.md`, `04_DOMAIN_ENGINE_DESIGN.md` | Frontend docs, deployment docs |
| Security | `07_SECURITY_MODEL.md`, `05_APPLICATION_STRUCTURE.md` (middleware section) | Domain internals, frontend component details |
| Testing | `09_TESTING_STRATEGY.md`, relevant subsystem doc | All unrelated subsystem docs |
| Deployment | `10_DEPLOYMENT_WORKFLOW.md`, `08_BACKUP_AND_RECOVERY.md` | Domain, frontend internals |

---

### 3.3 Anti-Patterns to Avoid

- **Never paste the full schema document** when implementing a single repository — paste only the relevant table definition.
- **Never load all architecture documents** at task start — identify the 1–2 documents that directly govern the task.
- **Never carry forward debugging traces** into the next task's chat — debugging context pollutes reasoning.
- **Do not re-explain the system** at the start of each message — load the document once and reference sections by name.

---

## 4. Dependency Graph Overview

---

### 4.1 Subsystem Dependency Order

```
[Phase 0] Project Scaffold & Infrastructure
    │
    ▼
[Phase 1] Database Layer
    │  (ORM models, Alembic migrations, repository interfaces)
    ▼
[Phase 2] Domain Engine
    │  (Pure logic: all engines, Pydantic models, zero I/O)
    ▼
[Phase 3] Infrastructure Adapters
    │  (FAISS, embeddings, Ollama, OpenAI, Detoxify, repositories — depend on domain interfaces)
    ▼
[Phase 4] Application Layer & Pipeline Orchestrator
    │  (Wires domain engines + adapters; owns pipeline execution and audit)
    ▼
[Phase 5] API Layer
    │  (FastAPI routes, WebSocket, middleware — expose application layer)
    ▼
[Phase 6] Frontend
    │  (React SPA — consumes API; Playground, KB Management)
    ▼
[Phase 7] Cross-Cutting: Analytics, Policy, SDK, Advanced Features
    │  (Layered on top of Phase 4–6; partially parallel after Phase 5)
    ▼
[Phase 8] Security Hardening
    │  (Audits and hardens Phase 4–7 outputs)
    ▼
[Phase 9] Testing & Performance Hardening
    │  (Integration, E2E, load tests; requires all prior phases functional)
    ▼
[Phase 10] Release Preparation
        (Deployment hardening, docs, smoke tests, public launch)
```

> **Note:** This plan maps the above to 8 engineering phases (Phase 0 through Phase 7) by collapsing the later cross-cutting concerns into unified phases.

---

### 4.2 Critical Path

The critical path is the sequence with no parallel slack:

```
Scaffold → DB Schema → Domain Models → Pipeline Orchestrator
→ FastAPI Submit Endpoint → Playground UI → Public Deployment
```

Every item on this path blocks public demo availability. Prioritize unblocking this path before branching into supporting features (analytics, policy config, SDK).

---

### 4.3 Foundational Modules

These modules are dependencies for the highest number of downstream tasks. Correctness errors here propagate broadly. They require `thinking` model assignment and the strictest test coverage requirements.

| Module | Downstream Impact |
|---|---|
| `PipelineContext` dataclass | All 7 pipeline stages depend on its structure |
| `GuardrailDecisionEngine` | Determines the final output of every request |
| `ConfidenceScoringEngine` | Feeds `GuardrailDecisionEngine`; any scoring error affects all decisions |
| Alembic `0001_initial_schema` migration | All repositories depend on this schema being correct |
| `ApplicationContainer` (DI wiring) | Application startup; wiring errors are runtime crashes |
| `AuditService` transaction logic | All request records depend on atomic multi-table writes |
| `EventBus` (WebSocket event queue) | All real-time UI progress depends on this abstraction |

---

### 4.4 Parallelizable Work

After Phase 3 is complete, the following streams can proceed in parallel (on a 2-person team):

- **Stream A:** Application Layer → API Layer → Deployment
- **Stream B:** Domain Engine additional tests → Performance benchmarks

After Phase 5 (API Layer) is complete:

- **Stream A:** Frontend Playground + KB Management
- **Stream B:** Analytics backend endpoints + Policy backend endpoints

---

## 5. Phased Engineering Plan

---

### Phase 0 — Project Setup & Infrastructure

**Objective:**  
Establish the complete development environment: monorepo layout, dependency management, Docker stack, CI pipeline skeleton, Alembic initialization, and pre-commit quality gates. No application logic is written in this phase — only the scaffolding that every subsequent task builds on.

**Risk Level:** Low  
All work in this phase is configuration and tooling. The primary risk is dependency version conflicts between Python ML libraries (`sentence-transformers`, `faiss-cpu`, `detoxify`, `torch`) that must be resolved before any application code is written.

**Completion Criteria:**

- `docker compose up` starts backend, frontend dev server, and any local services without errors.
- `alembic upgrade head` runs successfully against an empty database (even with zero migration files — just the environment configured correctly).
- `pre-commit run --all-files` passes on the empty repository.
- `pytest tests/` runs with zero tests and zero failures.
- `npm run type-check` passes on an empty Vite + TypeScript scaffold.
- GitHub Actions CI pipeline executes on push and reports green on the empty test suite.
- All Python dependencies resolve without conflicts via `uv lock`.

---

### Phase 1 — Database Layer

**Objective:**  
Implement the complete database schema as Alembic migrations, all SQLAlchemy ORM models for all 10 tables, and the repository abstraction layer. This phase establishes the data contract that all higher layers depend on.

**Risk Level:** Medium  
The schema is complex (10 tables, multiple FKs, UUID primary keys, JSON columns). Migration correctness errors discovered later are expensive — they require new migrations and potential data loss if the system is already in production. Every constraint must be verified in the migration test suite before this phase is closed.

**Completion Criteria:**

- `alembic upgrade head` produces all 10 tables with correct columns, types, constraints, indexes, and FK relationships on both SQLite and PostgreSQL.
- `alembic downgrade base` runs without error (no-op downgrades).
- `pytest tests/migration/` passes: all tables verified, all indexes confirmed, all FK constraints enforced.
- All SQLAlchemy ORM models map 1:1 to the schema with no unmapped columns.
- All repository interfaces have stub implementations that raise `NotImplementedError` — enough for the application layer to wire against.
- `mypy src/sentinel/infrastructure/database/` reports zero errors.

---

### Phase 2 — Domain Engine

**Objective:**  
Implement the complete pure-Python domain engine layer: all domain value objects (Pydantic/frozen dataclasses), all seven pipeline stage engines, and their unit test suites. This phase must achieve ≥95% line coverage on the domain layer. No I/O, no database access, no HTTP calls in any domain module.

**Risk Level:** High  
This is the highest-risk phase because domain logic errors produce subtly wrong outputs — incorrect confidence scores, missed injection patterns, wrong claim verification statuses — that are difficult to detect without exhaustive test cases. Boundary conditions (score == threshold, empty claim list, no KB, all claims unverified) are especially dangerous.

**Completion Criteria:**

- All domain value objects are defined as frozen dataclasses or Pydantic models with complete field types.
- `InjectionDetector`, `PIIDetector`, `PolicyFilter`, `RiskScorer` all pass their unit test suites.
- `ConfidenceScoringEngine` produces deterministic output for identical inputs across 1000 randomized test cases.
- `GuardrailDecisionEngine` correctly applies priority ordering: safety filter override beats confidence threshold beats policy block.
- `GuardrailDecisionEngine` passes all threshold boundary tests (score == accept_threshold, score == warn_threshold).
- `FallbackStrategyEngine` correctly sequences all 4 fallback strategies without infinite loops.
- `pytest tests/unit/domain/` achieves ≥ 95% line coverage.
- `mypy src/sentinel/domain/` reports zero errors.
- All engines are stateless: no class-level mutable state, no shared singletons.

---

### Phase 3 — Infrastructure Adapters

**Objective:**  
Implement all infrastructure adapters that connect domain interfaces to external systems: SQLAlchemy repositories, FAISS vector store, SentenceTransformer embedding adapter, Ollama adapter, OpenAI adapter, Detoxify classifier, text chunker, and local file storage. Each adapter is tested in isolation via integration tests.

**Risk Level:** High  
Infrastructure adapters interact with external processes (Ollama, file system, in-process ML models) and have complex error modes: FAISS `remove_ids` edge cases, detoxify worker serialization in `ProcessPoolExecutor`, async SQLAlchemy session lifecycle, embedding model LRU cache thread-safety. Each must be verified before the application layer wires them together.

**Completion Criteria:**

- All repositories implement their interfaces with real database I/O (SQLite in tests).
- FAISS add → query → remove → query round-trip test passes.
- `SentenceTransformerAdapter.embed()` returns vectors of dimension 384 (MiniLM-L6-v2).
- `OllamaAdapter.health_check()` returns `True` when Ollama is running, `False` otherwise (no crash).
- `DetoxifyClassifier.predict()` dispatches correctly to a `ProcessPoolExecutor` worker and returns within 10 seconds.
- `TextChunker.chunk()` produces overlapping windows with correct sentence boundary detection.
- All integration tests pass: `pytest tests/integration/`.
- `mypy src/sentinel/infrastructure/` reports zero errors.

---

### Phase 4 — Application Layer & Pipeline Orchestrator

**Objective:**  
Wire domain engines and infrastructure adapters into the application layer: `ApplicationContainer` (dependency injection), `GuardrailPipelineOrchestrator` (full pipeline execution with short-circuit and retry), `SubmitPromptUseCase`, `AuditService` (atomic multi-table write), `KnowledgeRetrievalLayer`, and the background KB indexing worker. A complete pipeline execution (from Python, not HTTP) must succeed by the end of this phase.

**Risk Level:** High  
This phase is where all prior components must integrate correctly. The orchestrator's concurrency model (asyncio + ProcessPoolExecutor), retry loop correctness, and audit atomicity are all complex. Errors here produce silent data corruption or non-deterministic behavior.

**Completion Criteria:**

- `ApplicationContainer.initialize()` starts without errors with Ollama running.
- A direct Python call to `SubmitPromptUseCase.execute()` with a test prompt produces a `GuardrailResponse` with all fields populated.
- The orchestrator correctly short-circuits: a blocked prompt produces no LLM call (verified by mock).
- The retry loop terminates correctly: `MAX_RETRIES_EXCEEDED` is emitted after N retries.
- `AuditService` writes all audit rows in a single transaction; partial failure rolls back completely.
- The background KB indexer transitions a document from `pending` → `indexing` → `ready` for a test document.
- `pytest tests/consistency/` passes: pipeline determinism, audit immutability, score invariants.
- `mypy src/sentinel/application/` reports zero errors.

---

### Phase 5 — API Layer

**Objective:**  
Expose the application layer via FastAPI: all REST routers (`/v1/guardrail`, `/v1/kb`, `/v1/analytics`, `/v1/requests`, `/v1/policy`, `/health`), WebSocket handler with `EventBus`, all middleware (CORS, Request ID injection, Session ID validation, API Key Stripping, Structured Logging), and all error handlers. The public API surface is fully defined and integration-tested by end of this phase.

**Risk Level:** Medium  
The API layer is structurally straightforward but has important correctness requirements: API key stripping middleware must never log a key, WebSocket event buffering must handle late subscribers, session ID validation must never crash on malformed input. These are security and reliability requirements, not just functionality.

**Completion Criteria:**

- `POST /v1/guardrail/submit` completes end-to-end with a real Ollama model and returns a fully populated response.
- WebSocket events arrive in order during pipeline execution (verified via test WebSocket client).
- `GET /health/ready` returns `200` with `{"ollama": "ok"}` when Ollama is running.
- `GET /health/ready` returns `503` with degraded status when Ollama is unavailable.
- All 12 exception → HTTP status code mappings are tested.
- API key in request body is stripped from structured logs (verified by log inspection test).
- `pytest tests/integration/api/` passes with all 9+ test scenarios.
- OpenAPI schema is valid and all routes are documented.

---

### Phase 6 — Frontend

**Objective:**  
Build the complete React SPA: Playground page (full submission flow, pipeline progress, confidence badge, analysis panel, execution trace viewer), Knowledge Base Management page (document upload, status tracking, KB selector), shared component library, Zustand store, React Router, and WebSocket integration. The public playground must be fully functional by end of this phase.

**Risk Level:** Medium  
Frontend risk is primarily integration risk: WebSocket event buffering interaction with the React lifecycle, claim-to-evidence linking state coordination, file upload progress UX. TypeScript discipline must be maintained throughout — `npm run type-check` must pass at every commit.

**Completion Criteria:**

- A first-time user can submit a prompt, observe real-time pipeline progress, and see the final result with confidence badge, decision label, and analysis panel.
- The Execution Trace Viewer expands and collapses per stage.
- A blocked prompt renders the block state (no response text, red alert with reason code).
- A document can be uploaded and transitions from Pending → Indexing → Ready with live status updates.
- Evidence retrieved from the KB appears in the Analysis Panel linked to its claim.
- `npm run type-check` reports zero errors.
- All `data-testid` attributes required for E2E tests are present.

---

### Phase 7 — Analytics, Policy, SDK & Release Preparation

**Objective:**  
Complete the remaining product surfaces: Analytics Dashboard, Request Explorer with replay, Policy Configuration UI, vector search preview, Python developer SDK, Prometheus metrics endpoint, export functionality, session cleanup worker, and production deployment hardening. This phase takes the system from "working demo" to "production-ready product."

**Risk Level:** Medium  
This phase involves the most breadth. Risk is managed by treating each surface as an independent deliverable — each feature is shippable before the next one begins. The PostgreSQL migration and multi-worker deployment carry the highest technical risk in this phase.

**Completion Criteria:**

- Analytics Dashboard renders correct charts after 5+ requests.
- Request Explorer supports search, filter by decision type, and request replay.
- Policy Configuration saves and takes effect on the next request.
- Python SDK: `pip install -e sdk/python` installs cleanly; a developer can submit a prompt in 5 lines.
- `GET /metrics` returns valid Prometheus text format when `ENABLE_METRICS=true`.
- `GET /v1/requests/export?format=csv` produces a valid CSV file.
- Session cleanup worker deletes sessions older than `SESSION_RETENTION_DAYS`.
- Production deployment is live at a public URL with HTTPS enforced.
- `GET /health/ready` returns `200` on the production deployment.
- Backup script runs and `validate_restore.py` confirms backup integrity.
- All Phase 7 CI tests pass.

---

## 6. Detailed Task Breakdown

---

### Phase 0 — Project Setup & Infrastructure

---

#### Task ID: T-001

**Title:** Monorepo Scaffold, Python Project Initialization, and Pre-Commit Gates

**Phase:** 0

**Subsystem:** Project Infrastructure

**Description:**  
Initialize the complete monorepo directory layout as defined in `05_APPLICATION_STRUCTURE.md`. Configure the Python project with `pyproject.toml`, pin all backend dependencies using `uv`, generate `uv.lock`, and install pre-commit hooks for backend code quality gates (`ruff`, `mypy`, `bandit`). Create the `.env.example` file with all required environment variables documented inline.

**Scope Boundaries**

Files affected:

- `pyproject.toml`
- `uv.lock`
- `.pre-commit-config.yaml`
- `.env.example`
- `backend/src/sentinel/__init__.py`
- `backend/src/sentinel/config.py` (Pydantic Settings scaffold, all env vars declared, no logic)
- All `__init__.py` stubs for every package in the `sentinel/` tree

Modules affected:

- Project configuration layer only

Explicitly NOT touching:

- Application logic, database, domain, infrastructure, API, frontend, or Docker files

**Implementation Steps**

1. Create the full directory tree from `05_APPLICATION_STRUCTURE.md` section 1 for the `backend/` subtree; all `__init__.py` files are empty stubs.
2. Write `pyproject.toml`: Python 3.12 minimum, all dependencies pinned (`fastapi`, `uvicorn[standard]`, `sqlalchemy[asyncio]`, `alembic`, `pydantic-settings`, `structlog`, `sentence-transformers`, `faiss-cpu`, `detoxify`, `torch`, `ollama`, `openai`, `httpx`, `pytest`, `pytest-asyncio`, `mypy`, `ruff`). Pin versions to the tested combination documented in `02_TECH_DECISIONS.md`.
3. Run `uv lock` and commit the lockfile. Verify `uv sync` installs cleanly in a fresh virtualenv.
4. Write `backend/src/sentinel/config.py`: `AppConfig(BaseSettings)` class declaring all environment variables from `.env.example` with types, defaults, and descriptions. No runtime logic — declaration only.
5. Write `.env.example` with all variables from `config.py`, with inline comments describing each variable.
6. Write `.pre-commit-config.yaml`: `ruff` (lint + format), `mypy` (strict mode on `src/sentinel/`), `bandit` (B-level severity). Configure `ruff` to enforce import ordering and disallow star imports.
7. Run `pre-commit run --all-files` against the empty scaffold; fix any initial violations.

**Data Impact**

Schema changes: None  
Migration required: No

**Test Plan**

Unit tests: None (configuration layer is not unit-tested independently)  
Integration tests: None  
Manual verification steps:

- `uv sync` completes without dependency conflicts
- `pre-commit run --all-files` passes on the empty scaffold
- `python -c "from sentinel.config import AppConfig; AppConfig()"` succeeds with defaults

**Acceptance Criteria**

- Full directory tree matching `05_APPLICATION_STRUCTURE.md` exists with all `__init__.py` stubs
- `uv lock` resolves without conflicts; all ML dependencies (`sentence-transformers`, `faiss-cpu`, `detoxify`, `torch`) co-exist in the same environment
- `AppConfig` can be instantiated with all defaults (no env file required)
- `pre-commit run --all-files` passes
- `.env.example` documents every variable in `AppConfig` with type and description
- No application logic exists yet — scaffold only

**Rollback Strategy**

Delete the repository and re-initialize. No state exists at this point. The `uv.lock` is the only artifact requiring version history.

**Estimated Complexity:** S

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (thinking)  
Recommended Mode: thinking

Reason: Dependency version resolution between `sentence-transformers`, `faiss-cpu`, `detoxify`, and `torch` requires reasoning about compatible version combinations. A wrong pin here causes cascading failures in every subsequent task.

---

**Context Strategy**

Start new chat? Yes — this is the first task.

Required files to include as context:

- `02_TECH_DECISIONS.md` (dependency decisions and versions)
- `05_APPLICATION_STRUCTURE.md` (directory layout section)

Architecture docs to reference:

- `02_TECH_DECISIONS.md` sections TD-01 through TD-03, TD-18, TD-19

Documents NOT required:

- `03_DATABASE_SCHEMA.md`, `04_DOMAIN_ENGINE_DESIGN.md`, `06_AUTOMATION_AND_AI_INTEGRATION.md`, `07_SECURITY_MODEL.md`, `08_BACKUP_AND_RECOVERY.md`, `09_TESTING_STRATEGY.md`, `10_DEPLOYMENT_WORKFLOW.md`

---

---

#### Task ID: T-002

**Title:** Docker Compose Stack and Multi-Stage Dockerfile

**Phase:** 0

**Subsystem:** Project Infrastructure

**Description:**  
Write the multi-stage `Dockerfile.backend` (build, test, development, model-preload, production stages), `docker-compose.dev.yml` for local development, and `docker-compose.yml` for production. The Docker stack must start all services cleanly. No application logic is required to be functional — the containers must start and be healthy.

**Scope Boundaries**

Files affected:

- `docker/Dockerfile.backend`
- `docker/docker-compose.dev.yml`
- `docker/docker-compose.yml`
- `docker/.dockerignore`
- `docker/Caddyfile` (stub — proxies `/v1/*` to backend, serves static from `/app/static`)

Modules affected:

- Infrastructure/deployment layer only

Explicitly NOT touching:

- Application source code, migrations, frontend

**Implementation Steps**

1. Write `Dockerfile.backend` with five named stages:
   - `base`: Python 3.12-slim, system deps (`libgomp1` for FAISS), non-root user `sentinel`
   - `build`: install `uv`, copy `pyproject.toml` + `uv.lock`, run `uv sync --frozen`
   - `test`: extends `build`, copies source, sets `PYTHONPATH`
   - `model-preload`: extends `build`, runs a Python script that downloads and caches the SentenceTransformer model to `/app/.cache/`
   - `production`: extends `model-preload`, copies source, sets `CMD ["uvicorn", "sentinel.main:app"]`
2. Write `docker-compose.dev.yml`: backend service (build target `test`, volume mount `backend/src/`, env from `.env`), no Caddy in dev.
3. Write `docker-compose.yml`: backend service (build target `production`), Caddy service (with `Caddyfile` volume), shared network, named volume for SQLite data and FAISS index persistence.
4. Write `docker/.dockerignore` excluding `__pycache__`, `.pytest_cache`, `*.pyc`, `.env`, `uv.lock` (installed via `uv sync`).
5. Write stub `docker/Caddyfile`: reverse proxy `/v1/*` and `/ws/*` to `backend:8000`; serve `/app/static` for all other paths.
6. Verify: `docker compose -f docker/docker-compose.dev.yml up --build` starts without errors. Backend container exits cleanly (no `main.py` yet — that is acceptable; check for import errors only via `python -c "import sentinel"`).

**Data Impact**

Schema changes: None  
Migration required: No

**Test Plan**

Unit tests: None  
Integration tests: None  
Manual verification steps:

- `docker compose -f docker/docker-compose.dev.yml build` completes with no layer errors
- Container starts and `python -c "import sentinel"` succeeds inside the container
- Named volumes are created and persisted across `docker compose down && docker compose up`

**Acceptance Criteria**

- `docker compose up` starts backend and Caddy without errors
- Multi-stage build produces a `production` image under 2GB (SentenceTransformer model included)
- Non-root user `sentinel` owns all process files inside the container
- FAISS data directory and SQLite file directory are on named Docker volumes (not ephemeral container layers)
- `docker compose down -v` cleanly removes all volumes
- No secrets or `.env` contents are baked into any image layer

**Rollback Strategy**

Remove Docker image tags and revert Dockerfile changes. Named volumes are unaffected by image rollback — data persistence is container-independent.

**Estimated Complexity:** S

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (fast)  
Recommended Mode: fast

Reason: Docker multi-stage build patterns are well-defined and mechanical. The structure follows a standard Python ML service pattern.

---

**Context Strategy**

Start new chat? No — continue from T-001 chat.

Required files to include as context:

- `10_DEPLOYMENT_WORKFLOW.md` (Docker stages and Caddy config section)
- `02_TECH_DECISIONS.md` (TD-20 containerization)

Architecture docs to reference:

- `10_DEPLOYMENT_WORKFLOW.md` sections on Docker build and Caddy configuration

Documents NOT required:

- All domain, schema, and frontend documents

---

---

#### Task ID: T-003

**Title:** GitHub Actions CI Pipeline

**Phase:** 0

**Subsystem:** Project Infrastructure

**Description:**  
Configure the GitHub Actions CI pipeline with three workflows: `lint-backend` (ruff + mypy), `lint-frontend` (eslint + tsc), and `test-unit` (pytest with empty test suite). All workflows must pass on the scaffold before any application code is written. This establishes the green-baseline that every subsequent PR must maintain.

**Scope Boundaries**

Files affected:

- `.github/workflows/lint-backend.yml`
- `.github/workflows/lint-frontend.yml`
- `.github/workflows/test-unit.yml`
- `.github/workflows/deploy.yml` (stub — triggers on `main` push, no steps yet)

Modules affected:

- CI/CD infrastructure only

Explicitly NOT touching:

- Application source, Docker files, frontend source

**Implementation Steps**

1. Write `.github/workflows/lint-backend.yml`: triggers on `push` and `pull_request` targeting any branch; jobs: (a) `ruff check backend/src/`, (b) `mypy backend/src/sentinel/ --strict`; use `uv` for dependency installation with cache keyed on `uv.lock`.
2. Write `.github/workflows/lint-frontend.yml`: triggers on `push` and `pull_request`; jobs: `npm ci`, `npm run lint`, `npm run type-check`; requires Node.js 20.x; uses `actions/setup-node` with npm cache.
3. Write `.github/workflows/test-unit.yml`: triggers on `push` and `pull_request`; jobs: install deps via `uv sync`, run `pytest tests/ -x --tb=short`; uses SQLite in-memory (no external services required); matrix: Python 3.12 only.
4. Write `.github/workflows/deploy.yml`: stub only — triggers on push to `main`, contains a single `echo "Deploy placeholder"` step. Real deploy steps are added in Phase 7 (T-070).
5. Push to a `ci/scaffold` branch and verify all three live workflows pass (green) before merging to `main`.

**Data Impact**

Schema changes: None  
Migration required: No

**Test Plan**

Unit tests: Empty pytest suite must report `0 passed, 0 failed`  
Integration tests: None  
Manual verification steps:

- All three CI jobs appear green in the GitHub Actions tab on the scaffold PR
- `lint-backend` reports `All checks passed` with zero ruff errors and zero mypy errors
- `test-unit` completes in under 60 seconds with zero tests run

**Acceptance Criteria**

- All three CI workflows pass green on the empty scaffold
- `uv.lock` hash-based caching works — second CI run installs dependencies from cache in under 30 seconds
- `deploy.yml` stub is present and non-blocking (placeholder step passes)
- Branch protection rules are configured: require all three CI checks to pass before merge to `main`
- No hardcoded secrets or tokens in any workflow file

**Rollback Strategy**

Disable the failing workflow file. CI failures are non-destructive — they block merges but do not affect the application.

**Estimated Complexity:** XS

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (fast)  
Recommended Mode: fast

Reason: GitHub Actions YAML configuration is mechanical and well-templated.

---

**Context Strategy**

Start new chat? No — continue from T-002 chat.

Required files to include as context:

- `09_TESTING_STRATEGY.md` (CI configuration section)

Architecture docs to reference:

- `09_TESTING_STRATEGY.md` CI pipeline section

Documents NOT required:

- All domain, schema, API, and frontend documents

---

---

#### Task ID: T-004

**Title:** Frontend Scaffold — Vite + TypeScript + React + Tailwind

**Phase:** 0

**Subsystem:** Frontend Infrastructure

**Description:**  
Initialize the frontend project using Vite + TypeScript + React 18. Configure Tailwind CSS with the project's custom color tokens and design system values. Set up ESLint and the TypeScript compiler. Create the application shell (`App.tsx`, `main.tsx`, `router.tsx`) with placeholder routes for all 4 pages. Implement the Zustand store with all 5 slice stubs (no logic yet). Create the Axios API client instance and WebSocket client stub.

**Scope Boundaries**

Files affected:

- `frontend/package.json`
- `frontend/vite.config.ts`
- `frontend/tsconfig.json`
- `frontend/tailwind.config.ts`
- `frontend/.eslintrc.cjs`
- `frontend/index.html`
- `frontend/src/main.tsx`
- `frontend/src/App.tsx`
- `frontend/src/router.tsx`
- `frontend/src/store/index.ts` + all 5 slice stubs
- `frontend/src/api/client.ts` + `frontend/src/api/websocket.ts` (stubs)

Modules affected:

- Frontend project structure and configuration only

Explicitly NOT touching:

- Any page components, feature components, API endpoint clients, or backend code

**Implementation Steps**

1. Initialize Vite project: `npm create vite@latest frontend -- --template react-ts`. Install all dependencies: `react-router-dom`, `zustand`, `axios`, `recharts`, `@dnd-kit/core`, `@dnd-kit/sortable`, `lucide-react`. Install dev dependencies: `tailwindcss`, `postcss`, `autoprefixer`, `@types/react`, `@types/react-dom`, `eslint`, `@typescript-eslint/parser`.
2. Configure `tailwind.config.ts` with custom color tokens from `00_PRODUCT_SPECIFICATION.md` design section: confidence badge colors (high=green-500, medium=yellow-400, low=red-400), decision label colors, dark background palette.
3. Write `router.tsx` with React Router v6 `createBrowserRouter`: 4 routes (`/` → `PlaygroundPage`, `/analytics` → `AnalyticsDashboardPage`, `/requests` → `RequestExplorerPage`, `/kb` → `KnowledgeBasePage`). Each route renders a placeholder `<div>` with the page name — no real components yet.
4. Write Zustand store in `store/index.ts` combining 5 slices: `playgroundSlice`, `analyticsSlice`, `requestsSlice`, `kbSlice`, `policySlice`. Each slice stub exports its interface with all fields typed as `null | undefined` and no-op action functions.
5. Write `api/client.ts`: Axios instance with `baseURL` from `import.meta.env.VITE_API_URL`, request interceptor that injects `X-Session-ID` header from `sessionStorage`, response interceptor that maps HTTP errors to typed `ApiError` objects.
6. Write `api/websocket.ts`: `WebSocketClient` class stub with `connect(requestId)`, `disconnect()`, `onMessage(handler)` interface — no real WebSocket logic yet.
7. Run `npm run type-check` and `npm run lint` — both must pass on the scaffold.

**Data Impact**

Schema changes: None  
Migration required: No

**Test Plan**

Unit tests: None  
Integration tests: None  
Manual verification steps:

- `npm run dev` starts Vite dev server without errors
- Navigating to `/`, `/analytics`, `/requests`, `/kb` all render without console errors
- `npm run type-check` reports zero errors
- `npm run lint` reports zero errors

**Acceptance Criteria**

- Vite dev server starts and serves 4 placeholder pages
- All 5 Zustand store slices are typed with no `any` types
- `npm run build` produces a production bundle without warnings
- `npm run type-check` passes
- Tailwind color tokens are defined and usable in components
- No component logic exists yet — scaffold only

**Rollback Strategy**

Delete the `frontend/` directory and reinitialize. No application state exists at this point.

**Estimated Complexity:** S

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (fast)  
Recommended Mode: fast

Reason: Frontend scaffolding is mechanical. The structure follows standard Vite + React + TypeScript conventions.

---

**Context Strategy**

Start new chat? Yes — frontend is a separate subsystem from the backend infrastructure tasks in T-001 through T-003.

Required files to include as context:

- `05_APPLICATION_STRUCTURE.md` (frontend directory section)
- `00_PRODUCT_SPECIFICATION.md` (UX architecture and UI spec sections only)

Architecture docs to reference:

- `05_APPLICATION_STRUCTURE.md` frontend section
- `02_TECH_DECISIONS.md` TD-03 (React/Vite), TD-22 (Zustand)

Documents NOT required:

- All backend, schema, domain, security, and deployment documents

---

---

#### Task ID: T-005

**Title:** Alembic Environment Initialization

**Phase:** 0

**Subsystem:** Database Infrastructure

**Description:**  
Initialize Alembic for the backend project. Configure `alembic.ini` and `alembic/env.py` for async SQLAlchemy with both SQLite and PostgreSQL support. Write the async migration runner that works with `asyncpg` (PostgreSQL) and `aiosqlite` (SQLite). The migration environment must be functional — `alembic current` reports a clean baseline — before any migration files are written in Phase 1.

**Scope Boundaries**

Files affected:

- `backend/alembic.ini`
- `backend/alembic/env.py`
- `backend/alembic/script.py.mako`
- `backend/alembic/versions/` (empty directory, `.gitkeep`)

Modules affected:

- Database infrastructure configuration only

Explicitly NOT touching:

- ORM models, repositories, application code, domain code, or any migration files

**Implementation Steps**

1. Run `alembic init alembic` inside `backend/`. Update `alembic.ini`: set `script_location = alembic`, set `sqlalchemy.url` to a placeholder (will be overridden by `env.py`), configure `file_template = %%(year)d%%(month).2d%%(day).2d_%%(rev)s_%%(slug)s`.
2. Rewrite `alembic/env.py` for async execution: import `asyncio`, `AsyncEngine`, `create_async_engine` from SQLAlchemy. Pull `DATABASE_URL` from `AppConfig`. Implement `run_async_migrations()` using `connectable.connect()` with `run_sync(do_run_migrations)`. Support both `aiosqlite` (SQLite) and `asyncpg` (PostgreSQL) driver prefixes via URL scheme detection.
3. Configure `target_metadata = None` (will be set to `Base.metadata` after ORM models exist in T-007). Leave a clear `TODO: import ORM Base here` comment.
4. Test: `alembic current` returns `<empty>` (no head revision yet — correct for an empty versions directory).
5. Test: `alembic history` returns empty with no errors.
6. Verify SQLite path: `DATABASE_URL=sqlite+aiosqlite:///./test.db alembic current` runs without import errors.

**Data Impact**

Schema changes: None  
Migration required: No — this task establishes the migration environment; no migration files are written here.

**Test Plan**

Unit tests: None  
Integration tests: `pytest tests/migration/test_env.py` — verify `alembic current` runs without error and reports no applied revisions.  
Manual verification steps:

- `alembic current` exits 0 with no output (no revisions applied)
- `alembic history` exits 0 with no output (no migration files)
- No import errors on `alembic env.py` load

**Acceptance Criteria**

- `alembic current` runs cleanly against a fresh SQLite file
- `alembic env.py` loads without importing ORM models (deferred import pattern)
- URL switching between SQLite and PostgreSQL is handled without code changes (env var only)
- `alembic/versions/` directory exists and is tracked in git (via `.gitkeep`)
- No circular imports introduced

**Rollback Strategy**

Delete `alembic/` directory and `alembic.ini`. Re-initialize from scratch. No data exists at this stage.

**Estimated Complexity:** XS

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (thinking)  
Recommended Mode: thinking

Reason: Async Alembic configuration with dual-driver support (aiosqlite + asyncpg) has subtle correctness requirements. `env.py` must handle the async/sync bridge correctly — errors here cause all future migrations to fail silently or with cryptic errors.

---

**Context Strategy**

Start new chat? Yes — this is database infrastructure; separate subsystem from frontend (T-004).

Required files to include as context:

- `03_DATABASE_SCHEMA.md` (schema philosophy section only)
- `02_TECH_DECISIONS.md` (TD-06 database, TD-07 ORM)

Architecture docs to reference:

- `02_TECH_DECISIONS.md` TD-06 and TD-07

Documents NOT required:

- Domain design docs, API docs, frontend docs, security docs

---

---

### Phase 1 — Database Layer

---

#### Task ID: T-006

**Title:** Initial Alembic Migration — All 10 Tables

**Phase:** 1

**Subsystem:** Database Layer

**Description:**  
Write the single `0001_initial_schema.py` Alembic migration that creates all 10 database tables with their complete column definitions, data types, CHECK constraints, UNIQUE constraints, foreign key relationships, and indexes. This migration is the canonical data contract for the entire system. It must pass on both SQLite and PostgreSQL.

**Scope Boundaries**

Files affected:

- `backend/alembic/versions/0001_initial_schema.py`

Modules affected:

- Database migration only

Explicitly NOT touching:

- ORM models, repositories, application code, domain code, API code, frontend

**Implementation Steps**

1. Create `alembic/versions/0001_initial_schema.py`. Set `revision = '0001'`, `down_revision = None`.
2. In `upgrade()`, create tables in dependency order (tables with no FK dependencies first): `sessions`, `policy_snapshots`, `kb_documents`, `analytics_counters`, then `requests`, then `pipeline_traces`, `request_claims`, `safety_filter_results`, `claim_evidence`, `kb_chunks`.
3. For each table, define every column from `03_DATABASE_SCHEMA.md` with: exact column name, SQLAlchemy type, nullability, default value, and all CHECK constraints as named `sa.CheckConstraint` objects.
4. Define all foreign keys with explicit `ON DELETE` behavior: `CASCADE` where specified in the schema, `SET NULL` for optional FKs.
5. Create all indexes from the schema document using `op.create_index()` with the exact index names specified.
6. Implement `downgrade()` as explicit `op.drop_table()` calls in reverse dependency order. Downgrade must be a clean no-op from an application perspective (no data loss possible on a fresh install).
7. Run `alembic upgrade head` against a test SQLite database and verify with `sqlite3 test.db ".schema"` that all tables and indexes are created correctly.

**Data Impact**

Schema changes: Creates all 10 tables for the first time  
Migration required: Yes — this IS the migration

**Test Plan**

Unit tests: None  
Integration tests:

- `pytest tests/migration/test_0001_initial_schema.py`: verify all 10 tables exist post-upgrade
- Verify all FK relationships are enforced (insert orphan row → expect FK violation)
- Verify all CHECK constraints are enforced (insert out-of-range value → expect constraint violation)
- Verify all indexes exist (`sqlite_master` / `information_schema.indexes` query)
- Verify `alembic downgrade base` drops all tables cleanly
Manual verification steps:
- `alembic upgrade head` and `alembic downgrade base` both complete without errors on a fresh SQLite file
- `alembic history` shows one revision: `0001`

**Acceptance Criteria**

- All 10 tables are created with the exact column names, types, and constraints from `03_DATABASE_SCHEMA.md`
- All FK constraints are enforced (tested with FK violation inserts)
- All CHECK constraints are enforced (tested with boundary violation inserts)
- All 15+ indexes are created with the names from the schema document
- `alembic downgrade base` drops all tables with no errors
- Migration file is idempotent: running `upgrade` twice produces the same schema (Alembic revision state prevents double-apply)
- `mypy` reports zero errors on the migration file

**Rollback Strategy**

Run `alembic downgrade base` to drop all tables. Delete the migration file and re-write. No application data exists at this stage.

**Estimated Complexity:** M

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (thinking)  
Recommended Mode: thinking

Reason: Correctness of 10 interdependent tables with FKs, CHECK constraints, and indexes requires careful constraint ordering and SQLite/PostgreSQL compatibility verification. Errors here require a new migration to correct.

---

**Context Strategy**

Start new chat? No — continue from T-005 chat (same database subsystem).

Required files to include as context:

- `03_DATABASE_SCHEMA.md` (complete — all table definitions are needed)
- `02_TECH_DECISIONS.md` (TD-06, TD-07)

Architecture docs to reference:

- `03_DATABASE_SCHEMA.md` sections 2 and 3 (complete entity definitions)

Documents NOT required:

- Domain design, application structure, API, frontend, security, deployment docs

---

---

#### Task ID: T-007

**Title:** SQLAlchemy ORM Models for All 10 Tables

**Phase:** 1

**Subsystem:** Database Layer

**Description:**  
Implement `backend/src/sentinel/infrastructure/db/models.py` — SQLAlchemy 2.x declarative ORM models mapping all 10 database tables. Every column, relationship, and constraint from the migration must have a corresponding ORM definition. Update `alembic/env.py` to import `Base.metadata` for autogenerate support.

**Scope Boundaries**

Files affected:

- `backend/src/sentinel/infrastructure/db/models.py`
- `backend/src/sentinel/infrastructure/db/engine.py` (async engine + session factory)
- `backend/alembic/env.py` (add `target_metadata = Base.metadata`)

Modules affected:

- `sentinel.infrastructure.db` package only

Explicitly NOT touching:

- Domain models, repositories, application code, API code, or migration files

**Implementation Steps**

1. Write `infrastructure/db/engine.py`: `create_async_engine()` with `DATABASE_URL` from `AppConfig`, `echo=False` in production, WAL journal mode pragma for SQLite. Write `AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)`.
2. Write `infrastructure/db/models.py`: `DeclarativeBase` subclass `Base`. For each of the 10 tables, write a mapped class using SQLAlchemy 2.x `Mapped[T]` annotation style. Define all columns with exact types (`String`, `Integer`, `Float`, `DateTime`, `Boolean`). Define `relationship()` for all FK-linked tables (one-to-many with `back_populates`).
3. Use SQLAlchemy `JSON` type for all JSON columns (`restricted_categories`, `module_flags`, `fallback_priority`, `stage_metadata_json`, `confidence_signal_breakdown`). Ensure SQLite-compatible JSON storage.
4. Define `__tablename__` for each model matching the migration table names exactly.
5. Update `alembic/env.py`: import `Base` from `sentinel.infrastructure.db.models` and set `target_metadata = Base.metadata`.
6. Run `alembic check` — it must report no schema drift (ORM matches migration).

**Data Impact**

Schema changes: None — models map to the existing migration; no new migration is generated  
Migration required: No

**Test Plan**

Unit tests: None (ORM models are data declarations, not logic)  
Integration tests:

- `pytest tests/integration/db/test_orm_models.py`: insert one row per table, read it back, assert field equality
- Verify JSON columns round-trip correctly (insert dict, read back as dict)
- Verify FK cascade: delete a session row, assert all child records are deleted
Manual verification steps:
- `alembic check` reports "No new upgrade operations detected" (ORM matches migration)

**Acceptance Criteria**

- All 10 ORM models are defined with `Mapped[T]` typed columns
- All `relationship()` definitions have matching `back_populates` on both sides
- JSON columns store and retrieve Python `dict`/`list` values without manual serialization
- `alembic check` reports no schema drift
- `mypy src/sentinel/infrastructure/db/models.py` reports zero errors
- ORM insert + read round-trip test passes for all 10 models

**Rollback Strategy**

Remove the models file. The database schema is unaffected — migrations are independent of ORM model definitions.

**Estimated Complexity:** M

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (fast)  
Recommended Mode: fast

Reason: ORM model generation from a complete schema document is mechanical. The schema is fully specified in `03_DATABASE_SCHEMA.md` — this is transcription, not design.

---

**Context Strategy**

Start new chat? No — continue from T-006 chat.

Required files to include as context:

- `03_DATABASE_SCHEMA.md` (complete table definitions)

Architecture docs to reference:

- `03_DATABASE_SCHEMA.md` section 3 (complete entity definitions)
- `02_TECH_DECISIONS.md` TD-07 (SQLAlchemy 2.x async)

Documents NOT required:

- Domain, application, API, frontend, security, deployment docs

---

---

#### Task ID: T-008

**Title:** Repository Base Class and Interface Definitions

**Phase:** 1

**Subsystem:** Database Layer

**Description:**  
Define the repository interface protocol (abstract base), implement a `BaseRepository` class with shared session lifecycle management, and write stub `NotImplementedError` implementations for all 5 concrete repositories. This establishes the interface contract that both the application layer (Phase 4) and infrastructure implementations (Phase 3) depend on.

**Scope Boundaries**

Files affected:

- `backend/src/sentinel/infrastructure/db/repositories/base.py`
- `backend/src/sentinel/infrastructure/db/repositories/request_repo.py` (interface + stub)
- `backend/src/sentinel/infrastructure/db/repositories/session_repo.py` (interface + stub)
- `backend/src/sentinel/infrastructure/db/repositories/kb_repo.py` (interface + stub)
- `backend/src/sentinel/infrastructure/db/repositories/analytics_repo.py` (interface + stub)
- `backend/src/sentinel/infrastructure/db/repositories/policy_repo.py` (interface + stub)

Modules affected:

- `sentinel.infrastructure.db.repositories` package

Explicitly NOT touching:

- Domain models, application use cases, API code, ORM model internals, migration files

**Implementation Steps**

1. Write `base.py`: `BaseRepository` class accepting `AsyncSession` via constructor injection. Implement `_commit()`, `_rollback()`, `_flush()` helper methods. Define a `@contextmanager` `_transaction()` that wraps operations in `async with session.begin()`.
2. For each of the 5 repository files, write an interface Protocol class and a concrete stub class:
   - Protocol defines all method signatures with typed parameters and return types
   - Concrete stub class inherits `BaseRepository` and raises `NotImplementedError` for all methods
   - Method signatures must match the full interface as derived from `03_DATABASE_SCHEMA.md` and `05_APPLICATION_STRUCTURE.md`
3. `RequestRepository` interface methods: `create()`, `get_by_id()`, `list_by_session()`, `update_status()`, `update_completed()`, `get_for_export()`.
4. `SessionRepository` interface methods: `create_or_get()`, `update_last_active()`, `get_by_id()`.
5. `KBRepository` interface methods: `create_document()`, `update_document_status()`, `get_document()`, `list_documents_by_session()`, `create_chunk()`, `get_chunks_by_document()`, `get_chunk_by_faiss_id()`.
6. `AnalyticsRepository` interface methods: `upsert_counters()`, `get_summary_by_session()`, `get_daily_breakdown()`.
7. `PolicyRepository` interface methods: `create_snapshot()`, `get_latest_for_session()`, `get_by_id()`.
8. Run `mypy` on all repository files — zero errors required.

**Data Impact**

Schema changes: None  
Migration required: No

**Test Plan**

Unit tests: None (stubs raise `NotImplementedError` — tested by inspection only at this stage)  
Integration tests: None yet (implementations are stubs)  
Manual verification steps:

- All 5 repository stubs instantiate without errors when passed a mock `AsyncSession`
- `mypy` reports zero errors on all repository files

**Acceptance Criteria**

- All 5 repository interfaces are fully typed with no `Any` types
- All method signatures accept and return domain-appropriate types (UUIDs as `str`, not raw ints)
- `BaseRepository` session management is fully async-correct (no blocking calls)
- `mypy src/sentinel/infrastructure/db/repositories/` reports zero errors
- Stubs are committable and the application layer can import and call them without runtime errors (they raise `NotImplementedError`, which is the expected behavior at this stage)

**Rollback Strategy**

Delete the repository files. Application layer code that imports them will break immediately, making the rollback obvious and safe.

**Estimated Complexity:** S

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (fast)  
Recommended Mode: fast

Reason: Repository interface generation from a schema document is mechanical. Typing discipline is enforced by mypy, not by the generation model.

---

**Context Strategy**

Start new chat? No — continue from T-007 chat.

Required files to include as context:

- `03_DATABASE_SCHEMA.md` (table definitions and field names)
- `05_APPLICATION_STRUCTURE.md` (repository file list)

Architecture docs to reference:

- `03_DATABASE_SCHEMA.md` table definitions

Documents NOT required:

- Domain engine design, API docs, frontend docs

---

---

#### Task ID: T-009

**Title:** Database Layer Migration Test Suite

**Phase:** 1

**Subsystem:** Database Layer — Testing

**Description:**  
Write the complete migration test suite (`tests/migration/`) that verifies the database schema is exactly as specified. This suite runs `alembic upgrade head` against an in-memory SQLite database, then asserts every table, column, constraint, and index exists. This is the Phase 1 completion gate — the suite must pass before Phase 2 begins.

**Scope Boundaries**

Files affected:

- `tests/migration/conftest.py` (test database fixture)
- `tests/migration/test_0001_schema.py`
- `tests/migration/test_constraints.py`
- `tests/migration/test_indexes.py`

Modules affected:

- Test infrastructure only

Explicitly NOT touching:

- Migration files, ORM models, repository code, application code

**Implementation Steps**

1. Write `conftest.py`: pytest fixture `migrated_db` that creates a fresh SQLite in-memory engine, runs `alembic upgrade head` programmatically via `command.upgrade(alembic_cfg, "head")`, yields the engine, and tears it down.
2. Write `test_0001_schema.py`: for each of the 10 tables, assert:
   - Table exists (`inspect(engine).has_table(table_name)`)
   - All expected columns exist with correct types
   - All expected nullable/NOT NULL constraints are correct
   - All expected DEFAULT values are present
3. Write `test_constraints.py`: for each CHECK constraint and FK constraint, attempt an insertion that violates it and assert the appropriate `IntegrityError` is raised. Cover:
   - `policy_snapshots`: `warn >= accept` threshold violation
   - `requests`: invalid `model_provider` value
   - `requests`: invalid `status` value
   - `kb_documents`: FK violation (orphan document without parent session)
   - `claim_evidence`: FK cascade delete (delete request → claim_evidence deleted)
4. Write `test_indexes.py`: query `sqlite_master` for all expected index names and assert they exist.
5. Run `pytest tests/migration/ -v` — all tests must pass.

**Data Impact**

Schema changes: None  
Migration required: No (tests run migrations, not create them)

**Test Plan**

Unit tests: Not applicable  
Integration tests: This entire task IS the integration test suite  
Manual verification steps:

- `pytest tests/migration/ -v` passes with all tests green
- Test run completes in under 10 seconds (in-memory SQLite)

**Acceptance Criteria**

- All 10 tables verified for existence and column structure
- All CHECK constraints verified via violation-insertion tests
- All FK CASCADE behaviors verified
- All indexes verified by name
- `alembic downgrade base` verified: all tables dropped, `alembic upgrade head` re-creates them cleanly
- Test suite runs in under 10 seconds
- Zero test failures

**Rollback Strategy**

Migration test failures do not affect application state. Fix the underlying migration or ORM model and re-run.

**Estimated Complexity:** S

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (fast)  
Recommended Mode: fast

Reason: Test generation from a schema document is mechanical — each test is a direct assertion of a schema property.

---

**Context Strategy**

Start new chat? No — continue from T-008 chat (same database subsystem).

Required files to include as context:

- `03_DATABASE_SCHEMA.md` (all table definitions and constraints)
- `09_TESTING_STRATEGY.md` (migration test section)

Architecture docs to reference:

- `03_DATABASE_SCHEMA.md` section 3 (complete entity definitions)

Documents NOT required:

- Domain, application, API, frontend, security, deployment docs

---

---

### Phase 2 — Domain Engine

---

#### Task ID: T-010

**Title:** Core Domain Value Objects and PipelineContext

**Phase:** 2

**Subsystem:** Domain Engine

**Description:**  
Implement all domain value objects and the `PipelineContext` accumulator as defined in `04_DOMAIN_ENGINE_DESIGN.md` section 2. These are the data contracts shared by every pipeline stage. Frozen dataclasses for value objects; mutable dataclass for `PipelineContext`. Also implement the domain exception hierarchy. Write unit tests confirming immutability, field validation, and `PipelineContext` state transition correctness.

**Scope Boundaries**

Files affected:

- `backend/src/sentinel/domain/models/claim.py`
- `backend/src/sentinel/domain/models/evidence.py`
- `backend/src/sentinel/domain/models/confidence.py`
- `backend/src/sentinel/domain/models/decision.py`
- `backend/src/sentinel/domain/models/policy.py`
- `backend/src/sentinel/domain/models/pipeline_context.py`
- `backend/src/sentinel/domain/exceptions.py`
- `tests/unit/domain/test_models.py`

Modules affected:

- `sentinel.domain.models` package

Explicitly NOT touching:

- Domain engines, infrastructure, application, API, or frontend

**Implementation Steps**

1. Implement all frozen dataclasses from `04_DOMAIN_ENGINE_DESIGN.md` section 2: `Claim`, `Evidence`, `ClaimVerificationResult`, `SafetyFilterResult`, `ConfidenceScore`, `GuardrailDecision`, `PromptValidationResult`, `TraceStage`. Use `@dataclass(frozen=True)` for all value objects.
2. Implement `PolicySnapshot` as a non-frozen dataclass (mutable — users can update thresholds). Add `__post_init__` validation: assert `block_threshold < warn_threshold < accept_threshold`; raise `ValueError` with descriptive message on violation.
3. Implement `PipelineContext` as a mutable dataclass with `field(default_factory=...)` for all list and dict fields. Add a `mark_terminal()` method that sets `is_terminal = True` and `retry_requested = False`. Add `request_retry(strategy: str)` method that sets `retry_requested = True` and `fallback_strategy_applied = strategy`.
4. Implement `domain/exceptions.py`: `SentinelBaseError`, `PipelineStageError(stage_name, cause)`, `LLMTimeoutError`, `LLMUnavailableError`, `EmbeddingError`, `KBNotFoundError`, `PolicyViolationError`, `ValidationError`. Each exception carries structured context fields for logging.
5. Write `tests/unit/domain/test_models.py`: test frozen value object immutability (attempt field assignment → assert `FrozenInstanceError`), `PolicySnapshot` validation (5 boundary test cases), `PipelineContext` state transitions (`mark_terminal`, `request_retry`), `TraceStage` creation.

**Data Impact**

Schema changes: None  
Migration required: No

**Test Plan**

Unit tests:

- Frozen dataclass immutability (all value object classes)
- `PolicySnapshot` threshold validation: `block < warn < accept` boundary cases (equal values, reversed values, valid values)
- `PipelineContext.mark_terminal()`: `is_terminal=True`, `retry_requested=False`
- `PipelineContext.request_retry("retry_prompt")`: `retry_requested=True`, `fallback_strategy_applied="retry_prompt"`
- All exception classes instantiate with correct fields
Integration tests: None  
Manual verification steps:
- `mypy src/sentinel/domain/` reports zero errors

**Acceptance Criteria**

- All value objects are `frozen=True`; mutation raises `FrozenInstanceError`
- `PolicySnapshot` raises `ValueError` when `warn >= accept` or `block >= warn`
- `PipelineContext` initializes with all defaults (no required args beyond the 8 constructor params)
- All list/dict fields initialize as empty (not `None`, not shared mutable defaults)
- Domain exceptions carry structured fields accessible for structlog context
- `mypy src/sentinel/domain/models/` reports zero errors
- `pytest tests/unit/domain/test_models.py` passes (100% coverage on this file)

**Rollback Strategy**

Domain models have no I/O side effects. Remove the files; upstream code that imports them fails immediately and explicitly.

**Estimated Complexity:** S

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (thinking)  
Recommended Mode: thinking

Reason: `PipelineContext` field design and `PolicySnapshot` validation logic involve correctness constraints that affect every downstream task. The exception hierarchy must be precisely structured for the error handler mapping in Phase 5.

---

**Context Strategy**

Start new chat? Yes — entering the domain engine subsystem. Fresh context, no database or infrastructure files needed.

Required files to include as context:

- `04_DOMAIN_ENGINE_DESIGN.md` (section 2: domain model definitions)

Architecture docs to reference:

- `04_DOMAIN_ENGINE_DESIGN.md` sections 2 and 3

Documents NOT required:

- `03_DATABASE_SCHEMA.md`, `05_APPLICATION_STRUCTURE.md`, `06_AUTOMATION_AND_AI_INTEGRATION.md`, infrastructure, API, frontend, deployment docs

---

---

#### Task ID: T-011

**Title:** InjectionDetector and PIIDetector

**Phase:** 2

**Subsystem:** Domain Engine — Prompt Validation

**Description:**  
Implement `InjectionDetector` and `PIIDetector` as pure Python classes with no I/O. `InjectionDetector` implements block/flag pattern matching against all specified patterns. `PIIDetector` implements 6 pattern types with masking. Both classes take a prompt string and return a structured result value object. Write a comprehensive unit test suite covering all patterns and edge cases.

**Scope Boundaries**

Files affected:

- `backend/src/sentinel/domain/engines/prompt_validation/injection_detector.py`
- `backend/src/sentinel/domain/engines/prompt_validation/pii_detector.py`
- `tests/unit/domain/test_injection_detector.py`
- `tests/unit/domain/test_pii_detector.py`

Modules affected:

- `sentinel.domain.engines.prompt_validation`

Explicitly NOT touching:

- PolicyFilter, RiskScorer, orchestrator, infrastructure, application, API, frontend

**Implementation Steps**

1. Implement `InjectionDetector` from `04_DOMAIN_ENGINE_DESIGN.md` section 4.2: compile all `BLOCK_PATTERNS` and `FLAG_PATTERNS` as `re.compile()` at class instantiation (not per-call). `check(prompt: str) -> InjectionCheckResult`. Normalize prompt before matching: lowercase + collapse whitespace. Return `InjectionCheckResult` frozen dataclass with `status` and `detail`.
2. Implement `PIIDetector` from `04_DOMAIN_ENGINE_DESIGN.md` section 4.3: all 6 pattern types (`email`, `phone_us`, `ssn`, `credit_card`, `api_key`, `ipv4`). Compile patterns at instantiation. `check(prompt: str) -> PIICheckResult` returns detected types. `mask(prompt: str) -> str` replaces detected PII with `[REDACTED_<TYPE>]`. Ensure masking does not corrupt surrounding text (test with multi-PII prompts).
3. Write `test_injection_detector.py`: one positive test per `BLOCK_PATTERN` (confirms block), one positive test per `FLAG_PATTERN` (confirms flag), 5 clean prompts (confirm pass), 3 edge cases (empty string, unicode text, code snippet that should not false-positive on `system:` in a comment).
4. Write `test_pii_detector.py`: one positive test per PII type (confirms detection), masking round-trip test (masked text contains no original PII), multi-PII prompt (email + phone simultaneously detected), false-positive guard (IPv4-like version string `1.2.3.4` in a software context), empty prompt.

**Data Impact**

Schema changes: None  
Migration required: No

**Test Plan**

Unit tests:

- 8 BLOCK_PATTERN positive tests (one per pattern)
- 6 FLAG_PATTERN positive tests (one per pattern)
- 5 clean prompt negative tests
- 3 edge case tests (empty, unicode, code context)
- 6 PII type detection tests
- 3 masking correctness tests
- 2 false-positive guard tests
Integration tests: None  
Manual verification steps:
- `pytest tests/unit/domain/test_injection_detector.py tests/unit/domain/test_pii_detector.py -v` passes

**Acceptance Criteria**

- All 8 BLOCK patterns match their intended injection strings
- All 6 FLAG patterns match their intended suspicious strings
- PII masking replaces all detected PII tokens with `[REDACTED_<TYPE>]`
- No PII detector false-positive on a normal code snippet (IPv4 in a software dependency string)
- All regex patterns are compiled at class init time (not per `check()` call)
- `mypy` reports zero errors on both files
- `pytest --cov=sentinel/domain/engines/prompt_validation` achieves ≥ 95% line coverage

**Rollback Strategy**

These are pure functions with no side effects. Remove the files; the `PromptValidationEngine` (T-012) that calls them will fail to import.

**Estimated Complexity:** M

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (thinking)  
Recommended Mode: thinking

Reason: PII regex pattern design involves correctness tradeoffs between false positives and false negatives. The `api_key` pattern in particular must not false-positive on common code content. Pattern tuning requires reasoning, not generation.

---

**Context Strategy**

Start new chat? No — continue from T-010 chat (same domain subsystem).

Required files to include as context:

- `04_DOMAIN_ENGINE_DESIGN.md` (sections 4.2 and 4.3 specifically)

Architecture docs to reference:

- `04_DOMAIN_ENGINE_DESIGN.md` section 4 (Prompt Validation Engine)

Documents NOT required:

- Schema docs, infrastructure, application, API, frontend, security, deployment docs

---

---

#### Task ID: T-012

**Title:** PolicyFilter, RiskScorer, and PromptValidationEngine

**Phase:** 2

**Subsystem:** Domain Engine — Prompt Validation

**Description:**  
Implement `PolicyFilter` (restricted category check), `RiskScorer` (weighted signal aggregation), and `PromptValidationEngine` (composes all four validation components into a single `validate(context) -> PipelineContext` call). These three classes complete the Prompt Validation stage of the pipeline.

**Scope Boundaries**

Files affected:

- `backend/src/sentinel/domain/engines/prompt_validation/policy_filter.py`
- `backend/src/sentinel/domain/engines/prompt_validation/risk_scorer.py`
- `backend/src/sentinel/domain/engines/prompt_validation/__init__.py` (exports `PromptValidationEngine`)
- `tests/unit/domain/test_policy_filter.py`
- `tests/unit/domain/test_risk_scorer.py`
- `tests/unit/domain/test_prompt_validation_engine.py`

Modules affected:

- `sentinel.domain.engines.prompt_validation`

Explicitly NOT touching:

- LLM execution, hallucination engine, safety filter, confidence scoring, decision engine, infrastructure, application, API, frontend

**Implementation Steps**

1. Implement `PolicyFilter.check(prompt: str, policy: PolicySnapshot) -> PolicyCheckResult`: check if prompt text contains any string from `policy.restricted_categories`. Case-insensitive substring match. Return `PolicyCheckResult(status, violated_category)`.
2. Implement `RiskScorer.score(injection_result, pii_result, policy_result) -> int` (0–100 weighted aggregate): injection block = +60, injection flag = +30, pii flag = +15, policy block = +50. Sum, clamp to 100. Return integer score.
3. Implement `PromptValidationEngine.validate(context: PipelineContext) -> PipelineContext` composing the four sub-components: call `InjectionDetector`, `PIIDetector`, `PolicyFilter`, `RiskScorer`. Assemble `PromptValidationResult`. If `overall_status == 'block'`, call `context.mark_terminal()` and populate `context.guardrail_decision` with a block decision. Return updated context.
4. Write `test_prompt_validation_engine.py`: test injection block → terminal context (no LLM call flag), PII flag → non-terminal context with masked prompt, policy block → terminal context, clean prompt → pass with risk_score < 20.

**Data Impact**

Schema changes: None  
Migration required: No

**Test Plan**

Unit tests:

- `PolicyFilter`: restricted category match (case-insensitive), no match (pass), empty categories list (pass)
- `RiskScorer`: all four signal combinations (injection block + PII = verify sum), zero signals = 0, all signals = 100 (capped)
- `PromptValidationEngine`: injection block propagates to terminal context, PII flag sets `pii_detected`, clean prompt returns pass, high risk score (≥ 80) blocks even without individual block flag
Integration tests: None  
Manual verification steps:
- `pytest tests/unit/domain/ -v` all passing

**Acceptance Criteria**

- `PromptValidationEngine.validate()` returns a `PipelineContext` with `validation_result` populated
- Injection-blocked context has `is_terminal=True` and `guardrail_decision` set
- PII-flagged context has `masked_prompt` containing `[REDACTED_*]` tokens
- `RiskScorer` output is always in range [0, 100]
- All sub-components are injected via constructor (no module-level singletons)
- `mypy` reports zero errors on all three files
- ≥ 95% line coverage on `PromptValidationEngine`

**Rollback Strategy**

Pure functions with no I/O. Remove or revert files; errors are immediate import failures.

**Estimated Complexity:** S

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (fast)  
Recommended Mode: fast

Reason: Structure is specified in the design document. The weighting formula is given — this is implementation, not design.

---

**Context Strategy**

Start new chat? No — continue from T-011 chat.

Required files to include as context:

- `04_DOMAIN_ENGINE_DESIGN.md` (sections 4.1 through 4.5)

Architecture docs to reference:

- `04_DOMAIN_ENGINE_DESIGN.md` section 4 (Prompt Validation Engine business rules)

Documents NOT required:

- Schema docs, infrastructure, API, frontend docs

---

---

#### Task ID: T-013

**Title:** ConfidenceScoringEngine

**Phase:** 2

**Subsystem:** Domain Engine — Confidence Scoring

**Description:**  
Implement `ConfidenceScoringEngine` with the 4-signal weighted aggregation algorithm from `04_DOMAIN_ENGINE_DESIGN.md` section 7. This is a pure synchronous computation from `PipelineContext` state to a `ConfidenceScore`. The engine must be deterministic: same inputs always produce the same output. Write a comprehensive unit test suite covering all signal paths, neutral defaults, and boundary conditions.

**Scope Boundaries**

Files affected:

- `backend/src/sentinel/domain/engines/confidence_scoring.py`
- `tests/unit/domain/test_confidence_scoring.py`

Modules affected:

- `sentinel.domain.engines`

Explicitly NOT touching:

- Decision engine, prompt validation, hallucination engine, safety filter, infrastructure, application, API, frontend

**Implementation Steps**

1. Implement `ConfidenceScoringEngine.compute(context: PipelineContext) -> PipelineContext` exactly as specified in `04_DOMAIN_ENGINE_DESIGN.md` section 7.2. Implement all 4 signal computations in order: `evidence_similarity`, `claim_verification_ratio`, `claim_density_penalty`, `safety_penalty`.
2. Implement neutral defaults for missing inputs: empty `claim_results` → `evidence_similarity = 0.5`, `claim_verification_ratio = 0.5`; no response text → `claim_density_penalty = 1.0` (no penalty); no safety results → `safety_penalty = 1.0` (no penalty).
3. Weighted aggregation: `raw_score = sum(weight * signal for each signal)`. Clamp to [0.0, 1.0]. Scale to [0, 100] with `int(round(clamped * 100))`.
4. Label classification uses policy thresholds from `context.policy`: `score >= accept_threshold → 'high'`, `score >= warn_threshold → 'medium'`, else `'low'`.
5. Write `test_confidence_scoring.py`: determinism test (same context object, run twice, assert identical output), all-supported-claims test (expect high score), all-contradicted-claims test (expect low score), all-unsupported-claims test (expect low score), no-claims test (expect neutral ~50), safety-flagged test (expect score penalty), claim-density test (10 claims in 20-word response → density penalty applied), boundary test (score exactly equals accept_threshold → label 'high', score = accept_threshold - 1 → label 'medium').

**Data Impact**

Schema changes: None  
Migration required: No

**Test Plan**

Unit tests:

- 8 distinct scoring scenario tests as described above
- 1000-iteration randomized determinism test (same context → same output)
- Boundary test: `score == accept_threshold` → label `'high'`
- Boundary test: `score == warn_threshold` → label `'medium'`
- Boundary test: `score == warn_threshold - 1` → label `'low'`
Integration tests: None  
Manual verification steps:
- All tests pass; coverage ≥ 95%

**Acceptance Criteria**

- Engine is deterministic: identical inputs produce identical `ConfidenceScore.value` in all test runs
- `ConfidenceScore.value` is always an integer in [0, 100]
- `ConfidenceScore.signal_breakdown` contains all 4 signal keys with values in [0.0, 1.0]
- Neutral default for empty claims produces score near 50 (±5)
- All safety-flagged results reduce the score relative to the no-safety-flag baseline
- `mypy` reports zero errors
- `pytest --cov` achieves ≥ 95% coverage

**Rollback Strategy**

Pure function. Remove the file; `GuardrailDecisionEngine` (T-014) which depends on this will fail to import.

**Estimated Complexity:** M

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (thinking)  
Recommended Mode: thinking

Reason: The 4-signal weighted aggregation with neutral defaults and normalization requires careful arithmetic. The boundary condition between `score == accept_threshold` (high) vs `< accept_threshold` (medium) is a frequently buggy edge case requiring explicit reasoning.

---

**Context Strategy**

Start new chat? No — continue from T-012 chat.

Required files to include as context:

- `04_DOMAIN_ENGINE_DESIGN.md` (section 7 only: ConfidenceScoringEngine)

Architecture docs to reference:

- `04_DOMAIN_ENGINE_DESIGN.md` section 7

Documents NOT required:

- Schema docs, infrastructure, application, API, frontend docs

---

---

#### Task ID: T-014

**Title:** GuardrailDecisionEngine and FallbackStrategyEngine

**Phase:** 2

**Subsystem:** Domain Engine — Decision and Fallback

**Description:**  
Implement `GuardrailDecisionEngine` (priority-ordered rule evaluation that emits a `GuardrailDecision`) and `FallbackStrategyEngine` (applies one of 4 strategies to a `PipelineContext` for retry). These two engines complete the decision path of the pipeline. The decision engine's priority ordering (safety override → prompt validation block → confidence threshold) is a correctness invariant that must be verified by explicit tests.

**Scope Boundaries**

Files affected:

- `backend/src/sentinel/domain/engines/decision_engine.py`
- `backend/src/sentinel/domain/engines/fallback_strategy.py`
- `tests/unit/domain/test_decision_engine.py`
- `tests/unit/domain/test_fallback_strategy.py`

Modules affected:

- `sentinel.domain.engines`

Explicitly NOT touching:

- Confidence scoring engine, hallucination engine, prompt validation, infrastructure, application, API, frontend

**Implementation Steps**

1. Implement `GuardrailDecisionEngine.decide(context: PipelineContext) -> PipelineContext` following the priority rules from `04_DOMAIN_ENGINE_DESIGN.md` section 8: Rule 1 (safety override ≥ 0.7 score → block, `safety_filter_override=True`), Rule 2 (prompt validation block → block, defensive), Rule 3 (confidence ≥ accept_threshold → accept), Rule 4 (confidence ≥ warn_threshold → accept_with_warning), Rule 5 (confidence in fallback range → emit the first untried fallback strategy from `policy.fallback_priority` and set `retry_requested=True`), Rule 6 (confidence < block_threshold → block). Set `context.is_terminal = True` for all block decisions; `context.retry_requested = True` for all retry decisions.
2. Implement `FallbackStrategyEngine.apply(context: PipelineContext) -> PipelineContext` for all 4 strategies: `retry_prompt` (appends a clarification instruction to `masked_prompt`), `retry_lower_temp` (sets a temperature hint in context metadata), `rag_augmentation` (marks `rag_requested = True` in context for the orchestrator to handle), `alternate_model` (switches `model_name` in context if an alternate is configured).
3. Write `test_decision_engine.py`: safety override test (safety score 0.8 → block regardless of confidence 90), safety flag low-confidence test (safety score 0.5 → does NOT override), confidence accept test (score = accept_threshold → accept), confidence warn test (score = warn_threshold → accept_with_warning), retry dispatch test (score in fallback range → retry_requested True + first fallback strategy set), block threshold test (score = 0 → block), retry budget exhausted test (all 4 strategies already attempted → block with `MAX_RETRIES_EXCEEDED`).
4. Write `test_fallback_strategy.py`: one test per strategy type (verify the correct field mutation on context).

**Data Impact**

Schema changes: None  
Migration required: No

**Test Plan**

Unit tests:

- 7 decision engine scenario tests
- 4 fallback strategy mutation tests
- Safety override priority test (safety block beats confidence 100)
- Boundary: confidence exactly equal to each threshold
Integration tests: None  
Manual verification steps:
- `pytest tests/unit/domain/test_decision_engine.py -v` all passing

**Acceptance Criteria**

- Safety filter override ALWAYS produces a block decision when safety score ≥ 0.7, regardless of confidence score
- `GuardrailDecision.safety_filter_override` is `True` only when a safety filter caused the block
- Retry decision correctly cycles through `policy.fallback_priority` without repeating used strategies
- `context.is_terminal = True` is set on every block decision
- `context.retry_requested = True` is set on every retry decision
- `mypy` reports zero errors on both files
- ≥ 95% line coverage

**Rollback Strategy**

Pure functions. Remove files; pipeline orchestrator (Phase 4) which calls them will fail to import.

**Estimated Complexity:** M

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (thinking)  
Recommended Mode: thinking

Reason: The decision rule priority ordering is a complex multi-condition branching structure. The fallback strategy deduplication logic (not repeating already-tried strategies) requires careful state reasoning. Errors here are silent and produce wrong guardrail decisions.

---

**Context Strategy**

Start new chat? No — continue from T-013 chat.

Required files to include as context:

- `04_DOMAIN_ENGINE_DESIGN.md` (sections 8 and 9: Decision Engine and Fallback Strategy Engine)

Architecture docs to reference:

- `04_DOMAIN_ENGINE_DESIGN.md` sections 8 and 9

Documents NOT required:

- Schema docs, infrastructure, API, frontend, deployment docs

---

---

#### Task ID: T-015

**Title:** Domain Engine Unit Test Consolidation and Coverage Gate

**Phase:** 2

**Subsystem:** Domain Engine — Testing

**Description:**  
Consolidate all domain engine unit tests, run the full domain test suite, verify ≥ 95% line coverage on the entire `sentinel/domain/` package, and fix any gaps. This task is the Phase 2 completion gate. No new engine code is written here — only test additions for uncovered lines and final coverage verification.

**Scope Boundaries**

Files affected:

- `tests/unit/domain/conftest.py` (shared fixtures for domain tests)
- `tests/unit/domain/test_models.py` (additions if coverage gaps found)
- `tests/unit/domain/test_injection_detector.py` (additions if coverage gaps found)
- `tests/unit/domain/test_pii_detector.py` (additions if coverage gaps found)
- `tests/unit/domain/test_confidence_scoring.py` (additions if coverage gaps found)
- `tests/unit/domain/test_decision_engine.py` (additions if coverage gaps found)

Modules affected:

- Test infrastructure only; no production code changes

Explicitly NOT touching:

- Domain engine production files (only test files are modified)
- Infrastructure, application, API, or frontend

**Implementation Steps**

1. Run `pytest tests/unit/domain/ --cov=sentinel/domain --cov-report=term-missing`. Identify all uncovered lines.
2. For each uncovered line, determine the missing test case (typically an unexercised conditional branch or exception path). Write the missing test.
3. Specific common gaps to check: `PIIDetector` false-positive guard for `api_key` pattern, `ConfidenceScoringEngine` when `llm_response_text` is `None`, `GuardrailDecisionEngine` when `confidence_score` is `None` (should default to 0), all `domain/exceptions.py` exception string representations.
4. Write `conftest.py` with shared fixtures: `default_policy_snapshot()`, `minimal_pipeline_context(prompt)`, `blocked_pipeline_context()`, `accepted_pipeline_context()`. These fixtures are reused across all domain tests and prevent fixture duplication.
5. Re-run coverage check. Target: ≥ 95% line coverage on `sentinel/domain/`.
6. Run `mypy src/sentinel/domain/ --strict` — zero errors required.

**Data Impact**

Schema changes: None  
Migration required: No

**Test Plan**

Unit tests: See above — this task is test-only  
Integration tests: None  
Manual verification steps:

- `pytest tests/unit/domain/ --cov=sentinel/domain --cov-report=term-missing` shows ≥ 95% coverage
- `mypy src/sentinel/domain/ --strict` shows zero errors

**Acceptance Criteria**

- `pytest tests/unit/domain/` passes with zero failures
- `sentinel/domain/` line coverage ≥ 95% (enforced by `pytest-cov` `--cov-fail-under=95`)
- `mypy src/sentinel/domain/ --strict` reports zero errors
- All engines are stateless: `grep -r "self\." src/sentinel/domain/engines/ | grep -v "def \|__"` shows no mutable instance variables set after `__init__`
- Shared fixtures are defined in `conftest.py` and reused (no fixture duplication across test files)

**Rollback Strategy**

Test-only task. No production code is modified. Remove any failing new test cases and re-investigate the coverage gap.

**Estimated Complexity:** S

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (fast)  
Recommended Mode: fast

Reason: Coverage gap identification and test writing is mechanical once the uncovered lines are identified.

---

**Context Strategy**

Start new chat? No — continue from T-014 chat.

Required files to include as context:

- Coverage report output (paste the term-missing output)
- `04_DOMAIN_ENGINE_DESIGN.md` (relevant section for any gaps found)

Architecture docs to reference:

- Only as needed for specific uncovered branches

Documents NOT required:

- All infrastructure, schema, application, API, frontend, deployment docs

---

---

### Phase 3 — Infrastructure Adapters

---

#### Task ID: T-016

**Title:** SQLAlchemy Repository Implementations — Sessions, Policy, Analytics

**Phase:** 3

**Subsystem:** Infrastructure — Database Repositories

**Description:**  
Implement the full SQLAlchemy async repository classes for `SessionRepository`, `PolicyRepository`, and `AnalyticsRepository`. Replace the `NotImplementedError` stubs from T-008 with working database I/O implementations. These three repositories are the simplest (no complex queries) and establish the async SQLAlchemy session pattern for the remaining repositories.

**Scope Boundaries**

Files affected:

- `backend/src/sentinel/infrastructure/db/repositories/session_repo.py`
- `backend/src/sentinel/infrastructure/db/repositories/policy_repo.py`
- `backend/src/sentinel/infrastructure/db/repositories/analytics_repo.py`
- `tests/integration/db/test_session_repo.py`
- `tests/integration/db/test_policy_repo.py`
- `tests/integration/db/test_analytics_repo.py`

Modules affected:

- `sentinel.infrastructure.db.repositories`

Explicitly NOT touching:

- `RequestRepository`, `KBRepository`, domain models, application code, API code, FAISS, embedding adapters

**Implementation Steps**

1. Implement `SessionRepository.create_or_get(session_id: str) -> Session`: use `INSERT OR IGNORE` (SQLite) / `ON CONFLICT DO NOTHING` (PostgreSQL) to handle concurrent session creation. Return the session row.
2. Implement `SessionRepository.update_last_active(session_id: str)`: update `last_active_at` timestamp. Use `update().where().values()` — not read-then-write.
3. Implement `PolicyRepository.create_snapshot(session_id, policy: PolicySnapshot) -> str`: serialize `restricted_categories`, `fallback_priority`, `module_flags` to JSON strings before insert. Return the new snapshot UUID.
4. Implement `PolicyRepository.get_latest_for_session(session_id: str) -> PolicySnapshot | None`: query most recent snapshot ordered by `created_at DESC`; deserialize JSON fields back to Python types; return `PolicySnapshot` domain object.
5. Implement `AnalyticsRepository.upsert_counters(session_id, date_bucket, model_provider, model_name, delta: dict)`: SQLite `INSERT OR REPLACE` / PostgreSQL `INSERT ... ON CONFLICT DO UPDATE SET` pattern. The `delta` dict specifies increments for each counter column.
6. Write integration tests for each repository using an in-memory SQLite database seeded via the Alembic migration fixture from T-009.

**Data Impact**

Schema changes: None  
Migration required: No

**Test Plan**

Unit tests: None (repositories require database I/O; mocking is counterproductive here)  
Integration tests:

- `SessionRepository`: create session, get same session (idempotent), update last_active, concurrent create (no duplicate rows)
- `PolicyRepository`: create snapshot, retrieve latest (returns correct object), multiple snapshots (returns most recent), no snapshot (returns None)
- `AnalyticsRepository`: upsert creates new row, upsert increments existing counters, upsert for different models creates separate rows
Manual verification steps:
- `pytest tests/integration/db/ -v -k "session or policy or analytics"` passes

**Acceptance Criteria**

- `SessionRepository.create_or_get()` is idempotent: calling twice with the same ID returns the same row without error
- `PolicyRepository.get_latest_for_session()` deserializes JSON fields to correct Python types (`list`, `dict`)
- `AnalyticsRepository.upsert_counters()` never performs read-modify-write (uses SQL UPSERT)
- All repository methods use `await session.commit()` after mutations
- `mypy src/sentinel/infrastructure/db/repositories/` reports zero errors
- All integration tests pass

**Rollback Strategy**

Revert repository files to `NotImplementedError` stubs. Application layer calls will raise at runtime, not silently.

**Estimated Complexity:** M

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (fast)  
Recommended Mode: fast

Reason: Repository implementation is mechanical CRUD pattern application. The upsert SQL syntax requires care but is well-defined per database dialect.

---

**Context Strategy**

Start new chat? Yes — entering infrastructure subsystem. New context; domain engine files not needed.

Required files to include as context:

- `03_DATABASE_SCHEMA.md` (sessions, policy_snapshots, analytics_counters tables only)
- `backend/src/sentinel/infrastructure/db/models.py` (the ORM models from T-007)

Architecture docs to reference:

- `03_DATABASE_SCHEMA.md` sections 3.1 (sessions), 3.2 (policy_snapshots), 3.7 (analytics_counters)
- `02_TECH_DECISIONS.md` TD-07 (SQLAlchemy async)

Documents NOT required:

- Domain design docs, application structure, API docs, frontend docs, security docs

---

---

#### Task ID: T-017

**Title:** SQLAlchemy Repository Implementations — Requests and KB

**Phase:** 3

**Subsystem:** Infrastructure — Database Repositories

**Description:**  
Implement `RequestRepository` and `KBRepository` — the two most complex repositories. `RequestRepository` handles the central fact table with complex filtering queries (for Request Explorer). `KBRepository` handles document lifecycle and chunk management. Both are required before the pipeline orchestrator (Phase 4) can persist audit records.

**Scope Boundaries**

Files affected:

- `backend/src/sentinel/infrastructure/db/repositories/request_repo.py`
- `backend/src/sentinel/infrastructure/db/repositories/kb_repo.py`
- `tests/integration/db/test_request_repo.py`
- `tests/integration/db/test_kb_repo.py`

Modules affected:

- `sentinel.infrastructure.db.repositories`

Explicitly NOT touching:

- `pipeline_traces`, `request_claims`, `claim_evidence`, `safety_filter_results` tables (written by `AuditService` in Phase 4), domain models, application code, API code

**Implementation Steps**

1. Implement `RequestRepository.create(session_id, policy_snapshot_id, prompt_hash, prompt_masked_text, model_provider, model_name) -> str`: insert with `status='pending'`. Return new UUID.
2. Implement `RequestRepository.update_status(request_id, status)` and `RequestRepository.update_completed(request_id, result_dict)`: update all result fields atomically when pipeline completes.
3. Implement `RequestRepository.list_by_session(session_id, filters, limit, offset) -> list[RequestSummary]`: support `filter_by_decision`, `filter_by_status`, `search_by_id` filtering. Use SQLAlchemy `select().where()` with dynamic filter composition.
4. Implement `RequestRepository.get_by_id(request_id, session_id) -> RequestDetail | None`: full row fetch including all sub-tables via joined load (`pipeline_traces`, `request_claims`, `claim_evidence`, `safety_filter_results`).
5. Implement `KBRepository.create_document(session_id, filename, file_size, mime_type, storage_path) -> str`: insert with `status='pending'`.
6. Implement `KBRepository.update_document_status(document_id, status, chunk_count?, error_message?)`.
7. Implement `KBRepository.create_chunk(document_id, chunk_index, chunk_text, char_start, char_end, faiss_vector_id) -> str`.
8. Implement `KBRepository.get_chunks_by_document(document_id) -> list[KBChunk]` and `get_chunk_by_faiss_id(faiss_id) -> KBChunk | None`.
9. Write integration tests for all methods including the joined load for `get_by_id`.

**Data Impact**

Schema changes: None  
Migration required: No

**Test Plan**

Unit tests: None  
Integration tests:

- `RequestRepository`: create → update_status round-trip, list with decision filter (returns only matching), get_by_id with all sub-tables populated
- `KBRepository`: document lifecycle (pending → indexing → ready), chunk insertion and retrieval, `get_chunk_by_faiss_id` for an inserted chunk
Manual verification steps:
- `pytest tests/integration/db/ -v -k "request or kb"` passes

**Acceptance Criteria**

- `RequestRepository.list_by_session()` with `filter_by_decision='block'` returns only blocked requests
- `RequestRepository.get_by_id()` returns all child records in a single database query (not N+1)
- `KBRepository.update_document_status()` with `status='failed'` correctly sets `error_message`
- All repository methods handle `None` gracefully (no attribute access on `None`)
- `mypy` reports zero errors on both files
- All integration tests pass

**Rollback Strategy**

Revert to `NotImplementedError` stubs. The impact is localized to the audit persistence path (Phase 4).

**Estimated Complexity:** M

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (fast)  
Recommended Mode: fast

Reason: Repository implementation is CRUD pattern application. The joined load pattern for `get_by_id` is standard SQLAlchemy practice.

---

**Context Strategy**

Start new chat? No — continue from T-016 chat.

Required files to include as context:

- `03_DATABASE_SCHEMA.md` (requests, pipeline_traces, request_claims, claim_evidence, safety_filter_results, kb_documents, kb_chunks tables)
- `backend/src/sentinel/infrastructure/db/models.py`

Architecture docs to reference:

- `03_DATABASE_SCHEMA.md` sections 3.3 through 3.6 and 3.8 through 3.9

Documents NOT required:

- Domain design, application structure, API docs, frontend docs

---

---

#### Task ID: T-018

**Title:** FAISS Vector Store Implementation

**Phase:** 3

**Subsystem:** Infrastructure — Vector Store

**Description:**  
Implement `FAISSStore` — the in-process vector index for knowledge base chunk retrieval. Implements `VectorStore` protocol: `add(vectors, ids)`, `query(vector, top_k) -> list[ScoredID]`, `remove_ids(ids)`, `persist(path)`, `load(path)`. Each KB document set has its own `IndexIDMap` instance. Concurrent writes are protected by a per-index `asyncio.Lock`. Write integration tests covering add → query → remove → query round-trip.

**Scope Boundaries**

Files affected:

- `backend/src/sentinel/infrastructure/vector_store/base.py` (VectorStore Protocol definition)
- `backend/src/sentinel/infrastructure/vector_store/faiss_store.py`
- `tests/integration/infrastructure/test_faiss_store.py`

Modules affected:

- `sentinel.infrastructure.vector_store`

Explicitly NOT touching:

- ChromaDB store, embedding adapter, repositories, application code, API code, domain engines

**Implementation Steps**

1. Define `VectorStore` Protocol in `base.py` with method signatures: `add(vectors: np.ndarray, ids: np.ndarray)`, `query(vector: np.ndarray, top_k: int) -> list[tuple[int, float]]`, `remove_ids(ids: list[int])`, `persist(path: Path)`, `load(path: Path)`.
2. Implement `FAISSStore.__init__(dimension: int)`: creates `faiss.IndexIDMap(faiss.IndexFlatIP(dimension))` — inner product index (cosine similarity after L2 normalization). Initialize `_lock = asyncio.Lock()`.
3. Implement `add(vectors, ids)`: normalize vectors with `faiss.normalize_L2(vectors)`, acquire lock, call `index.add_with_ids(vectors, ids)`. Async method.
4. Implement `query(vector, top_k)`: normalize query vector, call `index.search(vector, top_k)`. Returns `list[tuple[int, float]]` of `(faiss_id, similarity_score)`. Handles empty index (returns `[]`).
5. Implement `remove_ids(ids)`: acquire lock, call `index.remove_ids(np.array(ids, dtype='int64'))`. Note: `remove_ids` requires `IndexIDMap` — verify this is correctly wrapped.
6. Implement `persist(path)`: `faiss.write_index(self.index, str(path))`. Implement `load(path)`: `faiss.read_index(str(path))`.
7. Write `test_faiss_store.py`: add 10 vectors → query top-3 returns 3 nearest, add → remove → query confirms removed vector not returned, persist → load → query returns same results, empty index query returns empty list, concurrent add from two async tasks (no corruption).

**Data Impact**

Schema changes: None  
Migration required: No

**Test Plan**

Unit tests: None  
Integration tests:

- Add + query round-trip (top-k ordering is correct)
- Remove + verify (removed ID never returned in query results)
- Persist + load + query (results identical pre/post persistence)
- Empty index returns empty result list
- Concurrent write test (two async tasks adding simultaneously, no assertion errors)
Manual verification steps:
- `pytest tests/integration/infrastructure/test_faiss_store.py -v` passes

**Acceptance Criteria**

- `query()` returns results sorted by descending cosine similarity score
- `remove_ids()` followed by `query()` never returns the removed vector
- `persist()` + `load()` round-trip produces identical query results
- Empty index query returns `[]` without error
- Concurrent `add()` calls are serialized by the `asyncio.Lock` — no FAISS corruption
- `mypy src/sentinel/infrastructure/vector_store/` reports zero errors

**Rollback Strategy**

The FAISS store is isolated to the vector store package. Application code that uses it will fail at the `KnowledgeRetrievalLayer` level (Phase 4) — not silently.

**Estimated Complexity:** M

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (thinking)  
Recommended Mode: thinking

Reason: FAISS `IndexIDMap` semantics and `remove_ids` behavior are version-dependent and non-obvious. The async lock integration with FAISS's C++ synchronous API requires careful reasoning to avoid race conditions.

---

**Context Strategy**

Start new chat? Yes — new subsystem (vector store). Database files not needed here.

Required files to include as context:

- `01_SYSTEM_ARCHITECTURE.md` (vector store section)
- `02_TECH_DECISIONS.md` (TD-08 vector store)
- `04_DOMAIN_ENGINE_DESIGN.md` (knowledge retrieval layer section)

Architecture docs to reference:

- `02_TECH_DECISIONS.md` TD-08
- `04_DOMAIN_ENGINE_DESIGN.md` section 6.1 (KnowledgeRetrievalLayer)

Documents NOT required:

- Schema docs, application structure, API docs, frontend docs, security docs, deployment docs

---

---

#### Task ID: T-019

**Title:** SentenceTransformer Embedding Adapter

**Phase:** 3

**Subsystem:** Infrastructure — Embeddings

**Description:**  
Implement `SentenceTransformerAdapter` wrapping the `all-MiniLM-L6-v2` model. Provides `embed(text: str) -> np.ndarray` and `embed_batch(texts: list[str]) -> np.ndarray` with LRU caching on single-text embeddings. Dispatches to a thread pool via `asyncio.run_in_executor` to avoid blocking the event loop during model inference. Write integration tests verifying dimension, caching behavior, and thread-pool dispatch.

**Scope Boundaries**

Files affected:

- `backend/src/sentinel/infrastructure/embeddings/base.py` (EmbeddingAdapter Protocol)
- `backend/src/sentinel/infrastructure/embeddings/sentence_transformer.py`
- `tests/integration/infrastructure/test_embedding_adapter.py`

Modules affected:

- `sentinel.infrastructure.embeddings`

Explicitly NOT touching:

- FAISS store, LLM adapters, repositories, domain engines, application, API, frontend

**Implementation Steps**

1. Define `EmbeddingAdapter` Protocol in `base.py`: `async def embed(text: str) -> np.ndarray`, `async def embed_batch(texts: list[str]) -> np.ndarray`.
2. Implement `SentenceTransformerAdapter.__init__(model_name: str, cache_size: int = 512)`: load `SentenceTransformer(model_name)` in `__init__`. Initialize `cachetools.LRUCache(maxsize=cache_size)` with an `asyncio.Lock` for cache access.
3. Implement `embed(text: str)`: check LRU cache (with lock). On cache miss, dispatch `model.encode([text])` to `asyncio.get_event_loop().run_in_executor(None, ...)`. Store result in cache. Return `np.ndarray` of shape `(384,)`.
4. Implement `embed_batch(texts: list[str])`: dispatch `model.encode(texts, batch_size=32)` to thread pool. Return `np.ndarray` of shape `(len(texts), 384)`. Do not use the single-item cache for batch calls.
5. Write `test_embedding_adapter.py`: dimension test (`embed("test") -> shape (384,)`), cache hit test (second call for same text returns from cache, verified by mock call count), batch test (`embed_batch(["a","b"]) -> shape (2, 384)`), async dispatch test (verify the event loop is not blocked during encoding — use `asyncio.wait_for` with a 5s timeout).

**Data Impact**

Schema changes: None  
Migration required: No

**Test Plan**

Unit tests: None  
Integration tests:

- Output dimension is 384 for `all-MiniLM-L6-v2`
- LRU cache hit (same text, second call does not call `model.encode`)
- Batch output shape is `(N, 384)` for N texts
- Thread pool dispatch: call completes within 5 seconds
Manual verification steps:
- `pytest tests/integration/infrastructure/test_embedding_adapter.py -v` passes

**Acceptance Criteria**

- `embed("test")` returns `np.ndarray` of shape `(384,)`
- LRU cache prevents redundant model inference on repeated texts
- LRU cache access is thread-safe (protected by `asyncio.Lock`)
- `embed_batch()` dispatches correctly to the thread pool (event loop not blocked)
- `mypy src/sentinel/infrastructure/embeddings/` reports zero errors

**Rollback Strategy**

Isolated adapter. `KnowledgeRetrievalLayer` (Phase 4) fails at import time if this adapter is removed.

**Estimated Complexity:** S

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (thinking)  
Recommended Mode: thinking

Reason: The asyncio/thread pool interaction for CPU-bound model inference and the `asyncio.Lock`-guarded LRU cache require reasoning about Python's concurrency model to get correct.

---

**Context Strategy**

Start new chat? No — continue from T-018 chat (same infrastructure subsystem).

Required files to include as context:

- `02_TECH_DECISIONS.md` (TD-09 embedding model)

Architecture docs to reference:

- `02_TECH_DECISIONS.md` TD-09

Documents NOT required:

- Schema docs, domain design, application structure, API docs, frontend docs

---

---

#### Task ID: T-020

**Title:** OllamaAdapter and OpenAIAdapter

**Phase:** 3

**Subsystem:** Infrastructure — LLM Adapters

**Description:**  
Implement the `LLMAdapter` protocol and both concrete implementations: `OllamaAdapter` (local model via HTTP to Ollama server) and `OpenAIAdapter` (OpenAI API via the official Python SDK). Both must implement `complete(prompt, model_name, temperature, max_tokens, timeout_seconds) -> LLMResponse` and `health_check() -> bool`. `OllamaAdapter` includes exponential backoff retry. Write integration tests for both adapters (Ollama tests gated on `OLLAMA_AVAILABLE` env flag).

**Scope Boundaries**

Files affected:

- `backend/src/sentinel/infrastructure/llm/base.py` (LLMAdapter Protocol + LLMResponse dataclass)
- `backend/src/sentinel/infrastructure/llm/ollama_adapter.py`
- `backend/src/sentinel/infrastructure/llm/openai_adapter.py`
- `tests/integration/infrastructure/test_ollama_adapter.py`
- `tests/integration/infrastructure/test_openai_adapter.py`

Modules affected:

- `sentinel.infrastructure.llm`

Explicitly NOT touching:

- Embedding adapter, FAISS store, repositories, domain engines, application, API, frontend

**Implementation Steps**

1. Define `LLMAdapter` Protocol and `LLMResponse(text, tokens_in, tokens_out, latency_ms, model_name)` frozen dataclass in `base.py`.
2. Implement `OllamaAdapter`: use `httpx.AsyncClient` to POST to `OLLAMA_BASE_URL/api/generate`. Parse the NDJSON streaming response (concatenate `response` fields). Implement exponential backoff retry: 3 attempts, 1s → 2s → 4s delays. `health_check()` pings `OLLAMA_BASE_URL/api/tags`. Map `httpx` connection errors → `LLMUnavailableError`.
3. Implement `OpenAIAdapter`: use `openai.AsyncOpenAI(api_key=key)`. Call `client.chat.completions.create()`. Map `openai.AuthenticationError` → `LLMUnavailableError`. Map missing API key → raise immediately before HTTP call with descriptive error. `health_check()` returns `True` if `api_key` is configured (no live check).
4. Write `test_ollama_adapter.py`: gated with `pytest.mark.skipif(not os.getenv("OLLAMA_AVAILABLE"), reason="Ollama not running")`. Tests: health check returns True, `complete()` with a short prompt returns text, timeout error maps to `LLMUnavailableError`.
5. Write `test_openai_adapter.py`: use `respx` to mock the HTTP calls. Tests: successful completion, `AuthenticationError` maps correctly, missing API key raises before HTTP call.

**Data Impact**

Schema changes: None  
Migration required: No

**Test Plan**

Unit tests: None  
Integration tests:

- `OllamaAdapter.health_check()` returns `True` when Ollama is running (skipped if not running)
- `OpenAIAdapter.complete()` with mocked response returns `LLMResponse` with correct fields
- `OpenAIAdapter` with missing API key raises `LLMUnavailableError` immediately
Manual verification steps:
- `pytest tests/integration/infrastructure/test_openai_adapter.py -v` passes (uses mocks, no real API call)

**Acceptance Criteria**

- `OllamaAdapter` retries up to 3 times with exponential backoff on connection failure
- Both adapters return `LLMResponse` with non-None `tokens_in`, `tokens_out`
- `OpenAIAdapter` with no API key raises before making any HTTP request
- `LLMUnavailableError` is raised (not a raw `httpx` exception) on connection failure
- `mypy src/sentinel/infrastructure/llm/` reports zero errors

**Rollback Strategy**

Isolated adapters. `LLMExecutionLayer` (Phase 4) fails at import time if removed.

**Estimated Complexity:** M

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (fast)  
Recommended Mode: fast

Reason: Both adapters follow standard HTTP client patterns. The NDJSON Ollama parsing is slightly non-standard but well-documented.

---

**Context Strategy**

Start new chat? No — continue from T-019 chat.

Required files to include as context:

- `02_TECH_DECISIONS.md` (TD-10 Ollama)
- `01_SYSTEM_ARCHITECTURE.md` (LLM provider section)

Architecture docs to reference:

- `01_SYSTEM_ARCHITECTURE.md` section 2 (LLM providers)
- `02_TECH_DECISIONS.md` TD-10

Documents NOT required:

- Schema docs, domain design, application structure, API docs, frontend docs

---

---

#### Task ID: T-021

**Title:** DetoxifyClassifier and TextChunker

**Phase:** 3

**Subsystem:** Infrastructure — Safety Classifier and Text Processing

**Description:**  
Implement `DetoxifyClassifier` (wraps the detoxify ML model, dispatches to `ProcessPoolExecutor` to avoid blocking the event loop) and `TextChunker` (sliding window text segmentation with sentence boundary detection for KB document indexing). Both are pure adapters with no domain logic.

**Scope Boundaries**

Files affected:

- `backend/src/sentinel/infrastructure/safety/detoxify_classifier.py`
- `backend/src/sentinel/infrastructure/chunking/text_chunker.py`
- `tests/integration/infrastructure/test_detoxify_classifier.py`
- `tests/unit/infrastructure/test_text_chunker.py`

Modules affected:

- `sentinel.infrastructure.safety`, `sentinel.infrastructure.chunking`

Explicitly NOT touching:

- FAISS store, embedding adapter, LLM adapters, repositories, domain engines, application, API, frontend

**Implementation Steps**

1. Implement `DetoxifyClassifier`: define a module-level `_predict_sync(text: str) -> dict[str, float]` function that loads the detoxify model inside the function (not at module level — must be serializable for `ProcessPoolExecutor`). Implement `async predict(text: str) -> dict[str, float]`: get the current event loop, call `loop.run_in_executor(self._process_pool, _predict_sync, text)`. Initialize `self._process_pool = ProcessPoolExecutor(max_workers=2)` in `__init__`. Map detoxify output keys to `SafetyFilterResult` field names.
2. Implement `TextChunker.chunk(text: str, chunk_size: int = 512, overlap: int = 64) -> list[TextChunk]`: split text into sentences using `re.split(r'(?<=[.!?])\s+', text)`. Group sentences into chunks of approximately `chunk_size` characters. Apply `overlap` characters of context from the previous chunk. Return `list[TextChunk(text, char_start, char_end, chunk_index)]`.
3. Write `test_detoxify_classifier.py` (integration test): `predict("I love programming")` returns scores all near 0.0, `predict` completes within 10 seconds (model loads inside worker), process pool shuts down cleanly on `classifier.shutdown()`.
4. Write `test_text_chunker.py` (unit test): short text produces 1 chunk, long text produces multiple overlapping chunks, overlap content is verified (last 64 chars of chunk N appear at start of chunk N+1), empty text returns empty list, single very long sentence is chunked at `chunk_size` boundary.

**Data Impact**

Schema changes: None  
Migration required: No

**Test Plan**

Unit tests: `TextChunker` tests (5 cases as described above)  
Integration tests: `DetoxifyClassifier.predict()` completes without error on benign text  
Manual verification steps:

- `pytest tests/unit/infrastructure/test_text_chunker.py -v` passes
- `pytest tests/integration/infrastructure/test_detoxify_classifier.py -v` passes

**Acceptance Criteria**

- `DetoxifyClassifier` loads the model inside the worker function (not at module level)
- `predict()` completes within 10 seconds for a single text input
- `ProcessPoolExecutor.shutdown(wait=True)` is called on `DetoxifyClassifier.shutdown()`
- `TextChunker` produces chunks where adjacent chunks share at least `overlap` characters
- `TextChunker` respects sentence boundaries: no sentence is split in the middle unless it exceeds `chunk_size` alone
- `mypy src/sentinel/infrastructure/safety/` and `src/sentinel/infrastructure/chunking/` report zero errors

**Rollback Strategy**

Isolated adapters. `OutputSafetyFilter` and KB indexing worker (both Phase 4) fail at import time if removed.

**Estimated Complexity:** M

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (thinking)  
Recommended Mode: thinking

Reason: `ProcessPoolExecutor` + async event loop interaction for the detoxify classifier has a specific correctness requirement (model loaded inside worker, not at module level). This is a non-obvious requirement that causes hard-to-debug failures if done incorrectly.

---

**Context Strategy**

Start new chat? No — continue from T-020 chat.

Required files to include as context:

- `04_DOMAIN_ENGINE_DESIGN.md` (safety filter section referencing detoxify)
- `02_TECH_DECISIONS.md` (TD-21 detoxify)

Architecture docs to reference:

- `02_TECH_DECISIONS.md` TD-21
- `04_DOMAIN_ENGINE_DESIGN.md` section 5 (OutputSafetyFilter)

Documents NOT required:

- Schema docs, FAISS design, application structure, API docs, frontend docs

---

---

#### Task ID: T-022

**Title:** LocalFileStorage and Infrastructure Integration Test Consolidation

**Phase:** 3

**Subsystem:** Infrastructure — File Storage and Testing

**Description:**  
Implement `LocalFileStorage` for KB document file management, then consolidate all infrastructure integration tests and verify the full Phase 3 test suite passes. `LocalFileStorage` is the last infrastructure adapter. This task also serves as the Phase 3 completion gate.

**Scope Boundaries**

Files affected:

- `backend/src/sentinel/infrastructure/storage/local_file_storage.py`
- `tests/integration/infrastructure/test_local_file_storage.py`
- `tests/integration/conftest.py` (shared infrastructure test fixtures)

Modules affected:

- `sentinel.infrastructure.storage`

Explicitly NOT touching:

- All previously implemented infrastructure adapters, domain engines, application, API, frontend

**Implementation Steps**

1. Implement `LocalFileStorage`: `__init__(base_path: Path)` — creates `base_path` if not exists. `save(file_content: bytes, filename: str, session_id: str) -> Path`: sanitize filename (strip path separators, limit length), create `base_path / session_id /` subdirectory, write file. `delete(path: Path)`: remove file; no error if not found. `sanitize_filename(filename: str) -> str`: remove path traversal characters (`../`, `/`, `\`), normalize Unicode, truncate to 255 chars.
2. Write `test_local_file_storage.py`: save file returns correct path, file exists at returned path, delete removes file (idempotent on second delete), `sanitize_filename` rejects path traversal (`../../../etc/passwd` → `etc_passwd`), max filename length enforced.
3. Write `tests/integration/conftest.py`: shared fixtures for all infrastructure integration tests: `async_test_db` (migrated in-memory SQLite + session factory), `faiss_store_256dim`, `mock_embedding_adapter` (returns deterministic random vectors).
4. Run full infrastructure integration test suite: `pytest tests/integration/ -v`. All tests from T-016 through T-022 must pass.
5. Run `mypy src/sentinel/infrastructure/` — zero errors across the entire infrastructure package.

**Data Impact**

Schema changes: None  
Migration required: No

**Test Plan**

Unit tests: `sanitize_filename` edge cases (path traversal, length limits, unicode normalization)  
Integration tests: File save/delete round-trip  
Manual verification steps:

- `pytest tests/integration/ -v` passes (all infrastructure tests)
- `mypy src/sentinel/infrastructure/` reports zero errors

**Acceptance Criteria**

- `sanitize_filename("../../../etc/passwd")` returns a safe filename with no path separators
- `save()` creates the session-scoped subdirectory if it does not exist
- `delete()` on a non-existent path does not raise an error
- Full infrastructure integration test suite (`pytest tests/integration/`) passes with zero failures
- `mypy src/sentinel/infrastructure/` reports zero errors across all adapter modules

**Rollback Strategy**

Remove the file storage module. KB document upload endpoint (Phase 5) will fail at the application layer.

**Estimated Complexity:** S

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (fast)  
Recommended Mode: fast

Reason: File storage is straightforward I/O with simple path manipulation. The `sanitize_filename` security logic follows standard rules.

---

**Context Strategy**

Start new chat? No — continue from T-021 chat.

Required files to include as context:

- `07_SECURITY_MODEL.md` (file upload security section)

Architecture docs to reference:

- `07_SECURITY_MODEL.md` file storage section

Documents NOT required:

- Domain design, schema (beyond what's already in context), application structure, API docs, frontend docs

---

*— End of Phase 2 Generation —*

---

### Phase 4 — Application Layer & Pipeline Orchestrator

---

#### Task ID: T-023

**Title:** ApplicationContainer and FastAPI Application Factory

**Phase:** 4

**Subsystem:** Application Layer — Dependency Injection and Startup

**Description:**  
Implement `ApplicationContainer` — the single root of the dependency graph that wires all infrastructure adapters into domain engines and use cases. Implement `main.py` with the `create_app()` factory and FastAPI `lifespan` context manager. After this task, `uvicorn sentinel.main:app` starts without errors (health check only — no routes yet).

**Scope Boundaries**

Files affected:

- `backend/src/sentinel/container.py`
- `backend/src/sentinel/main.py`
- `backend/src/sentinel/config.py` (finalize remaining config fields)

Modules affected: `sentinel.container`, `sentinel.main`

Explicitly NOT touching: Any router files, middleware, WebSocket handler, use cases, domain engines

**Implementation Steps**

1. Implement `ApplicationContainer.__init__(config: AppConfig)`: construct all infrastructure adapters from config — `AsyncEngine`, `AsyncSessionLocal`, `FAISSStore` per-KB instance registry (`dict[str, FAISSStore]`), `SentenceTransformerAdapter`, `OllamaAdapter`, `OpenAIAdapter`, `DetoxifyClassifier`, `LocalFileStorage`, all 5 repositories.
2. Implement `ApplicationContainer.initialize()`: run `alembic upgrade head` programmatically, pre-warm embedding model, call `OllamaAdapter.health_check()` and log warning (not error) if unavailable. Set `self._ready = True`.
3. Implement `ApplicationContainer.shutdown()`: call `DetoxifyClassifier.shutdown()` (terminates `ProcessPoolExecutor`), flush pending async tasks, set `self._ready = False`.
4. Implement `main.py`: `create_app()` factory per `05_APPLICATION_STRUCTURE.md` section 2.1. Register minimal `/health/live` route returning `{"status": "ok"}`. Mount `app.state.container = container` in lifespan startup.
5. Manual test: `uvicorn sentinel.main:app` starts, `GET /health/live` returns 200, `Ctrl-C` shuts down cleanly with no asyncio event loop errors.

**Data Impact**

Schema changes: None | Migration required: No

**Test Plan**

Integration tests: `ApplicationContainer(config)` instantiates and `initialize()` runs Alembic and pre-warms model against real SQLite + embedding model.  
Manual: `GET /health/live` returns HTTP 200 without requiring Ollama.

**Acceptance Criteria**

- `ApplicationContainer` wires all adapters from `AppConfig` with no hardcoded values
- `initialize()` logs a structured warning (not exception) when Ollama is unavailable
- `shutdown()` terminates the `ProcessPoolExecutor` before process exits
- `GET /health/live` returns HTTP 200
- `mypy src/sentinel/container.py src/sentinel/main.py` reports zero errors

**Rollback Strategy**

Revert `main.py` and `container.py`. All adapters are constructed in `__init__` — construction failures are immediate and explicit.

**Estimated Complexity:** M

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (thinking) | Recommended Mode: thinking

Reason: Container wiring order matters — adapters with dependencies must be constructed in correct order. The asyncio lifespan contract (startup completes before requests accepted; shutdown drains in-flight work) requires explicit reasoning.

---

**Context Strategy**

Start new chat? Yes — entering application layer. New subsystem.

Required files: `05_APPLICATION_STRUCTURE.md` (sections 2.1 and 2.2), `backend/src/sentinel/config.py`, adapter interface stubs.  
Architecture docs: `05_APPLICATION_STRUCTURE.md` sections 2.1–2.2, `02_TECH_DECISIONS.md` TD-05.  
NOT required: Full domain engine docs, schema docs, security docs, frontend docs.

---

---

#### Task ID: T-024

**Title:** LLMExecutionLayer and HallucinationDetectionEngine

**Phase:** 4

**Subsystem:** Application Layer — Pipeline Stages 2 and 3

**Description:**  
Implement `LLMExecutionLayer` (selects and calls correct LLM adapter), `ClaimExtractor` (LLM-based extraction with JSON and regex fallbacks), `KnowledgeRetrievalLayer` (embed claim → FAISS query → DB chunk lookup → `Evidence`), and `ClaimVerifier` (per-claim LLM verification). Write unit tests with mocked adapters.

**Scope Boundaries**

Files affected:

- `backend/src/sentinel/application/pipeline/llm_execution.py`
- `backend/src/sentinel/application/pipeline/hallucination/claim_extractor.py`
- `backend/src/sentinel/application/pipeline/hallucination/knowledge_retrieval.py`
- `backend/src/sentinel/application/pipeline/hallucination/claim_verifier.py`
- `tests/unit/application/test_llm_execution.py`
- `tests/unit/application/test_claim_extractor.py`
- `tests/unit/application/test_claim_verifier.py`

Modules affected: `sentinel.application.pipeline`

Explicitly NOT touching: Orchestrator, safety filter, confidence scoring, API layer, frontend

**Implementation Steps**

1. Implement `LLMExecutionLayer.generate(context)`: select adapter from `context.model_provider`, call `adapter.complete()`, populate `context.llm_response_text`, `tokens_in`, `tokens_out`, `llm_latency_ms`. On `LLMUnavailableError` set `context.is_terminal = True` and populate block decision.
2. Implement `ClaimExtractor.extract(response_text)` per `04_DOMAIN_ENGINE_DESIGN.md` section 6.1: LLM call, `json.loads()`, regex fallback `r'\[.*?\]'`, empty-list fallback on total failure. Cap at `config.max_claims_per_response`.
3. Implement `KnowledgeRetrievalLayer.retrieve(claims, kb_id) -> dict[int, list[Evidence]]`: per claim: embed → FAISS query → DB lookup → `Evidence` objects. Return empty dict immediately when `kb_id` is `None`.
4. Implement `ClaimVerifier.verify_batch()` per `04_DOMAIN_ENGINE_DESIGN.md` section 6.2: per-claim LLM call, `_score_claim()` logic, no-evidence fast-path (`status='unsupported'` immediately).
5. Unit tests (mocked LLM + FAISS): `ClaimExtractor` JSON success, regex fallback, total parse failure → `[]`; `LLMExecutionLayer` OpenAI without key → terminal block; `ClaimVerifier` no-evidence → all unsupported.

**Data Impact**

Schema changes: None | Migration required: No

**Test Plan**

Unit tests: 7 scenarios as described above. All use mocked adapters (no real LLM calls in unit tests).  
Manual: `mypy src/sentinel/application/pipeline/` reports zero errors.

**Acceptance Criteria**

- `ClaimExtractor` never raises regardless of LLM output format
- `KnowledgeRetrievalLayer` returns empty dict without error when `kb_id` is `None`
- `ClaimVerifier._score_claim('contradicted', ...)` returns a negative float
- `mypy` reports zero errors on all 4 files

**Rollback Strategy**

These pipeline stage files are imported by the orchestrator. Removing them causes an import failure at startup.

**Estimated Complexity:** M

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (thinking) | Recommended Mode: thinking

Reason: The JSON parse → regex fallback → empty-list fallback chain in `ClaimExtractor` is a critical reliability path. `KnowledgeRetrievalLayer` async fan-out (one embed + one FAISS query per claim) needs careful asyncio composition.

---

**Context Strategy**

Start new chat? No — continue from T-023.

Required files: `04_DOMAIN_ENGINE_DESIGN.md` (sections 5 and 6), domain model interfaces (`PipelineContext`, `Claim`, `Evidence`).  
NOT required: Schema docs, API docs, frontend, security, deployment docs.

---

---

#### Task ID: T-025

**Title:** OutputSafetyFilter and GuardrailPipelineOrchestrator

**Phase:** 4

**Subsystem:** Application Layer — Pipeline Stage 4 and Orchestrator

**Description:**  
Implement `OutputSafetyFilter` (concurrent detoxify + harmful instruction scan) and the complete `GuardrailPipelineOrchestrator` (full stage sequence, parallel stages 3+4, short-circuit on block, retry loop, trace accumulation). A complete end-to-end pipeline execution from Python must succeed by the end of this task.

**Scope Boundaries**

Files affected:

- `backend/src/sentinel/application/pipeline/safety_filter.py`
- `backend/src/sentinel/domain/engines/orchestrator.py`
- `tests/unit/application/test_orchestrator.py`
- `tests/consistency/test_pipeline_determinism.py`

Modules affected: `sentinel.application.pipeline`, `sentinel.domain.engines`

Explicitly NOT touching: API layer, WebSocket, use cases, audit service, frontend

**Implementation Steps**

1. Implement `OutputSafetyFilter.analyze(context)`: run `DetoxifyClassifier.predict(response_text)` via `run_in_executor`. Run harmful instruction regex scan synchronously. Use `asyncio.gather` with individual exception handling per task (exception in one must not cancel sibling). Populate `context.safety_results`.
2. Implement `GuardrailPipelineOrchestrator.execute(context)` from `04_DOMAIN_ENGINE_DESIGN.md` section 3.1: full while-loop retry structure, `_run_single_attempt()`, `_run_stage()` with timing and trace append, `_fill_not_reached()`, `_handle_stage_failure()`.
3. In `_run_single_attempt()`: stages 3 and 4 run as concurrent `asyncio.create_task()` calls. Context merge must be serialized: stage 3 completes first, then stage 4 reads from the completed context.
4. Write `test_orchestrator.py` with all engines mocked: clean prompt → accept, injection → short-circuit (no LLM call), safety flagged → block, retry exhaustion → `MAX_RETRIES_EXCEEDED` block.
5. Write `test_pipeline_determinism.py`: 3 runs with identical mocked adapters → identical `GuardrailDecision`.

**Data Impact**

Schema changes: None | Migration required: No

**Test Plan**

Unit tests: 4 orchestrator scenarios + 1 determinism test (3 runs).  
Manual: Direct Python call `await orchestrator.execute(minimal_context)` completes with Ollama running.

**Acceptance Criteria**

- Short-circuit: LLM adapter call count = 0 after injection block
- `context.trace_stages` contains one entry per stage per attempt including `not_reached` stages
- Retry loop terminates at exactly `max_retries + 1` total attempts
- `asyncio.gather` for stages 3+4 handles individual exceptions without cancelling sibling
- Determinism test passes (3 identical runs)
- `mypy src/sentinel/domain/engines/orchestrator.py` reports zero errors

**Rollback Strategy**

Called only by `SubmitPromptUseCase` (T-026). Reverting breaks T-026 tests but not domain or infrastructure.

**Estimated Complexity:** L

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (thinking) | Recommended Mode: thinking

Reason: Orchestrator concurrency model (stages 3+4 parallel with correct context merge), retry loop termination, and `_fill_not_reached` trace logic are complex multi-constraint correctness problems. Highest-risk task in Phase 4.

---

**Context Strategy**

Start new chat? No — continue from T-024.

Required files: `04_DOMAIN_ENGINE_DESIGN.md` (section 3: full orchestrator algorithm), `backend/src/sentinel/domain/models/pipeline_context.py`.  
NOT required: Schema docs, API docs, frontend, deployment docs.

---

---

#### Task ID: T-026

**Title:** SubmitPromptUseCase, AuditService, and SessionService

**Phase:** 4

**Subsystem:** Application Layer — Use Cases and Services

**Description:**  
Implement `SubmitPromptUseCase` (session lookup, policy resolution, PII masking, pipeline invocation, audit persistence), `AuditService` (atomic multi-table transaction), and `SessionService`. After this task, a full guardrail request can be processed from Python with all data written to the database.

**Scope Boundaries**

Files affected:

- `backend/src/sentinel/application/use_cases/submit_prompt.py`
- `backend/src/sentinel/application/services/audit_service.py`
- `backend/src/sentinel/application/services/session_service.py`
- `tests/unit/application/test_submit_prompt_use_case.py`
- `tests/unit/application/test_audit_service.py`
- `tests/consistency/test_audit_immutability.py`

Modules affected: `sentinel.application.use_cases`, `sentinel.application.services`

Explicitly NOT touching: API layer, WebSocket, KB indexing worker, frontend

**Implementation Steps**

1. Implement `SessionService.get_or_create(session_id)`: calls `SessionRepository.create_or_get()`, loads saved policy or returns default `PolicySnapshot`.
2. Implement `SubmitPromptUseCase.execute(request) -> GuardrailResponse`: get/create session, load policy, apply `policy_overrides`, create `requests` row (`status='processing'`), run `PIIDetector.check()`, compute `prompt_hash` as SHA-256 of **original** prompt, construct `PipelineContext`, call `orchestrator.execute(context)`, call `AuditService.persist()`, update `requests` row to `'completed'` or `'blocked'`, return `GuardrailResponse`.
3. Implement `AuditService.persist(request_id, context)`: single `async with session.begin()` block writing: update `requests` row, insert all `pipeline_traces`, `request_claims`, `claim_evidence`, `safety_filter_results` rows, call `analytics_repo.upsert_counters()`.
4. Write `test_audit_immutability.py`: call `persist()` once, attempt second `persist()` with modified context, assert original DB values unchanged.

**Data Impact**

Schema changes: None | Migration required: No

**Test Plan**

Unit tests: injection-blocked prompt → `status='blocked'`, no LLM call; PII prompt → `prompt_masked_text` contains `[REDACTED]`; DB failure mid-transaction → zero rows committed.  
Consistency: audit immutability test.  
Manual: End-to-end Python call with Ollama running → complete `GuardrailResponse` with full DB record.

**Acceptance Criteria**

- `AuditService.persist()` writes all child rows in one atomic transaction; forced rollback leaves zero rows
- `prompt_hash` is SHA-256 of original (unmasked) prompt
- Original prompt text is never written to any DB column
- `analytics_repo.upsert_counters()` called exactly once per `execute()` call
- `mypy src/sentinel/application/` reports zero errors

**Rollback Strategy**

Called only from API layer (T-029). Reverting breaks the API route, not domain or infrastructure layers.

**Estimated Complexity:** M

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (thinking) | Recommended Mode: thinking

Reason: SHA-256 + masking ordering and atomic multi-table transaction correctness require careful sequencing. Wrong order (hash after masking) is a silent data correctness bug.

---

**Context Strategy**

Start new chat? No — continue from T-025.

Required files: `03_DATABASE_SCHEMA.md` (requests, pipeline_traces, request_claims, claim_evidence, safety_filter_results tables), `05_APPLICATION_STRUCTURE.md` (use_cases section).  
NOT required: API docs, frontend, security, deployment docs.

---

---

#### Task ID: T-027

**Title:** Background KB Indexing Worker and EventBus

**Phase:** 4

**Subsystem:** Application Layer — Background Processing and Events

**Description:**  
Implement `kb_indexing_worker` (polls pending documents, indexes them), `IndexDocumentUseCase`, and `EventBus` (per-request asyncio.Queue registry for WebSocket stage events). EventBus is a prerequisite for Phase 5 WebSocket integration.

**Scope Boundaries**

Files affected:

- `backend/src/sentinel/infrastructure/background/indexing_worker.py`
- `backend/src/sentinel/application/use_cases/index_document.py`
- `backend/src/sentinel/websocket/event_bus.py`
- `tests/integration/infrastructure/test_indexing_worker.py`
- `tests/unit/application/test_event_bus.py`

Modules affected: `sentinel.infrastructure.background`, `sentinel.application.use_cases`, `sentinel.websocket`

Explicitly NOT touching: WebSocket HTTP handler (Phase 5), API routers, frontend

**Implementation Steps**

1. Implement `EventBus` in `websocket/event_bus.py`: `dict[str, asyncio.Queue]` registry. `register(request_id) -> asyncio.Queue` (maxsize=20, ring-buffer: `put_nowait` discards oldest on overflow). `publish(request_id, event: dict)` puts to queue if exists. `unregister(request_id)` removes queue. Auto-expire queues after 30 seconds via `asyncio.get_event_loop().call_later(30, unregister, request_id)`.
2. Integrate `EventBus.publish()` into `GuardrailPipelineOrchestrator._run_stage()`: after each stage, call `event_bus.publish(request_id, {"stage": name, "status": status, "latency_ms": ms})`. EventBus injected via constructor; if not provided, publishing is a no-op.
3. Implement `IndexDocumentUseCase.execute(document_id)`: load file via `LocalFileStorage`, extract text (PDF: `pypdf`; TXT: raw read), call `TextChunker.chunk()`, call `embedding_adapter.embed_batch()`, acquire FAISS lock, call `faiss_store.add()`, call `kb_repo.create_chunk()` per chunk, call `kb_repo.update_document_status('ready')`.
4. Implement `kb_indexing_worker` coroutine: infinite loop polling `kb_repo.list_documents_by_status('pending')` every 5 seconds. Per pending document: set `'indexing'`, call `IndexDocumentUseCase.execute()`, handle exceptions (set `'failed'` with `error_message` — do not crash the loop).
5. Wire worker into `ApplicationContainer.initialize()` as `asyncio.create_task()`. Store task handle for cancellation in `shutdown()`.

**Data Impact**

Schema changes: None | Migration required: No

**Test Plan**

Unit tests: `EventBus.publish()` to unregistered ID is no-op; queue overflow (21st event) discards oldest without blocking.  
Integration tests: `IndexDocumentUseCase` with a test TXT file → `status='ready'`, 3+ chunks in DB, FAISS vectors queryable.

**Acceptance Criteria**

- KB indexer transitions `pending → indexing → ready` with correct `chunk_count`
- FAISS vectors added by indexer are immediately queryable
- EventBus queue auto-expires after 30 seconds (no memory leak)
- Worker exception: failed document set to `'failed'`; worker loop continues
- `mypy src/sentinel/websocket/event_bus.py` reports zero errors

**Rollback Strategy**

Worker is an `asyncio.create_task`. Cancel in `shutdown()`. Documents remain `pending`; no data lost.

**Estimated Complexity:** M

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (thinking) | Recommended Mode: thinking

Reason: EventBus ring-buffer auto-expiry and FAISS lock interaction in the indexing use case involve concurrency correctness. Worker exception handling must prevent a single document failure from killing the loop.

---

**Context Strategy**

Start new chat? No — continue from T-026.

Required files: `06_AUTOMATION_AND_AI_INTEGRATION.md` (KB indexing section), `04_DOMAIN_ENGINE_DESIGN.md` (KnowledgeRetrievalLayer section).  
NOT required: Security docs, frontend docs, deployment docs.

---

---

### Phase 5 — API Layer

---

#### Task ID: T-028

**Title:** Middleware Stack and Global Error Handlers

**Phase:** 5

**Subsystem:** API Layer — Cross-Cutting Concerns

**Description:**  
Implement all 5 middleware components and all 12 exception-to-HTTP-response mappings. The API key stripping middleware is security-critical: it must strip the key before the logging middleware runs. Every request passes through this code.

**Scope Boundaries**

Files affected:

- `backend/src/sentinel/api/middleware.py`
- `backend/src/sentinel/api/error_handlers.py`
- `backend/src/sentinel/api/dependencies.py`
- `tests/integration/api/test_middleware.py`
- `tests/integration/api/test_error_handlers.py`

Modules affected: `sentinel.api`

Explicitly NOT touching: Any router files, domain engines, infrastructure, frontend

**Implementation Steps**

1. Implement CORS Middleware: allow `config.cors_origins`, expose `X-Request-ID` response header.
2. Implement `RequestIDMiddleware`: read `X-Request-ID` or generate UUID; bind to structlog context vars; add as response header.
3. Implement `SessionIDMiddleware`: validate `X-Session-ID` against UUID v4 regex from `07_SECURITY_MODEL.md` section 3.2; return HTTP 400 `INVALID_SESSION_ID` if malformed/absent; store validated ID in `request.state.session_id`.
4. Implement `LoggingMiddleware`: log request start and completion with structlog; redact `Authorization`, `X-Api-Key`, `X-Openai-Api-Key` header values.
5. Implement `ApiKeyStrippingMiddleware` — register **before** `LoggingMiddleware`: extract `X-Openai-Api-Key` into `request.state.openai_api_key`; mutate request headers to remove the key before `call_next`.
6. Implement all 12 error handler mappings from `05_APPLICATION_STRUCTURE.md` section 2.4. All responses follow `{"error_code", "message", "request_id"}` shape.
7. Test: malformed UUID returns 400; API key in request not present in captured log output; `X-Request-ID` echoed in response.

**Data Impact**

Schema changes: None | Migration required: No

**Test Plan**

Integration tests: 10 invalid UUID formats all return 400; `X-Openai-Api-Key` value absent from all structlog output fields; `LLMUnavailableError` → HTTP 503; unhandled `Exception` → HTTP 500 body without stack trace.

**Acceptance Criteria**

- All 5 middleware registered in correct order (key stripped before logging)
- `X-Openai-Api-Key` value never appears in any structlog output field (verified by test)
- All 12 error handlers produce `{"error_code", "message", "request_id"}` shaped responses
- `mypy src/sentinel/api/middleware.py src/sentinel/api/error_handlers.py` reports zero errors

**Rollback Strategy**

Revert `middleware.register(app)` call. Application continues without security properties.

**Estimated Complexity:** M

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (thinking) | Recommended Mode: thinking

Reason: Middleware registration order determines security properties. API key stripping on FastAPI's immutable request headers requires an explicit workaround — this is a correctness-critical security requirement.

---

**Context Strategy**

Start new chat? Yes — entering API layer. New subsystem.

Required files: `05_APPLICATION_STRUCTURE.md` (sections 2.3 middleware, 2.4 error handlers), `07_SECURITY_MODEL.md` (sections 3.2 and 4).  
NOT required: Domain engine docs, schema docs, infrastructure docs, frontend docs, deployment docs.

---

---

#### Task ID: T-029

**Title:** Guardrail Router and WebSocket Handler

**Phase:** 5

**Subsystem:** API Layer — Core Endpoint

**Description:**  
Implement `POST /v1/guardrail/submit` and `WS /ws/{request_id}`. The guardrail route invokes `SubmitPromptUseCase`. The WebSocket handler subscribes to the `EventBus` and streams stage events to the client.

**Scope Boundaries**

Files affected:

- `backend/src/sentinel/api/routers/guardrail.py`
- `backend/src/sentinel/websocket/handler.py`
- `tests/integration/api/test_guardrail_router.py`

Modules affected: `sentinel.api.routers`, `sentinel.websocket`

Explicitly NOT touching: Other routers, middleware, domain engines, frontend

**Implementation Steps**

1. Implement `POST /v1/guardrail/submit`: accept `GuardrailSubmitRequest`; extract `session_id` from `request.state.session_id` and `openai_api_key` from `request.state.openai_api_key`; validate prompt non-empty and ≤ 4000 chars; get `SubmitPromptUseCase` from `request.app.state.container`; call `use_case.execute()`; return `GuardrailResponse`.
2. Implement `WS /ws/{request_id}`: accept WebSocket, `EventBus.register(request_id)`, async loop reading from queue, send each event as JSON text. On disconnect: `EventBus.unregister(request_id)`.
3. Implement `routers.register(app)` in `sentinel/api/__init__.py` including all routers with `/v1` prefix and mounting WebSocket handler.
4. Integration tests: empty prompt → 422, prompt > 4000 chars → 400, missing session ID → 400, mocked orchestrator success → 200 with full `GuardrailResponse`, OpenAI without key → 400.

**Data Impact**

Schema changes: None | Migration required: No

**Test Plan**

Integration tests: 5 scenarios as described above.  
Manual: `POST /v1/guardrail/submit` with Ollama running and valid session returns complete response.

**Acceptance Criteria**

- Prompt validated before any use case call (empty/too-long rejected at route level)
- WebSocket handler unregisters from EventBus on client disconnect (no queue leak)
- WebSocket handler receives buffered events published before client connected
- `mypy src/sentinel/api/routers/guardrail.py src/sentinel/websocket/handler.py` reports zero errors

**Rollback Strategy**

Remove router files and `routers.register()` call. Application reverts to serving `/health/live` only.

**Estimated Complexity:** M

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (fast) | Recommended Mode: fast

Reason: FastAPI route from defined request/response schema is mechanical. WebSocket handler is a standard queue-drain pattern.

---

**Context Strategy**

Start new chat? No — continue from T-028.

Required files: `05_APPLICATION_STRUCTURE.md` (section 2.5 guardrail router and WebSocket), `GuardrailResponse` field list.  
NOT required: Domain engine docs, infrastructure docs, frontend docs, deployment docs.

---

---

#### Task ID: T-030

**Title:** KB, Analytics, Requests, Policy, and Health Routers

**Phase:** 5

**Subsystem:** API Layer — Supporting Endpoints

**Description:**  
Implement all remaining REST routers: `/v1/kb/documents`, `/v1/analytics`, `/v1/requests`, `/v1/policy`, and `/health`. Wire KB document upload to trigger background indexing. Health router checks Ollama availability for `/health/ready`.

**Scope Boundaries**

Files affected:

- `backend/src/sentinel/api/routers/kb.py`
- `backend/src/sentinel/api/routers/analytics.py`
- `backend/src/sentinel/api/routers/requests.py`
- `backend/src/sentinel/api/routers/policy.py`
- `backend/src/sentinel/api/routers/health.py`
- `tests/integration/api/test_kb_router.py`
- `tests/integration/api/test_health_router.py`

Modules affected: `sentinel.api.routers`

Explicitly NOT touching: Guardrail router, WebSocket handler, domain engines, frontend

**Implementation Steps**

1. `kb.py`: `POST /v1/kb/documents` validates MIME type (`text/plain`, `application/pdf`) and size ≤ `config.max_upload_size_bytes`; saves file; creates DB record; enqueues indexing. `GET` lists session-scoped documents. `DELETE` removes FAISS vectors then DB records. `POST /v1/kb/search` embeds query, queries FAISS, returns top-k chunks.
2. `analytics.py`: `GET /v1/analytics` calls `GetAnalyticsUseCase` with optional `date_from`/`date_to` params. Returns `AnalyticsSummary`.
3. `requests.py`: `GET /v1/requests` with pagination + filters. `GET /v1/requests/{id}` returns full audit detail. Returns `RequestNotFoundError` if ID not in session scope.
4. `policy.py`: `GET /v1/policy` returns current or default policy. `PUT /v1/policy` validates `block < warn < accept` (raise `PolicyValidationError` on violation), calls `PolicyRepository.create_snapshot()`.
5. `health.py`: `GET /health/live` always 200. `GET /health/ready` checks Ollama `health_check()` and DB `SELECT 1`; returns HTTP 200 if all ready, 503 if not.
6. Integration tests: file > 10MB → 413; `PUT /v1/policy` with `warn >= accept` → 422; `/health/ready` with mocked Ollama unavailable → 503.

**Data Impact**

Schema changes: None | Migration required: No

**Test Plan**

Integration tests: 6 scenarios as described above.

**Acceptance Criteria**

- KB upload validates MIME and size before writing any file to disk
- `/health/ready` returns 503 when Ollama health check fails
- `/v1/requests` is session-scoped: different session's request_id returns 404
- Policy `PUT` with invalid thresholds returns 422 before any DB write
- `mypy src/sentinel/api/routers/` reports zero errors across all 5 router files

**Rollback Strategy**

Each router file is independently removable via its `app.include_router()` registration.

**Estimated Complexity:** M

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (fast) | Recommended Mode: fast

Reason: These routers follow the same FastAPI patterns as the guardrail router — mechanical implementations of defined request/response schemas.

---

**Context Strategy**

Start new chat? No — continue from T-029.

Required files: `05_APPLICATION_STRUCTURE.md` (section 2.5 all router definitions).  
NOT required: Domain engine docs, infrastructure internals, frontend docs, deployment docs.

---

---

#### Task ID: T-031

**Title:** API Integration Test Suite

**Phase:** 5

**Subsystem:** API Layer — Testing and Phase 5 Gate

**Description:**  
Write the complete API integration test suite covering all critical routes. Tests use `httpx.AsyncClient` against a real FastAPI test app with in-memory SQLite and mocked LLM adapters. This is the Phase 5 completion gate.

**Scope Boundaries**

Files affected:

- `tests/integration/api/conftest.py`
- `tests/integration/api/test_guardrail_router.py` (additions)
- `tests/integration/api/test_kb_router.py` (additions)
- `tests/integration/api/test_policy_router.py`
- `tests/integration/api/test_analytics_router.py`
- `tests/integration/api/test_requests_router.py`

Modules affected: Test infrastructure only

Explicitly NOT touching: Domain engines, infrastructure, frontend

**Implementation Steps**

1. Write `conftest.py`: `test_app` fixture with real SQLite in-memory DB, mocked `OllamaAdapter` (deterministic `LLMResult`), mocked `DetoxifyClassifier` (all-zero safety scores), real `SentenceTransformerAdapter`. Provides `test_session_id` and `async_client`.
2. Complete `test_guardrail_router.py`: PII-masked prompt stored (original not retrievable), injection-detected → `guardrail_decision='block'`, Ollama mock returns valid completion → all response fields populated.
3. Write `test_policy_router.py`: GET defaults for new session, PUT saves and GET reflects update, PUT with invalid thresholds returns 422.
4. Write `test_analytics_router.py`: GET with no requests returns zero counts, GET after 3 submits returns correct aggregates.
5. Write `test_requests_router.py`: GET list paginated, GET `{id}` returns full audit detail with trace stages, GET `{id}` from different session returns 404.

**Data Impact**

Schema changes: None | Migration required: No

**Test Plan**

16+ integration test scenarios. `pytest tests/integration/api/ -v` must pass in under 60 seconds.

**Acceptance Criteria**

- All 16+ scenarios pass with zero flakiness across 3 consecutive runs
- Mocked `OllamaAdapter` used in all tests (no real Ollama dependency in CI)
- Original prompt never retrievable from any API response
- `GET /api/docs` returns HTTP 200 (OpenAPI schema valid)

**Rollback Strategy**

Test-only task. No production code modified.

**Estimated Complexity:** M

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (fast) | Recommended Mode: fast

Reason: Integration test generation from a defined API contract is mechanical once fixture infrastructure is established.

---

**Context Strategy**

Start new chat? No — continue from T-030.

Required files: `09_TESTING_STRATEGY.md` (API integration test section), `05_APPLICATION_STRUCTURE.md` (API contracts).  
NOT required: Domain engine docs, infrastructure docs, frontend docs, deployment docs.

---

---

### Phase 6 — Frontend

---

#### Task ID: T-032

**Title:** Shared Component Library and AppShell

**Phase:** 6

**Subsystem:** Frontend — Foundation Components

**Description:**  
Implement all shared primitive components, `AppShell` layout wrapper, `NavBar`, `PageContainer`, utility functions, TypeScript type definitions, and `sessionSlice` store initialization.

**Scope Boundaries**

Files affected:

- `frontend/src/components/shared/` (7 components)
- `frontend/src/components/layout/AppShell.tsx`, `NavBar.tsx`, `PageContainer.tsx`
- `frontend/src/store/sessionSlice.ts`
- `frontend/src/utils/formatters.ts`, `validators.ts`, `constants.ts`, `sessionId.ts`
- `frontend/src/types/api.ts`, `domain.ts`, `store.ts`

Modules affected: Frontend shared layer

Explicitly NOT touching: Page components, feature components, API client endpoint implementations, hooks

**Implementation Steps**

1. Implement `sessionId.ts`: `getOrCreateSessionId() -> string` reads `sessionStorage` or generates UUID v4 via `crypto.randomUUID()`.
2. Implement `sessionSlice.ts`: `initializeSession()` calls `getOrCreateSessionId()` and stores `sessionId`. Used by Axios interceptor from T-004.
3. Implement `types/api.ts`: TypeScript interfaces mirroring all Pydantic response schemas: `GuardrailResponse`, `ClaimResult`, `TraceStage`, `SafetyResult`, `AnalyticsSummary`, `RequestListItem`, `RequestDetail`, `KBDocument`, `PolicySnapshot`, `ApiError`.
4. Implement all 7 shared primitives with complete typed prop interfaces, no store access, no `any` types.
5. Implement `AppShell.tsx`: `<NavBar />` + `<Outlet />` + `<PrivacyNotice />` at footer. `NavBar.tsx`: 5 routes with `NavLink isActive` highlighting.
6. Implement `formatters.ts` (`formatConfidenceLabel`, `formatLatency`, `formatDecision`), `validators.ts` (`isValidApiKeyFormat`, `isValidPromptLength`), `constants.ts` (`MAX_PROMPT_LENGTH=4000`, `TERM_DEFINITIONS`).

**Data Impact**

Schema changes: None | Migration required: No

**Test Plan**

Unit tests: `ErrorBoundary` catches thrown error and renders fallback; `StatusBadge` renders correct label.  
Manual: `npm run dev` renders AppShell with all 5 nav links; `npm run type-check` passes.

**Acceptance Criteria**

- All shared components use only typed props (zero `any`)
- `sessionId.ts` returns same UUID across multiple calls in same browser session
- `TERM_DEFINITIONS` contains all terms from `00_PRODUCT_SPECIFICATION.md` tooltip glossary
- `npm run type-check` and `npm run lint` both pass

**Rollback Strategy**

Removing shared components breaks feature component imports explicitly at compile time.

**Estimated Complexity:** M

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (fast) | Recommended Mode: fast

Reason: Shared component generation from defined prop interfaces is mechanical. Type definitions mirroring Pydantic schemas are direct transcription.

---

**Context Strategy**

Start new chat? Yes — entering frontend subsystem. Completely different technology stack.

Required files: `05_APPLICATION_STRUCTURE.md` (frontend section: component taxonomy, store interfaces), `00_PRODUCT_SPECIFICATION.md` (UI specs and TERM_DEFINITIONS only).  
NOT required: All backend, schema, domain, infrastructure, security, deployment docs.

---

---

#### Task ID: T-033

**Title:** Playground Page — Input Form Components and Zustand Store

**Phase:** 6

**Subsystem:** Frontend — Playground Input

**Description:**  
Implement `PromptInput`, `ModelSelector`, `ApiKeyField`, `KbSelector`, `GuardrailToggles`, `PipelineProgressIndicator`, the complete `playgroundSlice` store, and the `guardrail.ts` API client function.

**Scope Boundaries**

Files affected:

- `frontend/src/store/playgroundSlice.ts`
- `frontend/src/components/playground/PromptInput.tsx`
- `frontend/src/components/playground/ModelSelector.tsx`
- `frontend/src/components/playground/ApiKeyField.tsx`
- `frontend/src/components/playground/KbSelector.tsx`
- `frontend/src/components/playground/GuardrailToggles.tsx`
- `frontend/src/components/playground/PipelineProgressIndicator.tsx`
- `frontend/src/api/endpoints/guardrail.ts`
- `frontend/src/pages/PlaygroundPage.tsx` (input panel only)

Modules affected: Frontend playground input layer

Explicitly NOT touching: Result display components, hooks

**Implementation Steps**

1. Implement complete `playgroundSlice.ts` from `05_APPLICATION_STRUCTURE.md` section 3.2: all state fields and action functions. `submitPrompt` action is a stub pending hook wiring in T-035.
2. `PromptInput.tsx`: textarea with character counter (`{length} / 4000`), disabled when `pipelineStatus === 'running'`, `data-testid="prompt-input"`.
3. `ApiKeyField.tsx`: password input, visible only when `modelProvider === 'openai'`, controlled from store, `data-testid="api-key-field"`.
4. `KbSelector.tsx`: dropdown from `kbSlice.documents`.
5. `GuardrailToggles.tsx`: 5 module flag toggles wired to `playgroundSlice.moduleFlags`.
6. `PipelineProgressIndicator.tsx`: 7 stage rows with idle/running/passed/failed status icons.
7. `api/endpoints/guardrail.ts`: `submit(request, headers) -> Promise<GuardrailResponse>` via Axios client.

**Data Impact**

Schema changes: None | Migration required: No

**Test Plan**

Unit tests: `PromptInput` character counter increments; `ApiKeyField` visible only with OpenAI selected.  
Manual: Typing updates counter; selecting OpenAI reveals API key field; `npm run type-check` passes.

**Acceptance Criteria**

- `ApiKeyField` cleared from store after every submit (success or error)
- `PromptInput` disabled when `pipelineStatus === 'running'` (no double-submit)
- All components have required `data-testid` attributes
- `npm run type-check` reports zero errors

**Rollback Strategy**

Each component file individually removable; compile-time import error in `PlaygroundPage`.

**Estimated Complexity:** M

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (fast) | Recommended Mode: fast

Reason: React component generation from defined prop interfaces and Zustand store spec is mechanical.

---

**Context Strategy**

Start new chat? No — continue from T-032.

Required files: `05_APPLICATION_STRUCTURE.md` (Zustand store interfaces and component taxonomy).  
NOT required: Backend docs, schema docs, domain docs.

---

---

#### Task ID: T-034

**Title:** Playground Page — Result Panels and Claim-Evidence Analysis

**Phase:** 6

**Subsystem:** Frontend — Playground Results

**Description:**  
Implement `ResponsePanel`, `ConfidenceBadge`, `DecisionLabel`, `GuardrailAnalysisPanel` (with claim-to-evidence linking), and `ExecutionTraceViewer`. Assemble the complete `PlaygroundPage` layout.

**Scope Boundaries**

Files affected:

- `frontend/src/components/playground/ResponsePanel.tsx`
- `frontend/src/components/playground/ConfidenceBadge.tsx`
- `frontend/src/components/playground/DecisionLabel.tsx`
- `frontend/src/components/analysis/GuardrailAnalysisPanel.tsx`
- `frontend/src/components/analysis/ClaimsList.tsx`
- `frontend/src/components/analysis/EvidenceList.tsx`
- `frontend/src/components/analysis/VerificationResults.tsx`
- `frontend/src/components/analysis/SignalBreakdownChart.tsx`
- `frontend/src/components/trace/ExecutionTraceViewer.tsx`
- `frontend/src/components/trace/TraceStageRow.tsx`
- `frontend/src/components/trace/TraceStageDetail.tsx`
- `frontend/src/pages/PlaygroundPage.tsx` (full assembly)

Modules affected: Frontend playground results layer

Explicitly NOT touching: Input form components, hooks, KB management page

**Implementation Steps**

1. `ConfidenceBadge.tsx`: renders score with color from `confidence_label` (high=green, medium=yellow, low=red). Must pass WCAG AA contrast on dark background.
2. `DecisionLabel.tsx`: chip with decision text and icon (accept=green checkmark, warn=yellow warning, block=red X, retry=blue arrow).
3. `ResponsePanel.tsx`: shows `final_response_text` for accept/warn; red alert with `block_reason` for block; empty state when no result.
4. `ClaimsList.tsx`: list of claims with verification status badges. Clicking calls `onClaimSelect(index)`. `data-testid="claim-item-{index}"`.
5. `EvidenceList.tsx`: filters to `selectedClaimIndex` evidence; relevance score as percentage bar; empty state when no claim selected.
6. `SignalBreakdownChart.tsx`: Recharts `BarChart` showing 4 confidence signal contributions.
7. `ExecutionTraceViewer.tsx`: accordion of `TraceStageRow`; click expands `TraceStageDetail` showing `stage_metadata_json`.
8. Assemble `PlaygroundPage.tsx`: two-column layout; results show `ConfidenceBadge + DecisionLabel + ResponsePanel + GuardrailAnalysisPanel + ExecutionTraceViewer`.

**Data Impact**

Schema changes: None | Migration required: No

**Test Plan**

Unit tests: `ConfidenceBadge` correct Tailwind color class per label; `ExecutionTraceViewer` expands on click.  
Manual: Submit prompt → all panels populate; click claim → evidence filters; blocked prompt → block panel only.

**Acceptance Criteria**

- `ConfidenceBadge` uses `confidence_label` (not raw score) for color — policy-relative
- Claim-to-evidence linking: clicking claim N filters `EvidenceList` to claim N's evidence only
- Blocked prompt: block reason shown; `final_response_text` never rendered
- `ExecutionTraceViewer` shows all 7 stages including `not_reached` (grayed out)
- `npm run type-check` reports zero errors

**Rollback Strategy**

Each result component independently removable; `PlaygroundPage` renders degraded but does not crash.

**Estimated Complexity:** M

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (fast) | Recommended Mode: fast

Reason: React component generation from defined taxonomy with known prop interfaces is mechanical.

---

**Context Strategy**

Start new chat? No — continue from T-033.

Required files: `05_APPLICATION_STRUCTURE.md` (component taxonomy section 4), `00_PRODUCT_SPECIFICATION.md` (confidence badge color specs).  
NOT required: Backend docs, schema docs.

---

---

#### Task ID: T-035

**Title:** usePipelineSubmit, usePipelineProgress, and WebSocket Integration

**Phase:** 6

**Subsystem:** Frontend — Data Fetching Hooks

**Description:**  
Implement `usePipelineSubmit` and `usePipelineProgress` hooks, and the full `WebSocketClient` implementation. After this task, the end-to-end Playground flow works: submit → real-time stage progress → final result. Apply all `data-testid` attributes.

**Scope Boundaries**

Files affected:

- `frontend/src/hooks/usePipelineSubmit.ts`
- `frontend/src/hooks/usePipelineProgress.ts`
- `frontend/src/api/websocket.ts` (full implementation)
- Updates to `PlaygroundPage.tsx` to wire hooks

Modules affected: Frontend hooks layer

Explicitly NOT touching: Component internal logic, store slices, API client endpoint definitions

**Implementation Steps**

1. Implement `usePipelineProgress` per `05_APPLICATION_STRUCTURE.md` section 3.3: `connectForRequest(requestId)` opens WebSocket, registers `onmessage` dispatching stage updates to `playgroundSlice`, exponential backoff reconnect (max 3 attempts: 500ms → 1s → 2s).
2. Implement `usePipelineSubmit` per `05_APPLICATION_STRUCTURE.md` section 3.3: client-side validation, set `pipelineStatus='running'`, call `guardrailApi.submit()`, on response set result + `'complete'`, on error set error + `'error'`, always `clearApiKey()` in `finally`.
3. Implement `api/websocket.ts`: `WebSocketClient` with `connect(requestId)`, `disconnect()`, `onStageUpdate(handler)`. Message parsing with `JSON.parse` try-catch. Reconnection logic.
4. Wire into `PlaygroundPage.tsx`: `const { submit, isRunning } = usePipelineSubmit()`. Submit button calls `submit()`.
5. Verify `data-testid` presence: `"submit-button"`, `"prompt-input"`, `"model-selector"`, `"api-key-field"`, `"confidence-badge"`, `"decision-label"`, `"claim-item-{n}"`, `"trace-stage-{name}"`.

**Data Impact**

Schema changes: None | Migration required: No

**Test Plan**

Unit tests: `usePipelineSubmit` — success updates store; error sets error state; API key cleared in both cases. `usePipelineProgress` — WebSocket message updates `stageStatuses`.  
Manual: Submit prompt to running API; observe stage progress updating; all result panels populate on completion.

**Acceptance Criteria**

- `clearApiKey()` called in `finally` block (tested: error path also clears key)
- `usePipelineProgress` reconnects up to 3 times before giving up
- Stage progress indicator shows current active stage during execution
- All `data-testid` attributes present (verified against E2E test fixture list)
- `npm run type-check` reports zero errors

**Rollback Strategy**

Hooks used only in `PlaygroundPage`. Reverting them renders the page non-functional (no submit).

**Estimated Complexity:** M

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (thinking) | Recommended Mode: thinking

Reason: WebSocket reconnection logic, `finally`-block API key clearing guarantee, and the ordering of WS registration before HTTP call (race condition avoidance) are concurrency-sensitive correctness requirements.

---

**Context Strategy**

Start new chat? No — continue from T-034.

Required files: `05_APPLICATION_STRUCTURE.md` (section 3.3: usePipelineSubmit and usePipelineProgress implementations).  
NOT required: Backend docs, schema docs, infrastructure docs.

---

---

#### Task ID: T-036

**Title:** Knowledge Base Management Page and Phase 6 Gate

**Phase:** 6

**Subsystem:** Frontend — KB Feature

**Description:**  
Implement the Knowledge Base Management page: `DocumentUploader` (with XHR progress), `DocumentList`, `DocumentStatusBadge`, `ChunkingPreview`, `useKnowledgeBase` hook, and full `kbSlice` store. Confirm end-to-end KB → Playground flow works. Phase 6 gate.

**Scope Boundaries**

Files affected:

- `frontend/src/pages/KnowledgeBasePage.tsx`
- `frontend/src/components/kb/DocumentUploader.tsx`
- `frontend/src/components/kb/DocumentList.tsx`
- `frontend/src/components/kb/DocumentStatusBadge.tsx`
- `frontend/src/components/kb/ChunkingPreview.tsx`
- `frontend/src/hooks/useKnowledgeBase.ts`
- `frontend/src/api/endpoints/kb.ts`
- `frontend/src/store/kbSlice.ts`

Modules affected: Frontend KB feature layer

Explicitly NOT touching: Playground components, analytics, policy, request explorer

**Implementation Steps**

1. Implement `useKnowledgeBase`: `fetchDocuments()` updates `kbSlice`; `uploadDocument(file)` uses `XMLHttpRequest` with `onprogress` for byte-level progress tracking; `deleteDocument(id)` calls DELETE endpoint; WebSocket event listener for `kb_status` events updates document status in real time.
2. `DocumentUploader.tsx`: drag-and-drop + file input; upload progress bar from `XHR.onprogress`; accepts `.txt` and `.pdf` only; pre-upload size validation (> 10MB rejected client-side before XHR).
3. `DocumentStatusBadge.tsx`: `pending`=gray, `indexing`=yellow+spinner, `ready`=green, `failed`=red+error tooltip.
4. `DocumentList.tsx`: list with badge; delete button with confirm dialog; empty state with instructional copy.
5. `ChunkingPreview.tsx`: shows first 3 chunks with character ranges.
6. Wire `KbSelector.tsx` to `kbSlice.documents` populated by `fetchDocuments()` on Playground page mount.
7. Phase 6 gate smoke test: upload TXT → status transitions to `ready` → select in Playground → submit prompt → evidence from document in Analysis Panel.

**Data Impact**

Schema changes: None | Migration required: No

**Test Plan**

Unit tests: `DocumentStatusBadge` correct color/spinner per status.  
Manual (Phase 6 gate): full upload → index → select → submit → evidence flow confirmed.  
Build gate: `npm run type-check` and `npm run build` both pass.

**Acceptance Criteria**

- Upload progress bar shows byte-level progress (not just start/complete)
- `DocumentStatusBadge` transitions to `ready` without page refresh (WebSocket-driven)
- Evidence from indexed document appears in `GuardrailAnalysisPanel` when KB selected
- `npm run type-check` and `npm run build` pass clean

**Rollback Strategy**

KB page is a separate route. Reverting has no impact on Playground functionality.

**Estimated Complexity:** M

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (fast) | Recommended Mode: fast

Reason: KB page components follow the same React patterns as the Playground components. XHR upload progress is a standard web API pattern.

---

**Context Strategy**

Start new chat? No — continue from T-035.

Required files: `05_APPLICATION_STRUCTURE.md` (KB component list), `00_PRODUCT_SPECIFICATION.md` (KB Management UX section).  
NOT required: Backend domain docs, infrastructure docs, security docs.

---

---

### Phase 7 — Analytics, Policy, SDK & Release Preparation

---

#### Task ID: T-037

**Title:** Analytics Dashboard — Backend Endpoint and Frontend Components

**Phase:** 7

**Subsystem:** Analytics — Full Stack

**Description:**  
Implement `GET /v1/analytics` backend endpoint and all 6 analytics frontend components using Recharts. Implement `useAnalytics` hook with time-range filtering. Assemble `AnalyticsDashboardPage`.

**Scope Boundaries**

Files affected:

- `backend/src/sentinel/application/use_cases/get_analytics.py`
- `backend/src/sentinel/api/routers/analytics.py` (full implementation)
- `frontend/src/pages/AnalyticsDashboardPage.tsx`
- `frontend/src/components/analytics/` (all 6 components)
- `frontend/src/hooks/useAnalytics.ts`
- `frontend/src/api/endpoints/analytics.ts`
- `frontend/src/store/analyticsSlice.ts`

Modules affected: Analytics full stack

Explicitly NOT touching: Request Explorer, Policy Config, SDK, deployment

**Implementation Steps**

1. Implement `GetAnalyticsUseCase.execute(session_id, date_from?, date_to?) -> AnalyticsSummary`: query `AnalyticsRepository` counters; compute `hallucination_rate`, `avg_confidence`, `avg_latency_ms`; return chart-ready `AnalyticsSummary`.
2. Implement `GET /v1/analytics` (full implementation replacing T-030 stub).
3. `AnalyticsDashboardPage.tsx`: time-range selector (All Time / Last 100 / Last 24h); `SummaryMetricsRow` (4 metric cards); 5 Recharts charts in 2-column grid; empty state when `total_requests === 0`.
4. Implement each chart: `DecisionDistributionChart` (PieChart), `HallucinationRateChart` (LineChart), `ConfidenceHistogram` (BarChart), `LatencyLineChart` (LineChart), `TokenUsageChart` (stacked BarChart).
5. `useAnalytics`: fetch on mount and on time-range change; 300ms debounce on time-range selector.

**Data Impact**

Schema changes: None | Migration required: No

**Test Plan**

Manual: Submit 5 prompts → navigate to Analytics → all charts render; change time range → charts update.

**Acceptance Criteria**

- Charts render without error when only one model has been used
- Time-range filter correctly scopes to the selected period
- `avg_latency_ms` derived from `sum_latency_ms / total_requests` (not full `requests` table scan)
- `npm run type-check` passes

**Rollback Strategy**

Analytics is a separate route and endpoint. Reverting has no impact on the Playground.

**Estimated Complexity:** M

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (fast) | Recommended Mode: fast

Reason: Analytics chart generation follows standard Recharts patterns. Backend use case is straightforward aggregation math over pre-computed counters.

---

**Context Strategy**

Start new chat? Yes — new phase. Reset context.

Required files: `05_APPLICATION_STRUCTURE.md` (analytics components section), `03_DATABASE_SCHEMA.md` (analytics_counters table only).  
NOT required: Domain engine docs, security docs, deployment docs.

---

---

#### Task ID: T-038

**Title:** Request Explorer — List, Filter, Detail, and Replay

**Phase:** 7

**Subsystem:** Request Explorer — Full Stack

**Description:**  
Implement the Request Explorer page: paginated list, decision-type filtering, request detail split-panel (full audit record with trace viewer), `ReplayButton` with PII guard, `POST /v1/requests/{id}/replay` backend endpoint, and deep-link support.

**Scope Boundaries**

Files affected:

- `backend/src/sentinel/application/use_cases/replay_request.py`
- `backend/src/sentinel/api/routers/requests.py` (add replay endpoint)
- `frontend/src/pages/RequestExplorerPage.tsx`
- `frontend/src/components/explorer/` (all 4 components)
- `frontend/src/hooks/useRequestExplorer.ts`
- `frontend/src/api/endpoints/requests.ts`

Modules affected: Request Explorer full stack

Explicitly NOT touching: Analytics, policy, SDK, deployment

**Implementation Steps**

1. Implement `ReplayRequestUseCase.execute(original_id, session_id)`: load request, verify session ownership (404 if not in session), check `pii_detected` (403 `ReplayNotAllowedError` if true), call `SubmitPromptUseCase` with stored `prompt_masked_text`.
2. Implement `POST /v1/requests/{request_id}/replay` route.
3. `RequestExplorerPage.tsx`: two-panel layout; URL param `requestId` pre-selects on load.
4. `RequestList.tsx` + `RequestListItem.tsx`: paginated; shows decision label, confidence score, created_at, latency.
5. `RequestDetailPanel.tsx`: masked prompt, decision, confidence badge, full `ExecutionTraceViewer`, claims + evidence (reuses Phase 6 components).
6. `ReplayButton.tsx`: disabled with tooltip `"Replay not available — prompt contains PII"` when `pii_detected=true`.

**Data Impact**

Schema changes: None | Migration required: No

**Test Plan**

Integration tests: replay with `pii_detected=true` → 403; replay of non-PII request → returns new `GuardrailResponse`.  
Manual: deep-link to `/requests/{id}` pre-selects request; replay creates new request, navigates to Playground.

**Acceptance Criteria**

- PII-detected requests have `ReplayButton` disabled with tooltip
- Replay creates a new DB row (does not mutate original)
- Deep-link pre-selects request without flash of unselected state
- Request list scoped to session: new tab/session shows empty list
- `npm run type-check` passes

**Rollback Strategy**

Request Explorer is a separate route. Reverting has no impact on Playground or Analytics.

**Estimated Complexity:** M

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (fast) | Recommended Mode: fast

Reason: Standard list-detail CRUD UI pattern. Replay is a straightforward use case composition.

---

**Context Strategy**

Start new chat? No — continue from T-037.

Required files: `05_APPLICATION_STRUCTURE.md` (request explorer components), `00_PRODUCT_SPECIFICATION.md` (request explorer UX section).  
NOT required: Backend infrastructure docs, domain engine docs.

---

---

#### Task ID: T-039

**Title:** Policy Configuration — Backend and Frontend

**Phase:** 7

**Subsystem:** Policy Configuration — Full Stack

**Description:**  
Implement `PolicyConfigPage` with drag-and-drop fallback priority ordering (via `@dnd-kit`), threshold sliders, category toggles, and module flag toggles. Implement full `policySlice` store with draft/saved state and unsaved-changes tracking. Wire to existing `/v1/policy` endpoints.

**Scope Boundaries**

Files affected:

- `frontend/src/pages/PolicyConfigPage.tsx`
- `frontend/src/components/policy/ThresholdSliders.tsx`
- `frontend/src/components/policy/CategoryToggles.tsx`
- `frontend/src/components/policy/FallbackPriorityList.tsx`
- `frontend/src/components/policy/ModuleToggles.tsx`
- `frontend/src/store/policySlice.ts` (full implementation)
- `frontend/src/hooks/usePolicy.ts`
- `frontend/src/api/endpoints/policy.ts`

Modules affected: Frontend policy feature layer

Explicitly NOT touching: Backend policy router (done in T-030), SDK, deployment

**Implementation Steps**

1. Implement `policySlice.ts` per `05_APPLICATION_STRUCTURE.md` section 3.2: `savedPolicy`, `draftPolicy`, `hasUnsavedChanges`, `updateDraft()`, `savePolicy()`, `discardChanges()`, `reorderFallbackPriority(from, to)`.
2. `usePolicy` hook: `fetchPolicy()` on mount loads into both `savedPolicy` and `draftPolicy`; `savePolicy()` validates `block < warn < accept` client-side before calling `PUT /v1/policy`.
3. `ThresholdSliders.tsx`: 3 range inputs; disable save and show error when `warn >= accept`.
4. `FallbackPriorityList.tsx`: `@dnd-kit/core` `DndContext` + `@dnd-kit/sortable` `SortableContext` for the 4 fallback strategy items; each item has drag handle icon.
5. `CategoryToggles.tsx`: text input to add restricted categories + tag list with delete buttons.
6. `PolicyConfigPage.tsx`: unsaved changes banner; "Save Policy" and "Discard Changes" buttons.

**Data Impact**

Schema changes: None | Migration required: No

**Test Plan**

Unit tests: `ThresholdSliders` save disabled when `warn >= accept`; `FallbackPriorityList` items reorder correctly after drag.  
Manual: set accept threshold to 95 → next prompt is warned not accepted; drag-drop reorder → persists after save.

**Acceptance Criteria**

- Threshold slider validation prevents save when invariant violated (client-side and API-level)
- Drag-and-drop works on touch devices (dnd-kit handles pointer and touch)
- Unsaved changes banner appears immediately on any draft mutation
- Policy changes take effect on the next request only
- `npm run type-check` passes

**Rollback Strategy**

Policy config is a separate route. Last saved policy remains in DB.

**Estimated Complexity:** M

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (fast) | Recommended Mode: fast

Reason: Standard form management patterns. `@dnd-kit` integration is well-documented.

---

**Context Strategy**

Start new chat? No — continue from T-038.

Required files: `05_APPLICATION_STRUCTURE.md` (policySlice interface and policy components).  
NOT required: Backend domain docs, infrastructure docs, security docs, deployment docs.

---

---

#### Task ID: T-040

**Title:** Python Developer SDK

**Phase:** 7

**Subsystem:** SDK

**Description:**  
Implement the Python developer SDK: sync `SentinelClient`, async `AsyncSentinelClient`, typed response models, exception hierarchy, SDK README with 5 usage examples. Package as installable Python package with unit tests.

**Scope Boundaries**

Files affected:

- `sdk/python/pyproject.toml`
- `sdk/python/sentinel_sdk/__init__.py`
- `sdk/python/sentinel_sdk/client.py`
- `sdk/python/sentinel_sdk/async_client.py`
- `sdk/python/sentinel_sdk/models.py`
- `sdk/python/sentinel_sdk/exceptions.py`
- `sdk/python/README.md`
- `sdk/python/tests/test_client.py`

Modules affected: SDK package only (independent from backend)

Explicitly NOT touching: Backend code, frontend, deployment

**Implementation Steps**

1. `pyproject.toml`: package `sentinel-sdk`, deps: `httpx`, `pydantic>=2`. No ML dependencies.
2. `models.py`: Pydantic models mirroring API response schemas: `GuardrailResponse`, `ClaimResult`, `TraceStage`, `SafetyResult`, `TokenUsage`, `PolicyOverrides`.
3. `exceptions.py`: `SentinelSDKError`, `AuthenticationError`, `PromptRejectedError`, `LLMUnavailableError`, `TimeoutError`, `ServerError`. Each carries HTTP status code and structured error body.
4. `client.py` (`SentinelClient`): `httpx.Client`. `submit(prompt, model_provider, model_name?, kb_id?, openai_api_key?, policy_overrides?) -> GuardrailResponse`. Auto-generates `session_id` UUID if not provided.
5. `async_client.py` (`AsyncSentinelClient`): same interface using `httpx.AsyncClient`. Supports `async with` context manager.
6. `README.md`: 5 usage examples (basic, OpenAI key, KB, async, error handling).
7. `test_client.py` using `respx`: success → `GuardrailResponse`; 503 → `LLMUnavailableError`; 400 PROMPT_TOO_LONG → `PromptRejectedError`; auto-generated session_id is valid UUID v4.

**Data Impact**

Schema changes: None | Migration required: No

**Test Plan**

Unit tests: 4 scenarios with `respx` mocks (no real API calls).  
Manual: `pip install -e sdk/python` + copy-paste README example 1 into REPL → returns `GuardrailResponse`.

**Acceptance Criteria**

- `pip install -e sdk/python` installs without errors
- Developer can submit in 5 lines of Python using README example
- All exception types map correctly to HTTP error codes
- `AsyncSentinelClient` supports `async with` context manager
- `mypy sdk/python/sentinel_sdk/` reports zero errors

**Rollback Strategy**

Completely independent package. Removing has zero impact on backend or frontend.

**Estimated Complexity:** M

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (fast) | Recommended Mode: fast

Reason: SDK generation from defined API contract is mechanical. Sync/async httpx client pattern is well-established.

---

**Context Strategy**

Start new chat? Yes — completely independent subsystem.

Required files: `05_APPLICATION_STRUCTURE.md` (API router definitions — the SDK's contract), `GuardrailResponse` Pydantic model definition.  
NOT required: Domain engine docs, infrastructure docs, schema docs, frontend docs, security docs.

---

---

#### Task ID: T-041

**Title:** Prometheus Metrics, Export Endpoint, and Session Cleanup Worker

**Phase:** 7

**Subsystem:** Observability and Maintenance

**Description:**  
Implement three independent maintenance features: `GET /metrics` Prometheus endpoint (gated by `ENABLE_METRICS=true`), `GET /v1/requests/export` CSV/JSON endpoint, and `session_cleanup_worker` coroutine for expired session deletion.

**Scope Boundaries**

Files affected:

- `backend/src/sentinel/api/routers/metrics.py`
- `backend/src/sentinel/api/routers/requests.py` (add export endpoint)
- `backend/src/sentinel/infrastructure/background/cleanup_worker.py`
- `frontend/src/components/explorer/` (add Export button)
- `tests/integration/api/test_metrics.py`

Modules affected: API routing, background workers, frontend export UI

Explicitly NOT touching: Analytics dashboard, SDK, deployment scripts

**Implementation Steps**

1. `GET /metrics`: add `prometheus-client`; register `guardrail_requests_total{decision,model_provider}`, `guardrail_pipeline_latency_seconds` (histogram), `guardrail_confidence_score` (histogram), `llm_adapter_calls_total{provider,status}`; mount via `make_asgi_app()` at `/metrics` gated by `config.enable_metrics`.
2. `GET /v1/requests/export?format=csv|json`: query all session requests; serialize to CSV or JSON; return `StreamingResponse` with correct `Content-Disposition`. PII-masked fields exported as-is.
3. `session_cleanup_worker` coroutine: 24h sleep loop; query sessions older than `config.session_retention_days`; for each: remove FAISS vectors, delete files from `LocalFileStorage`, delete session row (cascades). Log: `sessions_deleted`, `files_removed`, `bytes_freed`.
4. Wire cleanup worker into `ApplicationContainer.initialize()` as `asyncio.create_task()`.
5. Add "Export CSV" button to `RequestExplorerPage`.

**Data Impact**

Schema changes: None | Migration required: No

**Test Plan**

Integration tests: `GET /metrics` with `ENABLE_METRICS=true` → body contains `guardrail_requests_total`; `GET /metrics` with `ENABLE_METRICS=false` → 404; export → correct `Content-Type: text/csv` with correct headers; cleanup worker unit test: session with `last_active_at` 8 days ago + `RETENTION_DAYS=7` → deleted.

**Acceptance Criteria**

- Metrics only accessible when `ENABLE_METRICS=true` (not publicly exposed by default)
- CSV export includes all session requests, PII-masked as stored
- Cleanup worker deletes FAISS vectors before deleting KB document DB rows
- Cleanup worker logs structured statistics on every run
- `mypy src/sentinel/api/routers/metrics.py` reports zero errors

**Rollback Strategy**

Each feature independently revertable: remove metrics route, remove export endpoint, cancel cleanup task.

**Estimated Complexity:** M

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (fast) | Recommended Mode: fast

Reason: All three follow known patterns (prometheus-client, CSV streaming, cleanup loop).

---

**Context Strategy**

Start new chat? No — continue from T-040 context.

Required files: `08_BACKUP_AND_RECOVERY.md` (session cleanup section), `03_DATABASE_SCHEMA.md` (sessions table for cleanup logic).  
NOT required: Domain engine docs, frontend hook internals, SDK docs.

---

---

#### Task ID: T-042

**Title:** Production Deployment — Fly.io Configuration and CI Deploy Workflow

**Phase:** 7

**Subsystem:** Deployment

**Description:**  
Configure production deployment on Fly.io: write `fly.toml`, configure persistent volumes, set production environment secrets, configure Caddy for TLS and SPA serving, implement GitHub Actions `deploy.yml`, and run a smoke-tested production deployment.

**Scope Boundaries**

Files affected:

- `fly.toml`
- `.github/workflows/deploy.yml` (full implementation)
- `docker/Caddyfile` (production configuration)
- `scripts/smoke_test.py`

Modules affected: Deployment infrastructure only

Explicitly NOT touching: Application source, domain engines, frontend components

**Implementation Steps**

1. `fly.toml`: 1GB memory, 1 shared CPU, `/data` persistent volume, health check `GET /health/ready` (30s interval, 60s startup timeout).
2. Fly.io secrets: `DATABASE_URL`, `FAISS_INDEX_DIR`, `UPLOAD_DIR`, `LOG_LEVEL`, `CORS_ORIGINS`. Verify no secrets in `fly.toml`.
3. Production `Caddyfile`: automatic TLS via Caddy; HTTP → HTTPS redirect; `reverse_proxy /v1/* localhost:8000`; `reverse_proxy /ws/* localhost:8000`; SPA catch-all `try_files {path} /index.html`; rate limiting 30 req/min per IP.
4. `deploy.yml`: trigger on push to `main` after all CI checks pass; `docker build --target production` + `flyctl deploy`.
5. `scripts/smoke_test.py`: `GET /health/ready` → 200; `POST /v1/guardrail/submit` with benign prompt + OpenAI key → `guardrail_decision` present; `GET /` → 200.

**Data Impact**

Schema changes: None | Migration required: Alembic runs at app startup automatically on first deploy.

**Test Plan**

Manual: run `smoke_test.py` against production URL — all assertions pass.

**Acceptance Criteria**

- Production URL publicly accessible via HTTPS; HTTP → HTTPS redirect enforced
- No secrets in any committed file
- `GET /health/ready` returns 200 on production URL
- SPA routing works (`/analytics` directly returns correct React page, not 404)
- Rate limiting triggers at 31+ req/min from single IP
- Smoke test script passes all assertions

**Rollback Strategy**

`flyctl releases list` + `flyctl deploy --image <previous-image-id>`. One-command rollback.

**Estimated Complexity:** M

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (fast) | Recommended Mode: fast

Reason: Deployment configuration is mechanical. Fly.io TOML follows a standard format.

---

**Context Strategy**

Start new chat? Yes — deployment is a distinct operational concern.

Required files: `10_DEPLOYMENT_WORKFLOW.md`, `08_BACKUP_AND_RECOVERY.md` (backup scripts section).  
NOT required: Domain engine docs, schema docs, frontend component docs.

---

---

#### Task ID: T-043

**Title:** E2E Test Suite (Playwright)

**Phase:** 7

**Subsystem:** Testing — End-to-End

**Description:**  
Write the Playwright E2E test suite covering 5 critical user flows: playground submit with WebSocket progress, trace viewer interaction, KB document upload, policy config save-and-verify, and analytics dashboard after data population.

**Scope Boundaries**

Files affected:

- `tests/e2e/conftest.py`
- `tests/e2e/test_playground_submit.py`
- `tests/e2e/test_trace_viewer.py`
- `tests/e2e/test_kb_upload.py`
- `tests/e2e/test_policy_config.py`
- `tests/e2e/test_analytics_dashboard.py`

Modules affected: Test infrastructure only

Explicitly NOT touching: Production application code

**Implementation Steps**

1. `conftest.py`: start backend via `subprocess.Popen` with test SQLite DB; start Vite preview server; initialize `async_playwright()`. Yield `page` fixture. Tear down both servers on completion.
2. `test_playground_submit.py`: fill `data-testid="prompt-input"`, click submit, wait for `data-testid="confidence-badge"` visible within 30s, assert `data-testid="decision-label"` non-empty.
3. `test_trace_viewer.py`: after submit, assert 7 stage rows, click first → detail panel expands with non-empty metadata.
4. `test_kb_upload.py`: upload test TXT, wait for `data-testid="document-status-ready"` (max 60s), select KB in Playground, submit prompt, assert evidence panel populated.
5. `test_policy_config.py`: drag accept threshold slider to 95, save, submit prompt, assert decision is `accept_with_warning`.
6. `test_analytics_dashboard.py`: submit 3 requests, navigate to analytics, assert `SummaryMetricsRow` shows `Total Requests: 3`.

**Data Impact**

Schema changes: None | Migration required: No

**Test Plan**

All tests are E2E. Run in `test-e2e` CI job separately from `test-unit`. Pass on 3 consecutive runs without modification.

**Acceptance Criteria**

- All 5 E2E scenarios pass in headless Chrome
- Non-flaky: pass on 3 consecutive runs
- Complete in under 5 minutes total
- Use `data-testid` attributes exclusively (no CSS selectors)
- Skipped gracefully when Ollama unavailable

**Rollback Strategy**

Test-only. No production code modified. Remove failing test and investigate independently.

**Estimated Complexity:** M

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (fast) | Recommended Mode: fast

Reason: Playwright test generation from defined user flows and `data-testid` attributes is mechanical.

---

**Context Strategy**

Start new chat? No — continue from T-042.

Required files: `09_TESTING_STRATEGY.md` (E2E section), compiled `data-testid` list from T-033 through T-036.  
NOT required: Domain engine docs, infrastructure docs, schema docs.

---

---

#### Task ID: T-044

**Title:** Performance Benchmarks, Failure Injection Tests, and Backup Scripts

**Phase:** 7

**Subsystem:** Hardening and Operations

**Description:**  
Implement performance benchmark suite, failure injection tests, and production backup/validate-restore scripts. Ensures latency and reliability requirements are met before public launch.

**Scope Boundaries**

Files affected:

- `tests/performance/test_pipeline_latency.py`
- `tests/performance/test_embedding_throughput.py`
- `tests/performance/test_faiss_query_latency.py`
- `tests/failure_injection/test_ollama_unavailable.py`
- `tests/failure_injection/test_db_write_failure.py`
- `scripts/backup.py`
- `scripts/validate_restore.py`

Modules affected: Test infrastructure and operations scripts

Explicitly NOT touching: Production application code

**Implementation Steps**

1. `test_pipeline_latency.py`: benchmark `SubmitPromptUseCase.execute()` with mocked LLM over 50 runs via `pytest-benchmark`; assert P95 < 500ms (excluding LLM call).
2. `test_embedding_throughput.py`: benchmark `embed_batch(100 texts)` over 10 runs; assert > 50 texts/second.
3. `test_faiss_query_latency.py`: pre-populate 10,000 vectors; benchmark `query(vector, top_k=5)` over 1,000 runs; assert P95 < 50ms.
4. `test_ollama_unavailable.py`: force `LLMUnavailableError`; assert HTTP 503 (not 500), `requests.status='failed'`, no `GuardrailDecision` written.
5. `test_db_write_failure.py`: mock `AuditService.persist()` to raise `SQLAlchemyError` mid-transaction; assert `requests.status='failed'` and zero child rows committed.
6. `scripts/backup.py`: timestamped directory; copy SQLite (flush WAL via `PRAGMA wal_checkpoint(TRUNCATE)` first); copy FAISS index directory; SHA-256 checksums; write `backup_manifest.json`. Optional S3 upload if `S3_BACKUP_BUCKET` set.
7. `scripts/validate_restore.py`: read `backup_manifest.json`, verify all checksums, run `PRAGMA integrity_check` on SQLite, log result.

**Data Impact**

Schema changes: None | Migration required: No

**Test Plan**

Performance: `pytest tests/performance/ -m performance --benchmark-only` — all within thresholds.  
Failure injection: `pytest tests/failure_injection/ -v` — all pass.  
Operations: `python scripts/backup.py` then `python scripts/validate_restore.py` — both exit 0.

**Acceptance Criteria**

- P95 pipeline latency (excluding LLM) < 500ms
- FAISS query P95 < 50ms for 10,000 vectors
- Ollama unavailable → HTTP 503, `requests.status='failed'`
- DB write failure → `requests.status='failed'`, zero partial commit
- Backup produces verifiable SHA-256 manifest
- `validate_restore.py` exits 0 on valid backup

**Rollback Strategy**

Test-only and script-only. No production code modified.

**Estimated Complexity:** M

---

**LLM Execution Assignment**

Recommended Model: Claude Sonnet (fast) | Recommended Mode: fast

Reason: Performance tests, backup scripts, and failure injection tests follow standard patterns.

---

**Context Strategy**

Start new chat? No — continue from T-043.

Required files: `08_BACKUP_AND_RECOVERY.md`, `09_TESTING_STRATEGY.md` (performance and failure injection sections).  
NOT required: Frontend docs, domain engine docs, API design docs.

---

---

### Final Validation Milestones

---

#### Milestone M-0: Infrastructure Ready — after T-001 through T-005

| Check | Pass Condition |
|---|---|
| `uv sync` in CI | Exit 0, no version conflicts |
| `pre-commit run --all-files` | Zero violations |
| `docker compose up` | All services start without errors |
| `alembic current` | Exits 0 with no error |
| `npm run type-check` | Zero type errors |
| All 3 CI workflows | Pass green on `main` |

---

#### Milestone M-1: Database Layer Complete — after T-006 through T-009

| Check | Pass Condition |
|---|---|
| `alembic upgrade head` (SQLite + PostgreSQL) | All 10 tables created |
| `alembic downgrade base` | All tables dropped cleanly |
| `alembic check` | "No new upgrade operations detected" |
| `pytest tests/migration/test_constraints.py` | All FK/CHECK violations raise `IntegrityError` |
| `pytest tests/migration/test_indexes.py` | All 15+ indexes confirmed |
| `mypy src/sentinel/infrastructure/db/` | Zero errors |

---

#### Milestone M-2: Domain Engine Complete — after T-010 through T-015

| Check | Pass Condition |
|---|---|
| `pytest tests/unit/domain/ -v` | Zero failures |
| `pytest --cov=sentinel/domain --cov-fail-under=95` | ≥ 95% line coverage |
| Determinism test | Identical `GuardrailDecision` across 3 consecutive runs |
| Safety override invariant | `test_safety_override_beats_confidence_100` passes |
| Scoring boundaries | All 3 threshold boundary cases correct |
| `mypy src/sentinel/domain/ --strict` | Zero errors |

---

#### Milestone M-3: Infrastructure Adapters Complete — after T-016 through T-022

| Check | Pass Condition |
|---|---|
| `pytest tests/integration/ -v` | Zero failures |
| FAISS remove + query | Removed vector never returned in query results |
| Embedding dimension | `embed("test")` → shape `(384,)` |
| Detoxify dispatch | Completes within 10 seconds |
| Path traversal guard | `../` in filename sanitized to safe filename |
| UPSERT correctness | Analytics counter incremented, not overwritten |
| `mypy src/sentinel/infrastructure/` | Zero errors |

---

#### Milestone M-4: Application Layer Complete — after T-023 through T-027

| Check | Pass Condition |
|---|---|
| End-to-end Python call | `await use_case.execute()` returns complete `GuardrailResponse` |
| Short-circuit on block | LLM adapter mock call count = 0 after injection block |
| Audit atomicity | Forced mid-transaction error → zero rows committed |
| PII not stored | Original prompt absent from all DB columns |
| Retry termination | `MAX_RETRIES_EXCEEDED` after exactly `max_retries + 1` attempts |
| KB indexing | Document transitions `pending → ready` with queryable FAISS vectors |
| `pytest tests/consistency/ -v` | Zero failures |
| `mypy src/sentinel/application/` | Zero errors |

---

#### Milestone M-5: API Layer Complete — after T-028 through T-031

| Check | Pass Condition |
|---|---|
| API key log test | Zero key occurrences in any captured structlog output field |
| Session validation | All 10 malformed UUID formats return 400 |
| `pytest tests/integration/api/ -v` | Zero failures |
| `GET /api/docs` | HTTP 200 (valid OpenAPI schema) |
| Health + Ollama down | `/health/ready` returns 503 |
| Cross-session isolation | Different session's request_id returns 404 |
| `mypy src/sentinel/api/` | Zero errors |

---

#### Milestone M-6: Frontend Complete — after T-032 through T-036

| Check | Pass Condition |
|---|---|
| `npm run type-check` | Zero errors |
| `npm run lint` | Zero errors |
| `npm run build` | Exits 0, no warnings |
| Playground submission | Full result renders within 30s with Ollama running |
| Blocked prompt | Block panel rendered, no response text visible |
| KB flow | Document → `ready` → selected → evidence in analysis panel |
| Claim linking | Clicking claim N filters evidence to claim N |
| API key cleared | `openaiApiKey` empty in store after submit (success and error) |

---

#### Milestone M-7: Release Ready — after T-037 through T-044

| Check | Pass Condition |
|---|---|
| `pytest tests/e2e/ -v` (3× runs) | All 5 scenarios pass, zero flakiness |
| `pytest tests/performance/ -m performance` | All benchmarks within thresholds |
| `pytest tests/failure_injection/ -v` | All failure scenarios produce correct HTTP responses |
| `python scripts/smoke_test.py` | All assertions pass against production URL |
| `python scripts/validate_restore.py` | All checksums verified, integrity check OK |
| SDK smoke test | `pip install -e sdk/python` + submit → `GuardrailResponse` returned |
| HTTPS enforcement | `curl http://…` → 301 redirect to HTTPS |
| Rate limiting | Requests 31–60/min from single IP receive 429 |
| Privacy notice | Visible in playground footer |
| Production health | `GET /health/ready` → HTTP 200 |

---

## Task Index

| ID | Title | Phase | Complexity | Model |
|---|---|---|---|---|
| T-001 | Monorepo Scaffold and Pre-Commit Gates | 0 | S | thinking |
| T-002 | Docker Compose Stack and Dockerfile | 0 | S | fast |
| T-003 | GitHub Actions CI Pipeline | 0 | XS | fast |
| T-004 | Frontend Scaffold — Vite + React + Tailwind | 0 | S | fast |
| T-005 | Alembic Environment Initialization | 0 | XS | thinking |
| T-006 | Initial Alembic Migration — All 10 Tables | 1 | M | thinking |
| T-007 | SQLAlchemy ORM Models | 1 | M | fast |
| T-008 | Repository Base and Interface Stubs | 1 | S | fast |
| T-009 | Database Migration Test Suite | 1 | S | fast |
| T-010 | Core Domain Value Objects and PipelineContext | 2 | S | thinking |
| T-011 | InjectionDetector and PIIDetector | 2 | M | thinking |
| T-012 | PolicyFilter, RiskScorer, PromptValidationEngine | 2 | S | fast |
| T-013 | ConfidenceScoringEngine | 2 | M | thinking |
| T-014 | GuardrailDecisionEngine and FallbackStrategyEngine | 2 | M | thinking |
| T-015 | Domain Coverage Gate | 2 | S | fast |
| T-016 | Repository Implementations — Sessions, Policy, Analytics | 3 | M | fast |
| T-017 | Repository Implementations — Requests and KB | 3 | M | fast |
| T-018 | FAISS Vector Store | 3 | M | thinking |
| T-019 | SentenceTransformer Embedding Adapter | 3 | S | thinking |
| T-020 | OllamaAdapter and OpenAIAdapter | 3 | M | fast |
| T-021 | DetoxifyClassifier and TextChunker | 3 | M | thinking |
| T-022 | LocalFileStorage and Infrastructure Test Consolidation | 3 | S | fast |
| T-023 | ApplicationContainer and FastAPI Factory | 4 | M | thinking |
| T-024 | LLMExecutionLayer and HallucinationDetectionEngine | 4 | M | thinking |
| T-025 | OutputSafetyFilter and GuardrailPipelineOrchestrator | 4 | L | thinking |
| T-026 | SubmitPromptUseCase, AuditService, SessionService | 4 | M | thinking |
| T-027 | KB Indexing Worker and EventBus | 4 | M | thinking |
| T-028 | Middleware Stack and Global Error Handlers | 5 | M | thinking |
| T-029 | Guardrail Router and WebSocket Handler | 5 | M | fast |
| T-030 | KB, Analytics, Requests, Policy, Health Routers | 5 | M | fast |
| T-031 | API Integration Test Suite | 5 | M | fast |
| T-032 | Shared Component Library and AppShell | 6 | M | fast |
| T-033 | Playground — Input Form Components and Store | 6 | M | fast |
| T-034 | Playground — Result Panels and Analysis | 6 | M | fast |
| T-035 | usePipelineSubmit, usePipelineProgress, WebSocket | 6 | M | thinking |
| T-036 | Knowledge Base Management Page | 6 | M | fast |
| T-037 | Analytics Dashboard — Backend and Frontend | 7 | M | fast |
| T-038 | Request Explorer — List, Filter, Detail, Replay | 7 | M | fast |
| T-039 | Policy Configuration — Backend and Frontend | 7 | M | fast |
| T-040 | Python Developer SDK | 7 | M | fast |
| T-041 | Prometheus Metrics, Export, Session Cleanup | 7 | M | fast |
| T-042 | Production Deployment — Fly.io and CI Deploy | 7 | M | fast |
| T-043 | E2E Test Suite (Playwright) | 7 | M | fast |
| T-044 | Performance Benchmarks, Failure Injection, Backups | 7 | M | fast |

**Total Tasks: 44**  
**thinking model assignments: 15 tasks**  
**fast model assignments: 29 tasks**

---

*— End of 12_ENGINEERING_EXECUTION_PLAN.md —*
