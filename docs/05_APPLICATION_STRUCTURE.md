# 05_APPLICATION_STRUCTURE.md

# SentinelAI Guardrail — Application Structure

---

## 1. Repository Layout

```
sentinelai-guardrail/
├── backend/
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/
│   │       └── 0001_initial_schema.py
│   ├── scripts/
│   │   ├── export_sqlite.py
│   │   ├── import_postgres.py
│   │   └── seed_kb_demo.py
│   └── src/
│       └── sentinel/
│           ├── __init__.py
│           ├── main.py                    # FastAPI app factory + lifespan
│           ├── container.py               # ApplicationContainer (DI root)
│           ├── config.py                  # AppConfig (Pydantic Settings)
│           │
│           ├── api/                       # Presentation layer
│           │   ├── __init__.py
│           │   ├── dependencies.py        # FastAPI Depends() providers
│           │   ├── middleware.py           # Request ID, session ID, logging, CORS
│           │   ├── error_handlers.py      # Global exception → HTTP response mapping
│           │   └── routers/
│           │       ├── guardrail.py       # POST /v1/guardrail/submit
│           │       ├── analytics.py       # GET  /v1/analytics
│           │       ├── requests.py        # GET  /v1/requests (explorer)
│           │       ├── kb.py              # POST/GET/DELETE /v1/kb/documents
│           │       ├── policy.py          # GET/PUT /v1/policy
│           │       └── health.py          # GET /health, /health/ready, /health/live
│           │
│           ├── websocket/
│           │   ├── __init__.py
│           │   ├── handler.py             # WS /ws/{request_id} endpoint
│           │   └── event_bus.py           # Per-request asyncio.Queue + broadcast
│           │
│           ├── application/               # Application layer (use cases)
│           │   ├── __init__.py
│           │   ├── use_cases/
│           │   │   ├── submit_prompt.py
│           │   │   ├── index_document.py
│           │   │   ├── get_request_detail.py
│           │   │   ├── get_analytics.py
│           │   │   ├── replay_request.py
│           │   │   └── update_policy.py
│           │   └── services/
│           │       ├── audit_service.py   # Constructs + persists AuditRecord
│           │       └── session_service.py # Session creation + lookup
│           │
│           ├── domain/                    # Domain layer (pure logic, no I/O)
│           │   ├── __init__.py
│           │   ├── models/
│           │   │   ├── claim.py
│           │   │   ├── evidence.py
│           │   │   ├── confidence.py
│           │   │   ├── decision.py
│           │   │   ├── policy.py
│           │   │   └── pipeline_context.py
│           │   ├── engines/
│           │   │   ├── orchestrator.py
│           │   │   ├── prompt_validation/
│           │   │   │   ├── __init__.py
│           │   │   │   ├── injection_detector.py
│           │   │   │   ├── pii_detector.py
│           │   │   │   ├── policy_filter.py
│           │   │   │   └── risk_scorer.py
│           │   │   ├── llm_execution.py
│           │   │   ├── hallucination/
│           │   │   │   ├── __init__.py
│           │   │   │   ├── claim_extractor.py
│           │   │   │   └── claim_verifier.py
│           │   │   ├── safety_filter.py
│           │   │   ├── confidence_scoring.py
│           │   │   ├── decision_engine.py
│           │   │   └── fallback_strategy.py
│           │   └── exceptions.py          # Domain-specific exception hierarchy
│           │
│           └── infrastructure/            # Infrastructure layer (I/O adapters)
│               ├── __init__.py
│               ├── db/
│               │   ├── __init__.py
│               │   ├── engine.py          # SQLAlchemy async engine + session factory
│               │   ├── models.py          # SQLAlchemy ORM models (all tables)
│               │   └── repositories/
│               │       ├── request_repo.py
│               │       ├── session_repo.py
│               │       ├── kb_repo.py
│               │       ├── analytics_repo.py
│               │       └── policy_repo.py
│               ├── vector_store/
│               │   ├── __init__.py
│               │   ├── base.py            # VectorStore protocol
│               │   ├── faiss_store.py
│               │   └── chroma_store.py
│               ├── embeddings/
│               │   ├── __init__.py
│               │   ├── base.py            # EmbeddingAdapter protocol
│               │   └── sentence_transformer.py
│               ├── llm/
│               │   ├── __init__.py
│               │   ├── base.py            # LLMAdapter protocol
│               │   ├── ollama_adapter.py
│               │   └── openai_adapter.py
│               ├── safety/
│               │   ├── __init__.py
│               │   └── detoxify_classifier.py
│               ├── chunking/
│               │   ├── __init__.py
│               │   └── text_chunker.py
│               ├── storage/
│               │   ├── __init__.py
│               │   └── local_file_storage.py
│               └── background/
│                   ├── __init__.py
│                   └── indexing_worker.py
│
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── router.tsx                     # React Router v6 route definitions
│       │
│       ├── api/                           # API client layer
│       │   ├── client.ts                  # Axios instance + interceptors
│       │   ├── websocket.ts               # WebSocket client + reconnection
│       │   └── endpoints/
│       │       ├── guardrail.ts
│       │       ├── analytics.ts
│       │       ├── requests.ts
│       │       ├── kb.ts
│       │       └── policy.ts
│       │
│       ├── store/                         # Zustand state slices
│       │   ├── index.ts
│       │   ├── playgroundSlice.ts
│       │   ├── policySlice.ts
│       │   ├── kbSlice.ts
│       │   ├── analyticsSlice.ts
│       │   └── sessionSlice.ts
│       │
│       ├── hooks/                         # Custom React hooks
│       │   ├── usePipelineSubmit.ts
│       │   ├── usePipelineProgress.ts     # WebSocket consumer
│       │   ├── useAnalytics.ts
│       │   ├── useKnowledgeBase.ts
│       │   ├── usePolicy.ts
│       │   └── useRequestExplorer.ts
│       │
│       ├── pages/                         # Route-level page components
│       │   ├── PlaygroundPage.tsx
│       │   ├── AnalyticsDashboardPage.tsx
│       │   ├── RequestExplorerPage.tsx
│       │   ├── KnowledgeBasePage.tsx
│       │   ├── PolicyConfigPage.tsx
│       │   └── ApiDocsPage.tsx
│       │
│       ├── components/                    # Reusable UI components
│       │   ├── layout/
│       │   │   ├── AppShell.tsx           # Top nav + content area wrapper
│       │   │   ├── NavBar.tsx
│       │   │   └── PageContainer.tsx
│       │   ├── playground/
│       │   │   ├── PromptInput.tsx
│       │   │   ├── ModelSelector.tsx
│       │   │   ├── ApiKeyField.tsx
│       │   │   ├── KbSelector.tsx
│       │   │   ├── GuardrailToggles.tsx
│       │   │   ├── ResponsePanel.tsx
│       │   │   ├── ConfidenceBadge.tsx
│       │   │   ├── DecisionLabel.tsx
│       │   │   └── PipelineProgressIndicator.tsx
│       │   ├── analysis/
│       │   │   ├── GuardrailAnalysisPanel.tsx
│       │   │   ├── ClaimsList.tsx
│       │   │   ├── EvidenceList.tsx
│       │   │   ├── VerificationResults.tsx
│       │   │   └── SignalBreakdownChart.tsx
│       │   ├── trace/
│       │   │   ├── ExecutionTraceViewer.tsx
│       │   │   ├── TraceStageRow.tsx
│       │   │   └── TraceStageDetail.tsx
│       │   ├── analytics/
│       │   │   ├── SummaryMetricsRow.tsx
│       │   │   ├── HallucinationRateChart.tsx
│       │   │   ├── DecisionDistributionChart.tsx
│       │   │   ├── ConfidenceHistogram.tsx
│       │   │   ├── LatencyLineChart.tsx
│       │   │   └── TokenUsageChart.tsx
│       │   ├── explorer/
│       │   │   ├── RequestList.tsx
│       │   │   ├── RequestListItem.tsx
│       │   │   ├── RequestDetailPanel.tsx
│       │   │   └── ReplayButton.tsx
│       │   ├── kb/
│       │   │   ├── DocumentUploader.tsx
│       │   │   ├── DocumentList.tsx
│       │   │   ├── DocumentStatusBadge.tsx
│       │   │   ├── ChunkingPreview.tsx
│       │   │   └── VectorSearchPreview.tsx
│       │   ├── policy/
│       │   │   ├── ThresholdSliders.tsx
│       │   │   ├── CategoryToggles.tsx
│       │   │   ├── FallbackPriorityList.tsx  # drag-and-drop
│       │   │   └── ModuleToggles.tsx
│       │   └── shared/
│       │       ├── Tooltip.tsx
│       │       ├── StatusBadge.tsx
│       │       ├── EmptyState.tsx
│       │       ├── ErrorBoundary.tsx
│       │       ├── LoadingSpinner.tsx
│       │       ├── ConfirmDialog.tsx
│       │       └── PrivacyNotice.tsx
│       │
│       ├── types/                         # Shared TypeScript types
│       │   ├── api.ts                     # API request/response types (mirrors Pydantic schemas)
│       │   ├── domain.ts                  # Frontend domain types
│       │   └── store.ts                   # Zustand store shape types
│       │
│       └── utils/
│           ├── formatters.ts              # Score labels, latency formatting
│           ├── validators.ts              # API key format check, prompt length
│           ├── constants.ts              # Threshold defaults, max prompt length
│           └── sessionId.ts              # Browser sessionStorage UUID management
│
├── sdk/
│   ├── python/
│   │   ├── pyproject.toml
│   │   └── sentinel_sdk/
│   │       ├── __init__.py
│   │       ├── client.py
│   │       ├── models.py
│   │       ├── exceptions.py
│   │       └── async_client.py
│   └── javascript/
│       ├── package.json
│       └── src/
│           ├── client.ts
│           ├── types.ts
│           └── errors.ts
│
├── docker/
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   └── Caddyfile
│
├── docker-compose.yml
├── docker-compose.dev.yml
├── .env.example
└── .github/
    └── workflows/
        ├── ci.yml
        └── deploy.yml
```

