# 10_DEPLOYMENT_WORKFLOW.md

# SentinelAI Guardrail — Deployment Workflow

---

## 1. Development Environment Setup

### 1.1 Prerequisites

| Tool | Version | Purpose |
|---|---|---|
| Python | 3.12.x | Backend runtime |
| Node.js | 20.x LTS | Frontend build toolchain |
| Docker | 24.x+ | Container runtime |
| Docker Compose | 2.x | Local multi-service orchestration |
| Ollama | Latest | Local LLM runtime |
| uv | 0.4.x | Python package manager (fast, lock-file aware) |
| git | 2.x | Version control |

### 1.2 First-Time Setup

```bash
# 1. Clone repository
git clone https://github.com/your-org/sentinelai-guardrail.git
cd sentinelai-guardrail

# 2. Install pre-commit hooks (enforces Ruff, mypy, ESLint before every commit)
pip install pre-commit
pre-commit install

# 3. Backend: create virtual environment and install dependencies
cd backend
uv venv --python 3.12
source .venv/bin/activate          # Linux/macOS
# .venv\Scripts\activate           # Windows
uv sync --all-extras               # installs all deps from uv.lock

# 4. Copy environment file
cp .env.example .env
# Edit .env if needed (defaults work for local development)

# 5. Run database migrations
alembic upgrade head

# 6. Frontend: install dependencies
cd ../frontend
npm install

# 7. Pull Ollama model (one-time, ~4GB download)
ollama pull mistral:7b-instruct-v0.2-q4_K_M

# 8. Start development servers (two terminal windows)
# Terminal 1: Backend
cd backend && uvicorn sentinel.main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend && npm run dev          # starts Vite dev server on :5173

# 9. Verify: open http://localhost:5173
```

### 1.3 Docker-Based Local Development (Alternative)

For developers who prefer to avoid local Python/Node setup:

```bash
# Start all services with hot reload
docker compose -f docker-compose.dev.yml up

# Services started:
#   app      → http://localhost:8000  (FastAPI with volume-mounted source)
#   frontend → http://localhost:5173  (Vite dev server with HMR)
#   ollama   → http://localhost:11434 (local LLM)
```

```yaml
# docker-compose.dev.yml
services:
  app:
    build:
      context: ./backend
      dockerfile: ../docker/Dockerfile.backend
      target: dev
    volumes:
      - ./backend/src:/app/src:ro    # hot reload via watchfiles
    environment:
      - DATABASE_URL=sqlite+aiosqlite:///./data/sentinel.db
      - OLLAMA_BASE_URL=http://ollama:11434
    ports:
      - "8000:8000"
    depends_on:
      - ollama
    command: uvicorn sentinel.main:app --reload --host 0.0.0.0 --port 8000

  frontend:
    build:
      context: ./frontend
      dockerfile: ../docker/Dockerfile.frontend
      target: dev
    volumes:
      - ./frontend/src:/app/src:ro
    ports:
      - "5173:5173"
    command: npm run dev -- --host

  ollama:
    image: ollama/ollama:latest
    volumes:
      - ollama_data:/root/.ollama
    ports:
      - "11434:11434"

volumes:
  ollama_data:
```

### 1.4 Environment Variables Reference

```bash
# .env.example — copy to .env and edit as needed

# Database
DATABASE_URL=sqlite+aiosqlite:///./data/sentinel.db

# Vector store
FAISS_INDEX_DIR=./data/faiss_indexes
VECTOR_STORE_BACKEND=faiss

# Embedding
EMBEDDING_MODEL=all-MiniLM-L6-v2
EMBEDDING_CACHE_SIZE=512

# LLM
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_DEFAULT_MODEL=mistral:7b-instruct-v0.2-q4_K_M
LLM_TIMEOUT_SECONDS=25.0
LLM_MAX_TOKENS=1024
LLM_DEFAULT_TEMPERATURE=0.7

# Safety
DETOXIFY_MODEL=original
SAFETY_BLOCK_THRESHOLD=0.7

# Storage
UPLOAD_DIR=./data/uploads
MAX_UPLOAD_SIZE_BYTES=10485760

# Server
LOG_LEVEL=INFO
CORS_ORIGINS=["http://localhost:5173"]
RATE_LIMIT_REQUESTS_PER_MINUTE=30

# Production only (leave blank in development)
# DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/sentinel
```

