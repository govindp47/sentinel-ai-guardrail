# 07_SECURITY_MODEL.md

# SentinelAI Guardrail — Security Model

---

## 1. Threat Model

### 1.1 System Context

SentinelAI Guardrail is a publicly accessible web application with no authentication in the MVP. Any internet user can submit prompts, upload documents, and observe pipeline results. The OpenAI API key is the only credential that enters the system, supplied by users voluntarily per-request.

The primary assets requiring protection are:

| Asset | Sensitivity | Threat |
|---|---|---|
| OpenAI API keys (user-supplied) | High | Interception, logging, or persistence of user credentials |
| Prompt content | Medium | Extraction of other users' prompts; PII leakage |
| Knowledge base documents | Medium | Cross-session access to another user's uploaded documents |
| Pipeline audit records | Medium | Cross-session access to another user's request history |
| Server infrastructure | High | Remote code execution, denial of service, data destruction |
| LLM provider access (Ollama) | Medium | Abuse of local model resources via unmetered requests |

### 1.2 Threat Actors

| Actor | Capability | Motivation |
|---|---|---|
| Opportunistic attacker | Script-kiddie level; automated scanning | Resource abuse (compute), data theft |
| Prompt injection attacker | LLM-familiar; crafted inputs | Bypass guardrails, manipulate pipeline output |
| API abuser | Automated scripting; no account required | Exhaust LLM compute, denial of service |
| Curious user | Normal browser tools | Probe for data from other sessions |
| Malicious document uploader | Can craft files | Path traversal, server-side parsing exploits |

---

## 2. Attack Surface Analysis

### 2.1 External Attack Surface

| Entry Point | Method | Threats |
|---|---|---|
| `POST /v1/guardrail/submit` | HTTP REST | Prompt injection, oversized payloads, PII in prompts, API key interception |
| `POST /v1/kb/documents` | HTTP multipart upload | Malicious file content, path traversal in filename, SSRF via document content, zip bombs |
| `GET /v1/requests` | HTTP REST | Cross-session data leakage if session ID is predictable or stolen |
| `WS /ws/{request_id}` | WebSocket | Session hijacking; unauthorized subscription to another request's events |
| `PUT /v1/policy` | HTTP REST | Threshold manipulation to weaken guardrails (accepted; policy is per-session) |
| Static SPA assets | HTTP GET | XSS via compromised CDN dependency |
| Caddy reverse proxy | All | TLS stripping, header injection |

### 2.2 Internal Attack Surface

| Component | Threat |
|---|---|
| Ollama HTTP API (internal) | SSRF: if a crafted prompt causes the backend to make unexpected HTTP calls; Ollama itself has no authentication |
| SQLite database file | Direct filesystem access if container is compromised |
| FAISS index files | Filesystem access; no encryption at rest in MVP |
| Upload directory | Path traversal in stored filenames |
| Python `subprocess` / `ProcessPoolExecutor` | Code injection via maliciously crafted document content (mitigated by library-level parsing) |

---

## 3. Authentication Architecture

### 3.1 MVP: Session-Based Pseudonymous Access

No user authentication exists in MVP. Access control is based on `session_id`:

- `session_id` is a UUID v4 generated client-side and stored in `sessionStorage`.
- It is sent as the `X-Session-ID` HTTP header on every request.
- The server creates a `sessions` record on first use and scopes all data (requests, KB documents, policy) to that `session_id`.
- `session_id` is **not** a security credential. It is a data-scoping mechanism. An attacker who obtains another user's `session_id` can access that session's data.

**Mitigations for session_id weakness (MVP):**

- Sessions contain no permanently sensitive data. Prompt content is masked. API keys are never stored.
- All sessions are short-lived (browser session; wiped on tab close).
- HTTPS enforced at the Caddy layer prevents `session_id` interception in transit.
- Rate limiting at the IP level limits enumeration attempts.

### 3.2 Session ID Validation

```python
# middleware.py
UUID_PATTERN = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$',
    re.IGNORECASE
)

async def session_id_middleware(request: Request, call_next):
    session_id = request.headers.get("X-Session-ID", "")
    if not session_id or not UUID_PATTERN.match(session_id):
        return JSONResponse(
            status_code=400,
            content={"error_code": "INVALID_SESSION_ID",
                     "message": "X-Session-ID header must be a valid UUID v4."}
        )
    request.state.session_id = session_id.lower()
    return await call_next(request)
```