---

## 2. Backend Module Structure Detail

### 2.1 `main.py` — Application Factory

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sentinel.container import ApplicationContainer
from sentinel.config import AppConfig
from sentinel.api import middleware, error_handlers, routers

def create_app() -> FastAPI:
    config = AppConfig()  # reads from env vars via Pydantic Settings

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        container = ApplicationContainer(config)
        await container.initialize()          # load embedding model, init DB, start bg worker
        app.state.container = container
        yield
        # Shutdown
        await container.shutdown()            # flush pending audit writes, stop bg worker

    app = FastAPI(
        title="SentinelAI Guardrail API",
        version="1.0.0",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url="/api/redoc",
    )

    middleware.register(app, config)
    error_handlers.register(app)
    routers.register(app)

    return app

app = create_app()
```

### 2.2 `config.py` — Typed Configuration

```python
from pydantic_settings import BaseSettings, SettingsConfigDict

class AppConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Database
    database_url: str = "sqlite+aiosqlite:///./sentinel.db"

    # Vector store
    faiss_index_dir: str = "./data/faiss_indexes"
    vector_store_backend: str = "faiss"        # "faiss" | "chroma"
    chroma_host: str = "localhost"
    chroma_port: int = 8000

    # Embedding
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_cache_size: int = 512

    # LLM
    ollama_base_url: str = "http://localhost:11434"
    ollama_default_model: str = "mistral"
    llm_timeout_seconds: float = 25.0
    llm_max_tokens: int = 1024
    llm_default_temperature: float = 0.7

    # Safety
    detoxify_model: str = "original"           # "original" | "unbiased" | "multilingual"
    safety_block_threshold: float = 0.7

    # Pipeline
    max_claims_per_response: int = 20
    evidence_top_k: int = 5
    claim_model_name: str = "mistral"          # model used for claim extraction/verification

    # Storage
    upload_dir: str = "./data/uploads"
    max_upload_size_bytes: int = 10 * 1024 * 1024  # 10 MB

    # Session
    session_header_name: str = "X-Session-ID"

    # Server
    log_level: str = "INFO"
    cors_origins: list[str] = ["http://localhost:5173"]
    rate_limit_requests_per_minute: int = 30