---

## 2. Build Pipeline

### 2.1 Backend Build (Docker Multi-Stage)

```dockerfile
# docker/Dockerfile.backend

# ── Stage 1: base ────────────────────────────────────────────────
FROM python:3.12-slim AS base
RUN apt-get update && apt-get install -y \
    libmagic1 \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

# ── Stage 2: builder ─────────────────────────────────────────────
FROM base AS builder
RUN pip install uv
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# ── Stage 3: model-preloader ──────────────────────────────────────
# Pre-download AI model weights into the image to eliminate cold-start downloads
FROM builder AS model-preloader
RUN python -c "from sentence_transformers import SentenceTransformer; \
               SentenceTransformer('all-MiniLM-L6-v2')"
RUN python -c "from detoxify import Detoxify; Detoxify('original')"

# ── Stage 4: dev (for docker-compose.dev.yml) ────────────────────
FROM model-preloader AS dev
RUN uv sync --frozen --no-install-project  # includes dev deps
COPY backend/src /app/src
COPY backend/alembic /app/alembic
COPY backend/alembic.ini /app/
EXPOSE 8000
CMD ["uvicorn", "sentinel.main:app", "--reload", "--host", "0.0.0.0", "--port", "8000"]

# ── Stage 5: runtime (production image) ──────────────────────────
FROM model-preloader AS runtime
COPY backend/src /app/src
COPY backend/alembic /app/alembic
COPY backend/alembic.ini /app/
COPY backend/scripts /app/scripts

# Create data directories
RUN mkdir -p /app/data/faiss_indexes /app/data/uploads /app/backups

# Create non-root user
RUN addgroup --system sentinel && adduser --system --group sentinel
RUN chown -R sentinel:sentinel /app
USER sentinel

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health/live || exit 1

CMD ["gunicorn", "sentinel.main:app", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--workers", "2", \
     "--bind", "0.0.0.0:8000", \
     "--timeout", "60", \
     "--graceful-timeout", "30", \
     "--keep-alive", "5", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
```

### 2.2 Frontend Build

```dockerfile
# docker/Dockerfile.frontend

# ── Stage 1: builder ─────────────────────────────────────────────
FROM node:20-slim AS builder
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --prefer-offline
COPY frontend/ ./
RUN npm run build           # outputs to /app/dist

# ── Stage 2: dev ─────────────────────────────────────────────────
FROM node:20-slim AS dev
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
EXPOSE 5173
CMD ["npm", "run", "dev", "--", "--host"]

# The runtime stage for frontend is just the /dist directory.
# It is served by Caddy directly (not a separate container).
# The CI pipeline copies dist/ into the Caddy static serving directory.
```

### 2.3 Image Size Targets

| Image | Target Size | Key Contents |
|---|---|---|
| `sentinel-backend:runtime` | ≤ 2.5 GB | Python 3.12 + deps + MiniLM model (~500MB) + detoxify (~250MB) |
| `sentinel-backend:dev` | ≤ 2.8 GB | + dev deps (pytest, mypy, etc.) |
| Frontend (static assets) | ≤ 5 MB | Vite-bundled JS/CSS, gzip compressed |

The backend image is large due to AI model weights. The model-preloader stage caches the weights so that production restarts do not re-download models.

---

## 3. CI/CD Architecture