### 3.3 Phase 3: Authentication Upgrade Path

When authentication is added:

- JWT-based authentication (short-lived access tokens, refresh token rotation).
- `session_id` replaced by `user_id` from the JWT `sub` claim.
- All database queries switch from `WHERE session_id = :sid` to `WHERE user_id = :uid`.
- The schema change is additive: `user_id` column is added to `sessions`, `requests`, and `kb_documents` tables.

---

## 4. Authorization Model

### 4.1 Resource Ownership Enforcement

Every database query that accesses user-scoped data includes the `session_id` condition. This is enforced at the repository layer, not the route layer, so it cannot be bypassed by a route handler omission.

```python
# infrastructure/db/repositories/request_repo.py
class RequestRepository:
    async def get_by_id(self, request_id: str, session_id: str) -> RequestRecord | None:
        result = await self.session.execute(
            select(RequestORM)
            .where(RequestORM.id == request_id)
            .where(RequestORM.session_id == session_id)  # ownership enforced here
        )
        return result.scalar_one_or_none()
```

**Rule:** If `session_id` is omitted from a query on a session-scoped table, a `RepositorySecurityError` is raised. This is enforced via a base repository class that validates the `session_id` parameter before executing any SELECT, UPDATE, or DELETE.

### 4.2 KB Document Access

FAISS queries include a session-ownership check on the returned chunk IDs:

```python
async def retrieve(self, kb_id: str, query_vector: np.ndarray, session_id: str, top_k: int) -> list[Evidence]:
    faiss_ids, scores = self.vector_store.query(kb_id, query_vector, top_k)
    chunks = await self.chunk_repo.fetch_by_faiss_ids(faiss_ids, session_id=session_id)
    # fetch_by_faiss_ids joins kb_chunks → kb_documents and filters WHERE session_id = :session_id
    # If a faiss_id belongs to another session, it is excluded from the result silently
    return self._to_evidence(chunks, scores)
```

### 4.3 Policy Modification

Policy configuration can only be modified for the current session. The `PUT /v1/policy` endpoint reads `session_id` from `request.state` (set by middleware) and creates the policy snapshot scoped to that session. No endpoint accepts an arbitrary `session_id` as a query parameter or body field.

### 4.4 WebSocket Authorization

The WebSocket endpoint at `WS /ws/{request_id}` validates that the `request_id` belongs to the requesting session before establishing the connection:

```python
@router.websocket("/ws/{request_id}")
async def pipeline_ws(websocket: WebSocket, request_id: str):
    session_id = websocket.headers.get("X-Session-ID", "")
    if not UUID_PATTERN.match(session_id):
        await websocket.close(code=4000)  # custom: invalid session
        return

    exists = await request_repo.exists(request_id=request_id, session_id=session_id)
    if not exists:
        await websocket.close(code=4004)  # custom: request not found / unauthorized
        return

    await websocket.accept()
    # ... event loop
```

---

## 5. Encryption Strategy

### 5.1 In-Transit Encryption

- All HTTP and WebSocket traffic is encrypted via TLS 1.2+ enforced at the Caddy reverse proxy.
- Caddy obtains and auto-renews TLS certificates via Let's Encrypt (ACME protocol).
- HSTS header is set: `Strict-Transport-Security: max-age=31536000; includeSubDomains`.
- TLS 1.0 and 1.1 are disabled. Minimum TLS version: 1.2. Preferred: 1.3.
- The OpenAI API key travels exclusively over HTTPS (both client→server and server→OpenAI).

**Caddyfile (relevant excerpt):**

```
{
    email admin@example.com
}

sentinel.example.com {
    tls {
        protocols tls1.2 tls1.3
    }
    header Strict-Transport-Security "max-age=31536000; includeSubDomains; preload"
    header X-Content-Type-Options nosniff
    header X-Frame-Options DENY
    header Referrer-Policy strict-origin-when-cross-origin
    header Content-Security-Policy "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self' wss://sentinel.example.com"

    reverse_proxy /v1/* localhost:8000
    reverse_proxy /ws/* localhost:8000
    root * /srv/frontend
    file_server
}
```