```

### 2.3 `api/middleware.py` — Middleware Stack

Registered in order (outermost first):

1. **CORS Middleware** — allow configured origins; expose `X-Request-ID` header.
2. **Request ID Middleware** — reads `X-Request-ID` from inbound header or generates a UUID. Binds to structlog context vars.
3. **Session ID Middleware** — reads `X-Session-ID` header. Validates UUID format. Returns HTTP 400 if malformed. Creates session record on first use (via `SessionService`).
4. **Logging Middleware** — logs every request start and completion with method, path, status code, latency. Redacts `Authorization` and `X-Api-Key` headers.
5. **API Key Stripping Middleware** — removes `X-Openai-Api-Key` from the request after extracting it into `request.state.openai_api_key`. Ensures the key never appears in downstream logs.

### 2.4 `api/error_handlers.py` — Error Response Mapping

```python
# All error responses follow this shape:
{
    "error_code": "PROMPT_TOO_LONG",
    "message": "Prompt exceeds the maximum allowed length of 4000 characters.",
    "request_id": "req_abc123",
    "field": "prompt"           # optional: identifies the offending field
}

# Mapping table:
PromptTooLongError           → HTTP 400, PROMPT_TOO_LONG
PromptEmptyError             → HTTP 400, PROMPT_EMPTY
InjectionBlockedError        → HTTP 200, decision=block  (not an HTTP error; pipeline result)
LLMUnavailableError          → HTTP 503, LLM_UNAVAILABLE
LLMAuthenticationError       → HTTP 400, LLM_AUTH_FAILED
LLMTimeoutError              → HTTP 504, LLM_TIMEOUT
KBDocumentNotFoundError      → HTTP 404, KB_DOCUMENT_NOT_FOUND
KBIndexingError              → HTTP 500, KB_INDEXING_FAILED
RequestNotFoundError         → HTTP 404, REQUEST_NOT_FOUND
PolicyValidationError        → HTTP 422, POLICY_INVALID
ReplayNotAllowedError        → HTTP 403, REPLAY_BLOCKED_PII
ValidationError (Pydantic)   → HTTP 422, VALIDATION_ERROR
Unhandled Exception          → HTTP 500, INTERNAL_ERROR (stack trace in logs only)
```

### 2.5 API Router Definitions

#### `routers/guardrail.py`

```
POST /v1/guardrail/submit
    Body: GuardrailSubmitRequest
        - prompt: str (1–4000 chars)
        - model_provider: "ollama" | "openai"
        - model_name: str | None
        - kb_id: str | None
        - policy_overrides: PolicyOverrides | None

    Headers:
        - X-Session-ID: UUID (required)
        - X-Openai-Api-Key: str (required if model_provider == "openai")

    Response: GuardrailResponse
        - request_id: str
        - guardrail_decision: str
        - decision_reason: str
        - confidence_score: int
        - confidence_label: str
        - confidence_signal_breakdown: dict
        - final_response_text: str | None
        - block_reason: str | None
        - claims: ClaimResult[]
        - safety_filter_results: SafetyResult[]
        - execution_trace: TraceStage[]
        - token_usage: TokenUsage
        - pipeline_latency_ms: int
        - request_id: str