### 3.1 Pipeline Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     GitHub Actions CI/CD                        │
│                                                                 │
│  Pull Request:                                                  │
│  ┌──────────┐  ┌──────────────┐  ┌────────────────────────┐   │
│  │  lint    │→ │  test-unit   │→ │  test-integration      │   │
│  │ (2 min)  │  │  (3 min)     │  │  (5 min)               │   │
│  └──────────┘  └──────────────┘  └────────────────────────┘   │
│       │                                    │                    │
│  ┌──────────┐                    ┌─────────────────────┐       │
│  │  lint-fe │                    │  test-frontend      │       │
│  │ (1 min)  │                    │  (2 min)            │       │
│  └──────────┘                    └─────────────────────┘       │
│                                                                 │
│  Merge to main:                                                 │
│  ┌────────────────────────────────────────────────────────┐    │
│  │  All PR checks + performance tests + E2E tests         │    │
│  │  (15–20 min total)                                     │    │
│  └─────────────────────────┬──────────────────────────────┘    │
│                            │                                    │
│  ┌─────────────────────────▼──────────────────────────────┐    │
│  │  build                                                  │    │
│  │  - docker build --target runtime → push to GHCR        │    │
│  │  - npm run build → upload dist/ to artifact store      │    │
│  │  - trivy scan image for CVEs                           │    │
│  └─────────────────────────┬──────────────────────────────┘    │
│                            │                                    │
│  ┌─────────────────────────▼──────────────────────────────┐    │
│  │  deploy (staging)                                       │    │
│  │  - SSH deploy or platform API trigger                   │    │
│  │  - Run alembic upgrade head                            │    │
│  │  - Smoke test: GET /health/ready                       │    │
│  └─────────────────────────┬──────────────────────────────┘    │
│                            │ (manual approval gate)             │
│  ┌─────────────────────────▼──────────────────────────────┐    │
│  │  deploy (production)                                    │    │
│  │  - Same steps as staging                               │    │
│  └────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 GitHub Actions Workflow Files

#### `.github/workflows/ci.yml`

```yaml
name: CI

on:
  pull_request:
    branches: [main, develop]
  push:
    branches: [main]

env:
  PYTHON_VERSION: "3.12"
  NODE_VERSION: "20"
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}/sentinel-backend

jobs:
  lint-backend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "${{ env.PYTHON_VERSION }}" }
      - name: Install uv
        run: pip install uv
      - name: Install dev deps
        run: cd backend && uv sync --frozen
      - name: Ruff lint
        run: cd backend && uv run ruff check src/ tests/
      - name: Ruff format check
        run: cd backend && uv run ruff format --check src/ tests/
      - name: mypy
        run: cd backend && uv run mypy src/sentinel/

  lint-frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "${{ env.NODE_VERSION }}" }
      - run: cd frontend && npm ci
      - run: cd frontend && npm run lint
      - run: cd frontend && npm run type-check

  test-unit:
    needs: lint-backend
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "${{ env.PYTHON_VERSION }}" }
      - name: Install uv
        run: pip install uv
      - name: Install deps
        run: cd backend && uv sync --frozen
      - name: Run unit tests with coverage
        run: |
          cd backend
          uv run pytest tests/unit/ \
            --cov=src/sentinel \
            --cov-report=xml:coverage.xml \
            --cov-fail-under=85 \
            -v --tb=short
      - uses: actions/upload-artifact@v4
        with:
          name: coverage-unit
          path: backend/coverage.xml

  test-integration:
    needs: test-unit
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "${{ env.PYTHON_VERSION }}" }
      - name: Install system deps (libmagic for file validation)
        run: sudo apt-get install -y libmagic1
      - name: Install uv
        run: pip install uv
      - name: Install deps
        run: cd backend && uv sync --frozen
      - name: Run integration + consistency + migration tests
        run: |
          cd backend
          uv run pytest tests/integration/ tests/consistency/ tests/migration/ \
            -v --tb=short --timeout=60
      - name: pip-audit (dependency CVE scan)
        run: cd backend && uv run pip-audit

  test-frontend:
    needs: lint-frontend
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "${{ env.NODE_VERSION }}" }
      - run: cd frontend && npm ci
      - run: cd frontend && npm run test:coverage
      - uses: actions/upload-artifact@v4
        with:
          name: coverage-frontend
          path: frontend/coverage/

  test-performance:
    needs: test-integration
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "${{ env.PYTHON_VERSION }}" }
      - name: Install deps
        run: cd backend && pip install uv && uv sync --frozen
      - name: Run performance benchmarks
        run: |
          cd backend
          uv run pytest tests/performance/ -m performance -v \
            --benchmark-json=benchmark.json
      - uses: actions/upload-artifact@v4
        with:
          name: benchmark-results
          path: backend/benchmark.json

  test-e2e:
    needs: [test-integration, test-frontend]
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Start full stack
        run: docker compose up -d --wait
      - name: Wait for Ollama model pull
        run: |
          docker compose exec ollama ollama pull mistral:7b-instruct-v0.2-q4_K_M
          sleep 10
      - name: Install Playwright
        run: |
          cd backend && pip install uv && uv sync --frozen
          uv run playwright install chromium
      - name: Run E2E tests
        run: cd backend && uv run pytest tests/e2e/ -v --timeout=120
      - name: Stop stack
        if: always()
        run: docker compose down -v

  build:
    needs: [test-unit, test-integration, test-frontend]
    if: github.ref == 'refs/heads/main'
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: write
    outputs:
      image_tag: ${{ steps.meta.outputs.tags }}
      image_digest: ${{ steps.build.outputs.digest }}
    steps:
      - uses: actions/checkout@v4
      - name: Log in to GHCR
        uses: docker/login-action@v3
        with:
          registry: ${{ env.REGISTRY }}
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - name: Docker metadata
        id: meta
        uses: docker/metadata-action@v5
        with:
          images: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}
          tags: |
            type=sha,prefix=sha-
            type=raw,value=latest,enable={{is_default_branch}}
      - name: Build and push backend image
        id: build
        uses: docker/build-push-action@v5
        with:
          context: .
          file: docker/Dockerfile.backend
          target: runtime
          push: true
          tags: ${{ steps.meta.outputs.tags }}
          cache-from: type=gha
          cache-to: type=gha,mode=max
      - name: Trivy image scan
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:latest
          format: table
          exit-code: "1"
          severity: CRITICAL
      - name: Build frontend
        run: |
          cd frontend && npm ci && npm run build
      - uses: actions/upload-artifact@v4
        with:
          name: frontend-dist
          path: frontend/dist/
          retention-days: 7
```