### 5.2 At-Rest Encryption

**MVP:** No application-level encryption at rest. Relies on host OS disk encryption (e.g., LUKS on Linux, FileVault on macOS). For cloud deployments (Render, Railway, Fly.io), the platform provides encrypted storage volumes.

**Rationale for MVP:** The data stored at rest (audit records, KB chunks) contains no credentials and masked PII. The sensitivity does not justify the engineering overhead of application-level AES encryption in the MVP.

**Phase 3 upgrade:** If user accounts are added and prompt content becomes persistent, AES-256-GCM encryption of `prompt_masked_text` and `final_response_text` columns is added using a per-deployment secret key (stored in the environment, not in the database).

### 5.3 OpenAI API Key: Zero-Persistence Model

The key's lifecycle through the system:

```
1. HTTPS POST body → Caddy (TLS terminated) → FastAPI
2. ApiKeyStrippingMiddleware reads X-Openai-Api-Key header
3. Header value assigned to request.state.openai_api_key (Python string, process memory)
4. Header removed from the request object before any further processing
5. Context.openai_api_key = request.state.openai_api_key (transient field)
6. OpenAIAdapter.complete(api_key=context.openai_api_key) → httpx call with
   Authorization: Bearer {key} header
7. httpx sends the header over TLS to api.openai.com
8. After httpx call returns: key remains in context memory only
9. PipelineContext is garbage collected after the response is sent
10. structlog processor strips any field matching /api.?key|authorization|bearer/i from logs

NEVER:
- Written to database
- Written to any log file
- Included in WebSocket events
- Returned in any API response
- Stored in Python module-level variables
```

---

## 6. Key Management

### 6.1 Application Secret Keys

No application-level secret keys exist in MVP (no JWT signing, no cookie signing, no encryption keys). The only secrets are deployment environment variables:

| Variable | Purpose | Storage |
|---|---|---|
| `DATABASE_URL` | Database connection string (may include password for PostgreSQL) | Environment variable; `.env` file excluded from git via `.gitignore` |
| `OLLAMA_BASE_URL` | Internal service URL (no secret) | Environment variable |
| `CORS_ORIGINS` | Allowed frontend origins | Environment variable |

### 6.2 Secrets Management Rules

1. No secrets in source code, Dockerfiles, or docker-compose files.
2. `.env` file is in `.gitignore`. `.env.example` is committed with placeholder values only.
3. In CI/CD (GitHub Actions): secrets are stored in GitHub Secrets and injected as environment variables at deploy time.
4. In production (Render/Railway/Fly.io): secrets are configured via the platform's secret management UI, not via committed configuration files.

### 6.3 Phase 3: Key Rotation

When encryption at rest is added (Phase 3):

- A `SECRET_KEY` environment variable is introduced (32-byte random hex, generated at deployment).
- Key rotation requires: decrypt all encrypted columns with old key, re-encrypt with new key, rotate `SECRET_KEY` environment variable. A migration script (`scripts/rotate_encryption_key.py`) handles this process.
- Old key is retained in `SECRET_KEY_OLD` for one rotation cycle to decrypt records written before the rotation.

---

## 7. Data Protection Mechanisms

### 7.1 PII Detection and Masking

PII masking is the primary data protection mechanism for prompt content. It is applied before any database write and before any LLM call used for claim extraction/verification.

```
Original prompt:  "What should John Doe (john@example.com, SSN: 123-45-6789) know about GDPR?"
Masked prompt:    "What should John Doe ([EMAIL_REDACTED], SSN: [SSN_REDACTED]) know about GDPR?"
```

**What is stored:** The masked prompt only. The original is not persisted anywhere.
**What is hashed:** The original prompt is SHA-256 hashed before masking; the hash is stored as `prompt_hash` for duplicate detection. SHA-256 is a one-way function; the original cannot be recovered from the hash.
**Replay behavior:** Replay uses the stored masked prompt. If PII was detected, replay is disabled (the masked prompt changes the semantic meaning of factual claims about the PII subject).