```

#### `routers/analytics.py`

```
GET /v1/analytics
    Query: session_id (from header), date_from, date_to, model_provider
    Response: AnalyticsSummary
        - summary: { total_requests, avg_confidence, hallucination_rate, avg_latency_ms }
        - by_model: ModelMetrics[]
        - by_decision: { accept: int, warn: int, retry: int, block: int }
        - confidence_distribution: { buckets: int[], counts: int[] }
        - latency_over_time: { timestamps: str[], values: int[] }
```

#### `routers/requests.py`

```
GET /v1/requests
    Query: decision, model, min_confidence, max_confidence, page, page_size
    Response: { items: RequestListItem[], total: int, page: int, page_size: int }

GET /v1/requests/{request_id}
    Response: RequestDetailResponse (full audit record)

POST /v1/requests/{request_id}/replay
    Response: GuardrailResponse (new request, references original via replayed_from_request_id)
```

#### `routers/kb.py`

```
POST   /v1/kb/documents          — upload document (multipart/form-data)
GET    /v1/kb/documents          — list documents for session
GET    /v1/kb/documents/{doc_id} — get document detail + chunking preview
DELETE /v1/kb/documents/{doc_id} — delete document + remove from FAISS index
POST   /v1/kb/search             — vector search preview (query: str, top_k: int)
```

#### `routers/policy.py`

```
GET  /v1/policy          — get current session policy (or defaults)
PUT  /v1/policy          — save policy snapshot for session
```

---

## 3. Frontend Module Structure Detail

### 3.1 Navigation Architecture (React Router v6)

```typescript
// router.tsx
const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,          // persistent nav + outlet
    children: [
      { index: true,                  element: <Navigate to="/playground" replace /> },
      { path: "playground",           element: <PlaygroundPage /> },
      { path: "analytics",            element: <AnalyticsDashboardPage /> },
      { path: "requests",             element: <RequestExplorerPage /> },
      { path: "requests/:requestId",  element: <RequestExplorerPage /> },
      { path: "knowledge-base",       element: <KnowledgeBasePage /> },
      { path: "policy",               element: <PolicyConfigPage /> },
      { path: "api-docs",             element: <ApiDocsPage /> },
    ],
  },
]);
```

**Navigation behavior:**

- `AppShell` renders a persistent `NavBar` and a `<Outlet />` for page content.
- The NavBar highlights the active route using React Router's `NavLink` with `isActive`.
- Deep-linking to `/requests/:requestId` pre-selects that request in the Request Explorer.
- No authentication gate on any route (MVP).

### 3.2 State Management (Zustand)

Each slice is defined in its own file and combined in `store/index.ts`.

```typescript
// store/playgroundSlice.ts
interface PlaygroundState {
  // Input state
  prompt: string;
  modelProvider: 'ollama' | 'openai';
  modelName: string;
  openaiApiKey: string;
  selectedKbId: string | null;
  moduleFlags: ModuleFlags;