#### `.github/workflows/deploy.yml`

```yaml
name: Deploy

on:
  workflow_run:
    workflows: [CI]
    branches: [main]
    types: [completed]

jobs:
  deploy-staging:
    if: ${{ github.event.workflow_run.conclusion == 'success' }}
    runs-on: ubuntu-latest
    environment: staging
    steps:
      - uses: actions/checkout@v4
      - name: Deploy to staging (Render/Railway/Fly.io)
        env:
          DEPLOY_HOOK_URL: ${{ secrets.STAGING_DEPLOY_HOOK_URL }}
        run: |
          curl -X POST "${DEPLOY_HOOK_URL}" \
            -H "Content-Type: application/json" \
            -d '{"image_tag": "${{ needs.build.outputs.image_tag }}"}'
      - name: Wait for deployment readiness
        run: |
          for i in $(seq 1 24); do
            STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
              "${{ vars.STAGING_URL }}/health/ready")
            if [ "$STATUS" = "200" ]; then
              echo "Staging is ready"
              exit 0
            fi
            echo "Attempt $i: status=$STATUS, waiting 10s..."
            sleep 10
          done
          echo "Staging did not become ready in 4 minutes"
          exit 1
      - name: Run smoke tests against staging
        run: |
          curl -f "${{ vars.STAGING_URL }}/health/ready"
          curl -f "${{ vars.STAGING_URL }}/v1/analytics" \
            -H "X-Session-ID: 00000000-0000-4000-a000-000000000001"

  deploy-production:
    needs: deploy-staging
    runs-on: ubuntu-latest
    environment:
      name: production
      url: ${{ vars.PRODUCTION_URL }}
    steps:
      - name: Deploy to production
        env:
          DEPLOY_HOOK_URL: ${{ secrets.PRODUCTION_DEPLOY_HOOK_URL }}
        run: |
          curl -X POST "${DEPLOY_HOOK_URL}" \
            -H "Content-Type: application/json"
      - name: Wait for production readiness
        run: |
          for i in $(seq 1 36); do
            STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
              "${{ vars.PRODUCTION_URL }}/health/ready")
            [ "$STATUS" = "200" ] && exit 0
            sleep 10
          done
          exit 1
```