### 7.2 Response Content Masking

LLM responses are not PII-masked before storage. Rationale: the LLM response is generated from the user's own prompt and knowledge base; it does not contain other users' data. If a user prompts the LLM to reproduce their own PII, the response will contain it — this is the user's own information.

**Limitation noted:** If a user's KB document contains third-party PII and the LLM reproduces it in the response, that PII is stored in `final_response_text`. This is a known limitation in MVP scope. Phase 3 adds response-level PII scanning.

### 7.3 Uploaded Document Protection

- Uploaded files are stored with a UUID-based filename (never the original filename on disk) to prevent path traversal.
- The original filename is stored in `kb_documents.original_filename` (for display) and sanitized before storage:

```python
def sanitize_filename(filename: str) -> str:
    # Remove path components
    filename = os.path.basename(filename)
    # Remove all characters except alphanumeric, dot, hyphen, underscore
    filename = re.sub(r'[^\w.\-]', '_', filename)
    # Prevent hidden files
    filename = filename.lstrip('.')
    # Truncate to 100 chars
    return filename[:100] or 'document'
```

- Storage path construction:

```python
storage_path = os.path.join(
    config.upload_dir,
    session_id,          # session-namespaced subdirectory
    f"{uuid4()}_{sanitize_filename(original_filename)}"
)
os.makedirs(os.path.dirname(storage_path), exist_ok=True)
```

- `os.path.join` with the `session_id` prefix prevents path traversal: a malicious filename like `../../etc/passwd` becomes `upload_dir/{session_id}/etc/passwd` after `os.path.basename` strips the path components.

### 7.4 Input Size Limits

| Input | Limit | Enforcement |
|---|---|---|
| Prompt text | 4,000 characters | Client-side (disabled submit) + server-side (Pydantic `max_length=4000`) |
| Uploaded document | 10 MB | Client-side (file input validation) + server-side (Content-Length check in upload endpoint) |
| JSON body (any endpoint) | 1 MB | Caddy `request_body` directive; returns HTTP 413 |
| WebSocket message | 64 KB | FastAPI WebSocket `max_size` parameter |
| Query parameters | 2 KB total | Caddy `uri` directive |

---

## 8. Tamper Detection

### 8.1 Request Record Integrity

Audit records are append-only. Once a `requests` row reaches `status = completed/blocked/failed`, no application code path modifies it. This is enforced by:

1. **Repository-level guards:** `RequestRepository.update_status()` only accepts transitions from `pending → processing → {completed|blocked|failed}`. Any attempt to update a completed record raises `RecordImmutableError`.
2. **No UPDATE statements** on content columns (`prompt_masked_text`, `final_response_text`, `confidence_score`, etc.) after the initial write.
3. **Database-level:** In Phase 3, a PostgreSQL trigger can be added to reject UPDATE statements on these columns:

```sql
CREATE OR REPLACE FUNCTION prevent_request_modification()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.status IN ('completed', 'blocked', 'failed') THEN
        RAISE EXCEPTION 'Completed request records are immutable.';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER request_immutability
BEFORE UPDATE ON requests
FOR EACH ROW EXECUTE FUNCTION prevent_request_modification();
```

### 8.2 Pipeline Determinism as Integrity Signal

The confidence scoring engine is deterministic. An operator can re-run claim verification on a stored audit record and compare the computed score against the stored score. A mismatch indicates either a model version change (expected) or record tampering (unexpected). A `verify_audit_record(request_id)` utility is provided in `scripts/verify_audit.py`.

---

## 9. Abuse Mitigation

### 9.1 Rate Limiting

Rate limiting is enforced at the Caddy layer (per-IP) and optionally at the FastAPI middleware layer (per-session).

**Caddy rate limiting** (via `caddy-ratelimit` plugin):

```
rate_limit {
    zone guardrail_submit {
        match path /v1/guardrail/submit
        key {remote_host}
        events 10
        window 1m
    }
    zone kb_upload {
        match path /v1/kb/documents
        key {remote_host}
        events 5
        window 5m
    }
    zone global {
        key {remote_host}
        events 100
        window 1m
    }
}
```

**Rate limit response:** HTTP 429 with:

```json
{
    "error_code": "RATE_LIMIT_EXCEEDED",
    "message": "Too many requests. Please wait before trying again.",
    "retry_after_seconds": 60
}
```

**FastAPI session-level rate limiting** (middleware, optional):

- Maintains an in-process counter per `session_id` using an LRU dict (max 10,000 entries).
- Limit: 30 guardrail requests per minute per session.
- Resets on rolling 60-second window.

### 9.2 Prompt Length Enforcement

Maximum prompt length of 4,000 characters is enforced at two layers:

- Pydantic schema validation (`max_length=4000`): returns HTTP 422 with `PROMPT_TOO_LONG` before any processing.
- Client-side: submit button disabled when `prompt.length > 4000`.

This prevents token-stuffing attacks that would consume excessive LLM compute.

### 9.3 Document Upload Abuse

- File size limit (10 MB) enforced at Caddy (HTTP 413) and in the FastAPI upload handler.
- MIME type allowlist checked before writing to disk. The check uses `python-magic` (libmagic bindings) to validate the actual file magic bytes, not just the declared `Content-Type` header:

```python
import magic
ALLOWED_MIME_TYPES = {
    'text/plain', 'text/markdown', 'application/pdf',
    'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
}

async def validate_upload(file: UploadFile) -> None:
    header_bytes = await file.read(2048)
    await file.seek(0)
    detected_mime = magic.from_buffer(header_bytes, mime=True)
    if detected_mime not in ALLOWED_MIME_TYPES:
        raise UploadValidationError(
            f"File type '{detected_mime}' is not allowed. "
            f"Accepted types: PDF, TXT, MD, DOCX."
        )
```

- ZIP bomb protection: PDF and DOCX parsers (PyMuPDF, python-docx) decompress file content internally. Both are set with decompression limits:
  - PyMuPDF: no explicit limit needed; handles malformed PDFs gracefully without crashing.
  - python-docx: extracts DOCX (ZIP format) with a 50 MB extraction limit enforced via a custom `ZipFile` wrapper that counts extracted bytes.

### 9.4 Prompt Injection Awareness

The system's own prompt injection detector (Stage 1 of the pipeline) is the first line of defense against prompt injection. However, the system itself uses LLM prompts internally (claim extraction, verification, RAG augmentation). These internal prompts are constructed with hardcoded templates where the user content is inserted at a defined injection point — not concatenated into an instruction prefix.

```python
# Claim extraction prompt: user content is in a clearly delimited section
CLAIM_EXTRACTION_PROMPT = """
You are a fact-extraction assistant. [... fixed instructions ...]

Text:
{response_text}
"""
# The {response_text} is the LLM's own generated output, not raw user input.
# Even if the LLM output contains injection attempts targeting the extractor,
# the extractor is only asked to return a JSON array of strings.
# A JSON array cannot execute instructions; worst case is a parse error.
```

For claim verification, the prompt structure is similarly hardened. The `claim_text` and `evidence_text` are inserted into a template that immediately follows with `Respond with ONLY a JSON object`. Prompt injection into the verifier can only result in malformed JSON (which is caught by the parse fallback, not executed).

### 9.5 CORS Policy

```python
# middleware.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.cors_origins,   # e.g., ["https://sentinel.example.com"]
    allow_credentials=False,             # no cookies used
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "X-Session-ID", "X-Openai-Api-Key", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)
```

In development, `cors_origins = ["http://localhost:5173"]`. In production, only the deployed frontend domain is allowed. Wildcard `*` is never used in production.

### 9.6 Security Headers

Set by Caddy on all responses:

| Header | Value | Purpose |
|---|---|---|
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains` | Force HTTPS |
| `X-Content-Type-Options` | `nosniff` | Prevent MIME sniffing |
| `X-Frame-Options` | `DENY` | Prevent clickjacking |
| `Referrer-Policy` | `strict-origin-when-cross-origin` | Limit referrer leakage |
| `Content-Security-Policy` | `default-src 'self'; script-src 'self'; connect-src 'self' wss:` | XSS mitigation |
| `Permissions-Policy` | `camera=(), microphone=(), geolocation=()` | Disable unused browser APIs |

---

## 10. Secure Data Deletion Strategy

### 10.1 KB Document Deletion

When a user deletes a KB document:

```python
async def delete_kb_document(doc_id: str, session_id: str) -> None:
    doc = await kb_repo.get(doc_id, session_id=session_id)
    if not doc:
        raise KBDocumentNotFoundError()

    # 1. Remove vectors from FAISS index
    chunk_faiss_ids = await chunk_repo.get_faiss_ids(doc_id)
    if chunk_faiss_ids:
        async with vector_store.write_lock(doc.kb_id):
            vector_store.remove_ids(doc.kb_id, chunk_faiss_ids)
            vector_store.persist(doc.kb_id)  # overwrite .faiss file

    # 2. Delete chunks from database (cascade handled by FK)
    await chunk_repo.delete_by_document(doc_id)

    # 3. Delete document record
    await kb_repo.delete(doc_id)

    # 4. Delete file from filesystem
    if os.path.exists(doc.storage_path):
        os.unlink(doc.storage_path)
        # Overwrite with zeros before unlink (optional; platform-dependent effectiveness)
        # In MVP: standard unlink is sufficient (no evidence of sensitive data in raw document)

    # 5. Update KB metadata
    await kb_repo.update_chunk_count(doc.kb_id)
```

**FAISS ID removal:** FAISS `IndexFlatL2` does not support `remove_ids` directly. Workaround: rebuild the index from the remaining chunks. For large indexes, use `IndexIDMap` which wraps `IndexFlatL2` and supports `remove_ids(ids)`. The MVP uses `IndexIDMap` from initialization:

```python
# faiss_store.py
import faiss

class FAISSStore:
    def _create_index(self, dim: int) -> faiss.Index:
        flat = faiss.IndexFlatL2(dim)
        return faiss.IndexIDMap(flat)  # enables remove_ids

    def remove_ids(self, kb_id: str, faiss_ids: list[int]) -> None:
        index = self._load_index(kb_id)
        id_array = np.array(faiss_ids, dtype=np.int64)
        index.remove_ids(faiss.IDSelectorArray(len(id_array), faiss.swig_ptr(id_array)))
```

### 10.2 Session Data Retention

In MVP, data is retained for the browser session duration only:

- Session records and all cascaded data are not explicitly deleted on session end (the browser closing does not send a notification to the server).
- A background cleanup job (Phase 3) deletes sessions and cascaded data older than a configurable `session_retention_days` (default: 7 days for anonymous sessions).
- Uploaded files are included in the cleanup: the session cleanup job calls `delete_kb_document` for each document in the session before deleting the session record.

### 10.3 API Key Secure Deletion

No explicit deletion needed: the API key exists only in Python heap memory for the duration of a single `async def` call chain. Python's garbage collector reclaims the memory after the `PipelineContext` object goes out of scope. The memory region may be reused by the OS (Python does not zero memory on deallocation). This is acceptable for the threat model: an attacker with access to process memory has already compromised the host.

---

## 11. Dependency Security

### 11.1 Dependency Pinning

All Python dependencies are pinned to exact versions in `pyproject.toml` using `==` constraints. The `uv` package manager generates a `uv.lock` file (equivalent of `requirements.lock`) which is committed to version control.

```toml
[project.dependencies]
fastapi = "==0.115.0"
pydantic = "==2.7.0"
sqlalchemy = "==2.0.30"
openai = "==1.30.0"
sentence-transformers = "==3.0.0"
detoxify = "==1.5.2"
faiss-cpu = "==1.8.0"
python-magic = "==0.4.27"
# ...
```

### 11.2 Vulnerability Scanning

- `pip-audit` runs in the CI pipeline on every PR to scan for known CVEs in Python dependencies.
- `trivy` scans the Docker image for OS-level vulnerabilities in the CI `build` step.
- Dependabot (GitHub) is configured to open PRs for security updates automatically.

### 11.3 Frontend Dependency Security

- `npm audit` runs in the CI frontend lint stage.
- Subresource Integrity (SRI) is applied to any third-party scripts loaded from CDNs (none in the current design — all dependencies are bundled by Vite).
- The Content Security Policy prevents execution of inline scripts and scripts from unauthorized origins.