  // Pipeline state
  pipelineStatus: 'idle' | 'running' | 'complete' | 'error';
  currentStage: string | null;       // stage name during execution
  stageStatuses: Record<string, StageStatus>;  // live stage progress

  // Results
  result: GuardrailResponse | null;
  error: ApiError | null;

  // UI state
  isTraceExpanded: boolean;
  selectedClaimIndex: number | null;   // for claim→evidence linking

  // Actions
  setPrompt: (p: string) => void;
  setModel: (provider: string, name: string) => void;
  setApiKey: (key: string) => void;
  submitPrompt: () => Promise<void>;
  resetResult: () => void;
  setTraceExpanded: (v: boolean) => void;
  setSelectedClaim: (i: number | null) => void;
}
```

```typescript
// store/policySlice.ts
interface PolicyState {
  savedPolicy: PolicySnapshot;
  draftPolicy: PolicySnapshot;
  hasUnsavedChanges: boolean;
  isSaving: boolean;
  saveError: string | null;

  updateDraft: (updates: Partial<PolicySnapshot>) => void;
  savePolicy: () => Promise<void>;
  discardChanges: () => void;
  reorderFallbackPriority: (from: number, to: number) => void;
}
```

```typescript
// store/sessionSlice.ts
interface SessionState {
  sessionId: string;                  // UUID, persisted in sessionStorage
  wsStatus: 'disconnected' | 'connecting' | 'connected' | 'error';
  activeRequestId: string | null;     // request currently streaming progress