---

## 4. Environment Configurations

### 4.1 Environment Tiers

| Variable | Development | Staging | Production |
|---|---|---|---|
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/sentinel.db` | `sqlite+aiosqlite:///./data/sentinel.db` | `postgresql+asyncpg://...` |
| `LOG_LEVEL` | `DEBUG` | `INFO` | `INFO` |
| `CORS_ORIGINS` | `["http://localhost:5173"]` | `["https://staging.sentinel.example.com"]` | `["https://sentinel.example.com"]` |
| `OLLAMA_DEFAULT_MODEL` | `mistral:7b-instruct-v0.2-q4_K_M` | `mistral:7b-instruct-v0.2-q4_K_M` | `mistral:7b-instruct-v0.2-q4_K_M` |
| `RATE_LIMIT_REQUESTS_PER_MINUTE` | `1000` (disabled) | `30` | `30` |
| `MAX_UPLOAD_SIZE_BYTES` | `104857600` (100MB) | `10485760` (10MB) | `10485760` (10MB) |
| Gunicorn workers | 1 (uvicorn --reload) | 2 | 2–4 |

### 4.2 Production Docker Compose

```yaml
# docker-compose.yml (production)
services:
  app:
    image: ghcr.io/your-org/sentinelai-guardrail/sentinel-backend:latest
    restart: unless-stopped
    environment:
      DATABASE_URL: ${DATABASE_URL}
      OLLAMA_BASE_URL: http://ollama:11434
      FAISS_INDEX_DIR: /app/data/faiss_indexes
      UPLOAD_DIR: /app/data/uploads
      CORS_ORIGINS: '["https://sentinel.example.com"]'
      LOG_LEVEL: INFO
    volumes:
      - sentinel_data:/app/data
      - sentinel_backups:/app/backups
    depends_on:
      ollama:
        condition: service_started
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health/live"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 90s

  ollama:
    image: ollama/ollama:latest
    restart: unless-stopped
    volumes:
      - ollama_models:/root/.ollama
    # GPU configuration (optional; remove if CPU-only)
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

  ollama-init:
    image: ollama/ollama:latest
    depends_on: [ollama]
    volumes:
      - ollama_models:/root/.ollama
    environment:
      - OLLAMA_HOST=ollama
    entrypoint: ["/bin/sh", "-c", "ollama pull mistral:7b-instruct-v0.2-q4_K_M && echo 'Model ready'"]
    restart: "no"

  caddy:
    image: caddy:2-alpine
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
      - "443:443/udp"
    volumes:
      - ./docker/Caddyfile:/etc/caddy/Caddyfile:ro
      - ./frontend/dist:/srv/frontend:ro
      - caddy_data:/data
      - caddy_config:/config
    depends_on: [app]

volumes:
  sentinel_data:
  sentinel_backups:
  ollama_models:
  caddy_data:
  caddy_config:
```

### 4.3 Free Hosting Platform Configurations

#### Render

```yaml
# render.yaml
services:
  - type: web
    name: sentinel-backend
    env: docker
    dockerfilePath: ./docker/Dockerfile.backend
    dockerContext: .
    dockerCommand: gunicorn sentinel.main:app --worker-class uvicorn.workers.UvicornWorker --workers 1 --bind 0.0.0.0:$PORT --timeout 60
    plan: free            # 512MB RAM; cold start ~30s
    envVars:
      - key: DATABASE_URL
        value: sqlite+aiosqlite:///./data/sentinel.db
      - key: VECTOR_STORE_BACKEND
        value: faiss
      - key: OLLAMA_BASE_URL
        value: http://localhost:11434   # NOTE: Ollama not available on Render free tier
        # For Render free tier: disable local model; OpenAI only
    disk:
      name: sentinel-data
      mountPath: /app/data
      sizeGB: 1
```

**Render free tier constraint:** Ollama cannot run on Render (no persistent LLM process). For Render free-tier deployment, the local model is disabled and users must supply an OpenAI API key. This is noted in the UI with an info banner.

#### Fly.io (preferred for Ollama support)

```toml
# fly.toml
app = "sentinelai-guardrail"
primary_region = "lax"

[build]
  dockerfile = "docker/Dockerfile.backend"
  target = "runtime"

[env]
  DATABASE_URL = "sqlite+aiosqlite:///app/data/sentinel.db"
  OLLAMA_BASE_URL = "http://localhost:11434"
  FAISS_INDEX_DIR = "/app/data/faiss_indexes"
  UPLOAD_DIR = "/app/data/uploads"
  PORT = "8000"

[[services]]
  internal_port = 8000
  protocol = "tcp"

  [[services.ports]]
    port = 443
    handlers = ["tls", "http"]
  [[services.ports]]
    port = 80
    handlers = ["http"]

  [services.concurrency]
    type = "requests"
    hard_limit = 25
    soft_limit = 20

[mounts]
  source = "sentinel_data"
  destination = "/app/data"

# Ollama runs as a background process within the same VM on Fly.io
[processes]
  app = "gunicorn sentinel.main:app --worker-class uvicorn.workers.UvicornWorker --workers 2 --bind 0.0.0.0:$PORT"
  ollama = "ollama serve"
```

---

## 5. Database Migration Rollout

### 5.1 Migration Execution in Deployment

Migrations run automatically as part of the deployment startup sequence, before the application server accepts traffic:

```dockerfile
# In the container CMD, migrations run before gunicorn starts
CMD ["sh", "-c", "alembic upgrade head && exec gunicorn sentinel.main:app ..."]
```

This ensures:

1. The database schema is always at `head` before any application code runs.
2. If the migration fails, the container exits with a non-zero code and the deployment fails before the new version accepts traffic.
3. The old container continues running until the new container is healthy (rolling deploy behavior on Fly.io/Render).

### 5.2 Migration Safety Gates

Before any migration is applied in CI:

```bash
# In the CI test-integration job
alembic check   # fails if there are unapplied migrations not in the versions/ directory
alembic upgrade head --sql | head -50  # dry-run: print SQL without executing; reviewed in PR
```

Each migration PR must include:

- The generated migration file in `alembic/versions/`.
- A comment block at the top of the migration file describing: what changes, why, and the rollback procedure.
- Confirmation that the migration is additive-only (no DROP COLUMN without a two-phase plan).

### 5.3 Zero-Downtime Migration Pattern (PostgreSQL)

For PostgreSQL deployments with live traffic:

**Phase 1 (deploy with old code):**

```python
# 0002_add_replayed_from_field.py
def upgrade():
    op.add_column('requests',
        sa.Column('replayed_from_request_id', sa.Text(), nullable=True)
    )
    # New column: nullable, no default required; old code ignores it
```

**Phase 2 (deploy with new code that uses the new column):**

- New code reads/writes `replayed_from_request_id`.
- No further migration needed.

**Phase 3 (optional: add NOT NULL constraint after backfill):**

```python
# 0003_backfill_and_constrain_replayed_field.py
def upgrade():
    op.execute("UPDATE requests SET replayed_from_request_id = NULL WHERE replayed_from_request_id IS NULL")
    # Add index if needed
    op.create_index('idx_requests_replayed_from', 'requests', ['replayed_from_request_id'],
                    postgresql_concurrently=True)
```

---

## 6. Versioning Strategy

### 6.1 Application Version

Semantic versioning (`MAJOR.MINOR.PATCH`) following these rules:

| Change Type | Version Bump | Example |
|---|---|---|
| Breaking API change | MAJOR | 1.x.x → 2.0.0 |
| New feature (backward compatible) | MINOR | 1.0.x → 1.1.0 |
| Bug fix, performance improvement | PATCH | 1.0.0 → 1.0.1 |
| Schema migration (additive) | PATCH or MINOR | treated as feature |