  initializeSession: () => void;
  setWsStatus: (s: WsStatus) => void;
}
```

### 3.3 Custom Hooks

#### `usePipelineSubmit`

Orchestrates the full submit flow:

1. Validates prompt client-side (non-empty, length ≤ 4000).
2. Validates API key format if OpenAI is selected.
3. Dispatches `pipelineStatus = 'running'` to store.
4. Opens WebSocket connection for the upcoming `request_id`.
5. Calls `POST /v1/guardrail/submit`.
6. On response: updates store with full result, dispatches `pipelineStatus = 'complete'`.
7. On error: dispatches `pipelineStatus = 'error'`, sets `error` in store.
8. Clears API key from store after request completes (regardless of outcome).

```typescript
// hooks/usePipelineSubmit.ts
export function usePipelineSubmit() {
  const store = usePlaygroundStore();
  const { connectForRequest } = usePipelineProgress();

  const submit = async () => {
    // Client-side validation
    if (!store.prompt.trim()) return;
    if (store.prompt.length > MAX_PROMPT_LENGTH) return;
    if (store.modelProvider === 'openai' && !isValidApiKeyFormat(store.openaiApiKey)) return;

    store.setPipelineStatus('running');
    store.setCurrentStage('prompt_validation');

    try {
      // Pre-register WS listener before HTTP call to avoid race
      const wsQueue = connectForRequest(/* request_id known after response */);
      const response = await guardrailApi.submit({
        prompt: store.prompt,
        model_provider: store.modelProvider,
        model_name: store.modelName,
        kb_id: store.selectedKbId,
      }, {
        headers: { 'X-Openai-Api-Key': store.openaiApiKey }
      });

      store.setResult(response.data);
      store.setPipelineStatus('complete');
    } catch (err) {
      store.setError(parseApiError(err));
      store.setPipelineStatus('error');
    } finally {
      store.clearApiKey();  // key never lingers in state after request
    }
  };

  return { submit, isRunning: store.pipelineStatus === 'running' };
}
```

#### `usePipelineProgress`

Manages the WebSocket connection for real-time stage progress updates.

```typescript
export function usePipelineProgress() {
  const store = usePlaygroundStore();
  const wsRef = useRef<WebSocket | null>(null);

  const connectForRequest = (requestId: string) => {
    if (wsRef.current) wsRef.current.close();

    const ws = new WebSocket(`${WS_BASE_URL}/ws/${requestId}`);
    wsRef.current = ws;

    ws.onmessage = (event) => {
      const msg: PipelineEvent = JSON.parse(event.data);
      store.setCurrentStage(msg.stage);
      store.setStageStatus(msg.stage, msg.status);
    };

    ws.onerror = () => store.setWsStatus('error');
    ws.onclose = () => store.setWsStatus('disconnected');

    return ws;
  };

  // Reconnect logic with exponential backoff (max 3 attempts)
  const reconnect = useCallback((requestId: string, attempt = 0) => {
    if (attempt >= 3) return;
    setTimeout(() => connectForRequest(requestId), 2 ** attempt * 500);
  }, []);

  return { connectForRequest, reconnect };
}
```

---

## 4. Reusable Component Strategy

### 4.1 Component Taxonomy

| Category | Components | Rules |
|---|---|---|
| **Shared primitives** | `Tooltip`, `StatusBadge`, `EmptyState`, `LoadingSpinner`, `ConfirmDialog` | No business logic; fully controlled via props; no store access |
| **Feature components** | `ClaimsList`, `TraceStageRow`, `HallucinationRateChart` | May read from store via hooks; no direct store writes; dispatches via callback props |
| **Page sections** | `GuardrailAnalysisPanel`, `ExecutionTraceViewer`, `SummaryMetricsRow` | Compose feature components; access store directly |
| **Page containers** | `PlaygroundPage`, `AnalyticsDashboardPage` | Own top-level data fetching; pass data down; render page sections |

### 4.2 Prop Interface Conventions

- All components declare explicit TypeScript prop interfaces (no `any`).
- Optional props have explicit defaults using destructuring defaults, not `defaultProps`.
- Event handler props are named `on{Action}` (e.g., `onClaimSelect`, `onDocumentDelete`).
- Loading, error, and empty states are handled via explicit boolean/value props, not inferred from null data.

```typescript
// Example: ClaimsList component interface
interface ClaimsListProps {
  claims: ClaimResult[];
  selectedClaimIndex: number | null;
  onClaimSelect: (index: number | null) => void;
  isLoading?: boolean;
  emptyMessage?: string;
}
```

### 4.3 `Tooltip` Component

All technical terms in the UI (confidence score, RAG augmentation, hallucination detection, claim verification) must have inline tooltips. A central `TERM_DEFINITIONS` constant maps term keys to explanation strings. The `Tooltip` component wraps any child element and renders the definition on hover/focus.

```typescript
// utils/constants.ts
export const TERM_DEFINITIONS: Record<string, string> = {
  confidence_score: "A 0–100 score indicating how reliable this response is, based on evidence support, safety checks, and claim verification.",
  rag_augmentation: "Retrieval-Augmented Generation: the system retrieves relevant documents and injects them into the prompt to improve factual accuracy.",
  claim_verification: "Each factual statement in the response is checked against the knowledge base. Claims are labeled Supported, Unsupported, or Contradicted.",
  hallucination_detection: "The process of identifying claims in the AI response that are not supported by the available evidence.",
  // ...
};
```

---

## 5. Design System Architecture

### 5.1 Technology

- **Tailwind CSS** (utility-first) for all layout and spacing.
- **Radix UI** (headless primitives) for accessible interactive components: Dialog, Select, Tooltip, Switch, Slider, ScrollArea.
- **Recharts** for all data visualizations.
- **@dnd-kit/core** for drag-and-drop in the fallback strategy priority list.
- **lucide-react** for all icons.

### 5.2 Color System (Tailwind Custom Tokens)

Defined in `tailwind.config.ts` under `theme.extend.colors`:

```
sentinel-bg:         #0f1117   (page background)
sentinel-surface:    #1a1d27   (card/panel background)
sentinel-border:     #2d3146   (borders)
sentinel-text:       #e2e8f0   (primary text)
sentinel-muted:      #94a3b8   (secondary text)