Version is defined in `backend/pyproject.toml`:

```toml
[project]
version = "1.0.0"
```

And echoed in the API response header: `X-App-Version: 1.0.0` (set by middleware).

### 6.2 Docker Image Tags

| Branch/Event | Tag |
|---|---|
| Push to `main` | `latest` + `sha-{git_sha[:7]}` |
| Pull request | `pr-{pr_number}` (not pushed to registry) |
| Git tag `v1.2.3` | `1.2.3` + `1.2` + `1` + `latest` |

Images are stored in GitHub Container Registry (GHCR): `ghcr.io/your-org/sentinelai-guardrail/sentinel-backend`.

### 6.3 Database Schema Version

Alembic manages schema versions. Each migration file is prefixed with a 4-digit sequence number. The current schema version is queryable at runtime:

```python
# GET /health/ready response includes schema version
{
  "status": "ready",
  "schema_version": "0003",
  "app_version": "1.1.0",
  "ollama_available": true,
  "db_connected": true
}
```

---

## 7. Rollback Strategy

### 7.1 Application Rollback (No Schema Change)

If the new deployment has a bug but no schema migration was applied:

```bash
# Fly.io
fly releases list                          # list recent releases
fly deploy --image ghcr.io/.../sentinel-backend:sha-{previous_sha}

# Render: trigger a manual deploy from the dashboard selecting the previous image tag

# Docker Compose (self-hosted)
docker compose down app
docker compose up -d --no-deps \
  -e IMAGE_TAG=sha-{previous_sha} app
```

Health check polling during rollback:

```bash
# Verify old version is restored
curl https://sentinel.example.com/health/ready
# Expected: {"status": "ready", "app_version": "{previous_version}"}
```

### 7.2 Application Rollback (With Schema Migration)

If a migration was applied and must be rolled back:

```bash
# Step 1: Stop new application
docker compose stop app

# Step 2: Run Alembic downgrade
docker compose run --rm app alembic downgrade -1

# Step 3: Start old application version
docker compose up -d --no-deps \
  -e IMAGE_TAG=sha-{previous_sha} app
```

**Prerequisite:** Every migration must implement a complete `downgrade()` function. This is enforced in code review. Auto-generated Alembic downgrades are reviewed for correctness before merging.

### 7.3 Database Rollback (Data Corruption)

If a deployment caused data corruption in the database:

```bash
# 1. Stop application immediately
docker compose stop app

# 2. Take a snapshot of current (corrupted) state for investigation
python scripts/backup.py --label corrupted-state

# 3. Restore from the last known good backup
python scripts/restore.py --backup-dir backups/2024-03-15/2024-03-15T00-00-00Z

# 4. Run migrations to bring schema up to current version (if backup is from older schema)
docker compose run --rm app alembic upgrade head

# 5. Validate restore
python scripts/validate_restore.py

# 6. Start application on previous image
docker compose up -d app
```

### 7.4 Rollback Decision Matrix

| Scenario | Strategy | RTO |
|---|---|---|
| Bug in new code, no migration | Redeploy previous image | < 5 min |
| Bug in new code, with migration (additive) | Redeploy previous image; no downgrade needed | < 5 min |
| Bug in new code, with destructive migration | Alembic downgrade + redeploy previous image | 10–20 min |
| Data corruption (application bug) | Restore from backup + redeploy previous image | 20–60 min |
| Infrastructure failure (disk, RAM) | Restore from backup to new instance | 30–90 min |

---

## 8. Monitoring and Alerting Setup

### 8.1 MVP Observability (Structured Logs Only)

In MVP, all observability is through structured JSON logs emitted to stdout, collected by the platform (Render/Fly.io log drain or Docker logging driver).

Key log events and their operational significance:

| Log Event | Level | Action Required |
|---|---|---|
| `pipeline_stage_failed` with `stage=llm_generation` | WARNING | Check Ollama health; model may have crashed |
| `audit_flush_failed` | ERROR | Database write issue; check disk space or DB connection |
| `kb_indexing_failed` with error | ERROR | User document could not be indexed; no action unless persistent |
| `rate_limit_exceeded` | WARNING | Expected; monitor for DDoS pattern |
| `safety_filter_unavailable` | CRITICAL | detoxify model failed to load; restart required |
| `pipeline_crash` (unhandled exception) | ERROR | Investigate stack trace immediately |
| Application startup complete | INFO | Expected on cold start; note the cold start duration |