decision-accept:     #22c55e   (green)
decision-warn:       #f59e0b   (amber)
decision-block:      #ef4444   (red)
decision-retry:      #3b82f6   (blue)

confidence-high:     #22c55e   (≥70)
confidence-medium:   #f59e0b   (40–69)
confidence-low:      #ef4444   (<40)

stage-passed:        #22c55e
stage-flagged:       #f59e0b
stage-failed:        #ef4444
stage-skipped:       #64748b
stage-not-reached:   #334155
```

### 5.3 Typography Scale

All text uses `font-sans` (Inter via Google Fonts). Scale:

- `text-xs` (12px): metadata labels, timestamps
- `text-sm` (14px): body text, list items
- `text-base` (16px): primary text
- `text-lg` (18px): section headers
- `text-xl` / `text-2xl`: page headings

### 5.4 Spacing System

All spacing uses Tailwind's default 4px base grid. No custom spacing values. Components use `gap-*`, `p-*`, `m-*` from the standard scale only.

---

## 6. Accessibility Strategy

### 6.1 Keyboard Navigation

- All interactive elements (buttons, dropdowns, toggles, sliders, list items) are reachable via Tab.
- Modal dialogs trap focus until dismissed. Implemented via Radix UI Dialog.
- The Execution Trace Viewer stages are keyboard-navigable: Enter/Space expands/collapses a stage row.
- Claim selection in the Guardrail Analysis Panel is keyboard-navigable (arrow keys, Enter to select).

### 6.2 Screen Reader Support

- All icon-only buttons include `aria-label`.
- Status badges include both color and text (never color-only).
- Charts (Recharts) include `aria-label` on the container and a visually-hidden data table alternative for screen readers.
- Dynamic content updates (pipeline stage completion) use `aria-live="polite"` regions to announce changes without disrupting the reading flow.
- Error messages use `role="alert"` for immediate announcement.

### 6.3 Color Independence

Every color-coded signal includes a text label:

- Confidence badge: "High" / "Medium" / "Low" (not just green/yellow/red).
- Stage status: "Passed" / "Flagged" / "Failed" / "Skipped" (not just color dot).
- Decision label: "Accepted" / "Warning" / "Blocked" / "Retried" (not just color pill).

### 6.4 WCAG 2.1 AA Compliance

- All text/background color pairs meet a 4.5:1 contrast ratio minimum.
- Interactive element focus rings are visible (2px solid `sentinel-text` outline, `outline-offset-2`).
- Slider components (policy thresholds) expose `aria-valuenow`, `aria-valuemin`, `aria-valuemax`, `aria-label`.
- Form validation errors are associated with their inputs via `aria-describedby`.

---

## 7. Localization Readiness

The MVP ships in English only. The following conventions ensure future localization is non-breaking:

- All user-facing strings are defined in a central `src/utils/strings.ts` file (key-value map), not inline in JSX.
- No string concatenation for translated phrases (no `"Found " + count + " results"`). Use template functions: `strings.resultsFound(count)`.
- Dates and times are formatted using `Intl.DateTimeFormat` with explicit `locale` and `timeZone` options (defaults to `en-US` and `UTC`).
- Number formatting uses `Intl.NumberFormat`.
- RTL layout is not handled in MVP but Tailwind's logical properties (`ps-`, `pe-` instead of `pl-`, `pr-`) are used where practical to reduce future RTL migration cost.

---

## 8. Error State UX Patterns

### 8.1 Error Hierarchy

| Error Tier | Scope | UI Treatment |
|---|---|---|
| **Field error** | Single input | Inline red text below field; field border turns red; `aria-describedby` links error to input |
| **Panel error** | A section/panel failed to load | Inline error card within the panel with retry button; rest of page remains functional |
| **Page error** | Full page data fetch failed | Full-panel error state with heading, message, and retry/navigate-home action |
| **Critical error** | Unhandled JS exception | `ErrorBoundary` catches; renders a fallback UI with error message and "Reload" button; error details logged to console |
| **Pipeline error** | Guardrail pipeline failure | Displayed in the Response Panel as a structured error (not a toast); includes request_id |

### 8.2 Toast Notifications

Used only for transient feedback (not errors that require user action):

- KB document deleted successfully.
- Policy saved successfully.
- Policy save failed (with retry action in toast).

Toasts auto-dismiss after 4 seconds. Maximum 3 concurrent toasts. Implemented via Radix UI Toast.

### 8.3 `ErrorBoundary` Component

Wraps each page and major panel independently. A crash in `GuardrailAnalysisPanel` does not crash `ExecutionTraceViewer`. Each boundary renders a localized fallback with a "Try again" button that calls `ErrorBoundary.reset()`.

---

## 9. Empty State UX Patterns

All empty states follow a three-element structure:

1. **Icon** — relevant to the content type (magnifying glass for search, inbox for requests, file for KB).
2. **Heading** — short, clear statement of what's empty ("No requests yet").
3. **Body + CTA** — explanation and a direct action link/button.

| Screen | Empty State Heading | CTA |
|---|---|---|
| Playground (pre-submit) | (no empty state; instructional copy in output panel) | — |
| Analytics Dashboard | "No data yet" | "Go to Playground" link |
| Request Explorer | "No requests recorded" | "Submit a prompt" link |
| KB Management | "No documents indexed" | "Upload a document" button |
| Request detail (not found) | "Request not found" | "Back to Explorer" link |
| Claim list (no claims) | "No factual claims detected" | Tooltip explaining why |
| Evidence list (no KB) | "No knowledge base active" | "Select a knowledge base" link |

---

## 10. SDK Module Structure

### 10.1 Python SDK

```python
# sentinel_sdk/client.py

class SentinelClient:
    def __init__(self, base_url: str, session_id: str | None = None):
        self.base_url = base_url
        self.session_id = session_id or str(uuid4())
        self._http = httpx.Client(base_url=base_url, timeout=60.0)

    def submit(
        self,
        prompt: str,
        model_provider: str = "ollama",
        model_name: str | None = None,
        kb_id: str | None = None,
        openai_api_key: str | None = None,
        policy_overrides: dict | None = None,
    ) -> GuardrailResponse:
        headers = {"X-Session-ID": self.session_id}
        if openai_api_key:
            headers["X-Openai-Api-Key"] = openai_api_key
        response = self._http.post(
            "/v1/guardrail/submit",
            json={
                "prompt": prompt,
                "model_provider": model_provider,
                "model_name": model_name,
                "kb_id": kb_id,
                "policy_overrides": policy_overrides,
            },
            headers=headers,
        )
        response.raise_for_status()
        return GuardrailResponse(**response.json())

# sentinel_sdk/async_client.py
class AsyncSentinelClient:
    # Same interface, uses httpx.AsyncClient
    async def submit(self, ...) -> GuardrailResponse: ...
```

### 10.2 SDK Error Hierarchy

```
SentinelError (base)
├── SentinelAPIError          # HTTP 4xx/5xx from server
│   ├── PromptTooLongError
│   ├── LLMUnavailableError
│   └── AuthenticationError
├── SentinelConnectionError   # Cannot reach server
└── SentinelTimeoutError      # Request exceeded client timeout
```

All SDK errors include `error_code`, `message`, and `request_id` (if available from the response).