### 8.2 Health Check Monitoring

The `/health/ready` endpoint returns a structured JSON response used by the deployment platform for readiness probing:

```json
{
  "status": "ready",
  "checks": {
    "database": "ok",
    "ollama": "ok",
    "embedding_model": "ok",
    "safety_classifier": "ok"
  },
  "schema_version": "0001",
  "app_version": "1.0.0",
  "uptime_seconds": 3847
}
```

If any check is not "ok", the endpoint returns HTTP 503 with `"status": "degraded"`. The deployment platform marks the instance as unhealthy and routes traffic to healthy instances (if multiple exist).

### 8.3 Phase 3: Prometheus + Grafana

In Phase 3, the `/metrics` endpoint (gated behind the `ENABLE_METRICS=true` environment variable) exposes:

```
# Key metrics
sentinel_requests_total{decision="accept", model="mistral"} 142
sentinel_requests_total{decision="block", model="mistral"} 23
sentinel_pipeline_latency_seconds{stage="llm_generation", quantile="0.95"} 18.4
sentinel_confidence_score_histogram_bucket{le="40"} 31
sentinel_hallucinations_total{model="mistral"} 18
sentinel_safety_filter_triggered_total{filter="toxicity"} 7
sentinel_tokens_total{model="mistral", direction="in"} 48320
sentinel_tokens_total{model="mistral", direction="out"} 31204
```

Alerting rules (Prometheus Alertmanager):

```yaml
groups:
  - name: sentinel
    rules:
      - alert: HighBlockRate
        expr: rate(sentinel_requests_total{decision="block"}[5m]) /
              rate(sentinel_requests_total[5m]) > 0.5
        for: 5m
        annotations:
          summary: "More than 50% of requests are being blocked"

      - alert: LLMUnavailable
        expr: sentinel_llm_availability{provider="ollama"} == 0
        for: 2m
        annotations:
          summary: "Ollama LLM is unavailable"

      - alert: PipelineLatencyHigh
        expr: histogram_quantile(0.95, sentinel_pipeline_latency_seconds) > 35
        for: 10m
        annotations:
          summary: "P95 pipeline latency exceeds 35 seconds"
```

---

## 9. Cold Start Handling

On free hosting platforms (Render free tier, Fly.io Machines with auto-stop), the application may be stopped after inactivity and require a cold start on the next request.

Cold start sequence (expected ~60–90 seconds on first request):

1. Container starts (~5s).
2. Python process launches; imports all modules (~3s).
3. `ApplicationContainer.initialize()` runs:
   - SentenceTransformer loads from cached weights (~2s).
   - detoxify model loads (~1s).
   - Database connects and migration check runs (~1s).
   - FAISS indexes load from disk (~0.5s per index).
4. Ollama starts (if co-located); model loads into RAM (~30–60s for 7B model on CPU).
5. First request is served.

**UI handling:**

- The frontend polls `GET /health/ready` every 3 seconds on cold start detection.
- Cold start detection: if the first request to `/v1/guardrail/submit` returns HTTP 503 with `"status": "warming_up"`, the UI shows a "Warming up (this may take up to 60 seconds)..." banner.
- The banner dismisses automatically when `/health/ready` returns HTTP 200.

```python
# In the health router, before full initialization completes:
@router.get("/health/ready")
async def health_ready(request: Request):
    container: ApplicationContainer = request.app.state.container
    if not container.is_initialized:
        return JSONResponse(
            status_code=503,
            content={"status": "warming_up", "message": "Service is initializing..."}
        )
    checks = await container.run_health_checks()
    status_code = 200 if all(v == "ok" for v in checks.values()) else 503
    return JSONResponse(status_code=status_code, content={"status": "ready", "checks": checks})
```
