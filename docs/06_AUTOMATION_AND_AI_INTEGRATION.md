# 06_AUTOMATION_AND_AI_INTEGRATION.md

# SentinelAI Guardrail — Automation & AI Integration

---

## 1. Overview

SentinelAI Guardrail is itself an AI integration system. Every major subsystem involves a model inference call, an embedding operation, or a classification pipeline. This document specifies the exact integration boundaries, data contracts, inference triggers, latency budgets, failure modes, and privacy safeguards for every AI component in the system.

---

## 2. AI Component Inventory

| Component | Model Type | Runtime | Trigger | Latency Budget |
|---|---|---|---|---|
| LLM Generation | Generative (Mistral / GPT-4o) | Ollama / OpenAI API | Per guardrail request | ≤ 20s (local), ≤ 8s (OpenAI) |
| Claim Extraction | Generative (same model as above) | Ollama / OpenAI API | After LLM generation, if HD enabled | ≤ 5s |
| Claim Verification | Generative (per claim, batched) | Ollama / OpenAI API | After evidence retrieval | ≤ 2s × claim_batch |
| Document Embedding | Bi-encoder (MiniLM / BGE) | SentenceTransformers (CPU) | At KB document indexing | ≤ 100ms per chunk |
| Query Embedding | Same bi-encoder | SentenceTransformers (CPU) | Per claim during retrieval | ≤ 80ms per claim |
| Toxicity / Safety Classification | Multi-label classifier (detoxify) | Local (CPU) | After LLM generation | ≤ 300ms |
| Vector Similarity Search | FAISS IndexFlatL2 | In-process (CPU) | Per claim during evidence retrieval | ≤ 20ms per query (< 50k chunks) |

---

## 3. Data Ingestion Pipeline (Knowledge Base)

### 3.1 Pipeline Stages

```
User uploads file (PDF, TXT, MD, DOCX)
        │
        ▼
[1] FileValidation
    - Check MIME type against allowlist: {text/plain, text/markdown,
      application/pdf, application/vnd.openxmlformats-officedocument.wordprocessingml.document}
    - Check file size ≤ config.max_upload_size_bytes (default: 10MB)
    - If invalid: raise UploadValidationError → HTTP 400

        │
        ▼
[2] FileStorage
    - Generate safe storage filename: {uuid4()}_{sanitized_original_name}
    - Write raw bytes to config.upload_dir
    - Create kb_documents record (status=PENDING)

        │
        ▼
[3] Enqueue IndexDocumentJob
    - Push job to asyncio.Queue
    - Return document_id to client immediately (HTTP 202 Accepted)
    - WebSocket event: {type: "kb_status", doc_id: ..., status: "pending"}

        │ (background worker)
        ▼
[4] TextExtraction
    - PDF:  PyMuPDF (fitz) — extract text page by page; preserve page boundaries as chunk separators
    - DOCX: python-docx — extract paragraph text; preserve heading structure
    - TXT/MD: read directly; no special extraction

    - If extraction yields 0 characters: mark FAILED("empty document")

        │
        ▼
[5] DocumentChunker
    Algorithm: Sliding window with overlap
    - chunk_size:    512 characters (configurable, stored in kb_documents)
    - chunk_overlap: 64 characters
    - Split on sentence boundaries where possible (using simple regex: (?<=[.!?])\s+)
    - If no sentence boundary found within window: hard split at chunk_size

    Output: list[TextChunk(index, text, char_start, char_end)]

    - Insert all chunks into kb_chunks table (faiss_vector_id = NULL at this point)
    - WebSocket event: {type: "kb_status", doc_id: ..., status: "indexing", chunk_count: N}

        │
        ▼
[6] EmbeddingGeneration
    - Call EmbeddingAdapter.embed_batch(chunk_texts: list[str]) → vectors: np.ndarray (N × D)
    - Batch size: 32 chunks per embed call (balances memory vs. throughput)
    - If embedding fails (model unavailable): mark FAILED("embedding error")

        │
        ▼
[7] FAISSIndexing
    - Acquire per-KB asyncio.Lock
    - Load existing index if present, or create new IndexFlatL2(embedding_dim)
    - index.add(vectors)  → assigns sequential faiss_vector_ids starting from current index size
    - Serialize index to disk: {faiss_index_dir}/{kb_id}.faiss
    - Update id_map JSON: {faiss_index_dir}/{kb_id}_id_map.json
        id_map[faiss_vector_id] = chunk_db_id (UUID string)
    - Update kb_chunks.faiss_vector_id for each chunk (batch UPDATE)
    - Release lock

        │
        ▼
[8] Finalization
    - Update kb_documents: status=READY, chunk_count=N, indexed_at=NOW()
    - Reload in-process FAISS index cache for this kb_id
    - WebSocket event: {type: "kb_status", doc_id: ..., status: "ready", chunk_count: N}
```

### 3.2 Text Chunker Algorithm (Detailed)

```python
class TextChunker:
    SENTENCE_BOUNDARY = re.compile(r'(?<=[.!?])\s+')

    def chunk(
        self,
        text: str,
        chunk_size: int = 512,
        overlap: int = 64,
    ) -> list[TextChunk]:
        chunks = []
        start = 0
        text_len = len(text)

        while start < text_len:
            end = min(start + chunk_size, text_len)

            if end < text_len:
                # Try to find a sentence boundary within the last 20% of the window
                search_start = start + int(chunk_size * 0.8)
                segment = text[search_start:end]
                boundaries = list(self.SENTENCE_BOUNDARY.finditer(segment))
                if boundaries:
                    last_boundary = boundaries[-1]
                    end = search_start + last_boundary.start() + 1  # include the period

            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append(TextChunk(
                    index=len(chunks),
                    text=chunk_text,
                    char_start=start,
                    char_end=end,
                ))

            # Next chunk starts overlap characters before the end of this chunk
            start = max(start + 1, end - overlap)

        return chunks
```

**Edge cases:**

- Single word document: produces 1 chunk.
- Chunk boundary lands mid-word: acceptable; sentence-boundary detection minimizes this.
- Consecutive whitespace: normalized to single space before chunking.
- Non-UTF-8 bytes (e.g., binary PDFs with embedded fonts): PyMuPDF handles encoding; non-decodable characters are replaced with `?` before chunking.

---

## 4. Inference Pipeline (Per Guardrail Request)

### 4.1 LLM Inference Integration

#### OllamaAdapter

```python
class OllamaAdapter:
    BASE_URL: str  # from config

    async def complete(
        self,
        prompt: str,
        model_name: str,
        temperature: float,
        max_tokens: int,
        timeout_seconds: float,
        api_key: str | None = None,  # ignored for Ollama
    ) -> LLMResult:
        start = time.monotonic()

        # Ollama exposes an OpenAI-compatible endpoint
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            try:
                response = await client.post(
                    f"{self.BASE_URL}/v1/chat/completions",
                    json=payload
                )
            except httpx.ConnectError:
                raise LLMUnavailableError("Ollama service is not reachable.")
            except httpx.TimeoutException:
                raise LLMTimeoutError(f"Ollama did not respond within {timeout_seconds}s.")

        if response.status_code != 200:
            raise LLMProviderError(f"Ollama returned HTTP {response.status_code}")

        data = response.json()
        text = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})

        return LLMResult(
            text=text,
            tokens_in=usage.get("prompt_tokens", 0),
            tokens_out=usage.get("completion_tokens", 0),
            latency_ms=int((time.monotonic() - start) * 1000),
            model_name=model_name,
            provider="ollama",
        )
```

#### OpenAIAdapter

```python
class OpenAIAdapter:
    async def complete(
        self,
        prompt: str,
        model_name: str,
        temperature: float,
        max_tokens: int,
        timeout_seconds: float,
        api_key: str | None = None,
    ) -> LLMResult:
        if not api_key:
            raise LLMAuthenticationError("OpenAI API key is required.")

        start = time.monotonic()
        client = AsyncOpenAI(api_key=api_key, timeout=timeout_seconds)

        try:
            response = await client.chat.completions.create(
                model=model_name or "gpt-4o-mini",
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
            )
        except openai.AuthenticationError:
            raise LLMAuthenticationError("Invalid or expired OpenAI API key.")
        except openai.RateLimitError:
            raise RateLimitError("OpenAI rate limit or quota exceeded.")
        except openai.APITimeoutError:
            raise LLMTimeoutError(f"OpenAI did not respond within {timeout_seconds}s.")

        text = response.choices[0].message.content or ""
        return LLMResult(
            text=text,
            tokens_in=response.usage.prompt_tokens,
            tokens_out=response.usage.completion_tokens,
            latency_ms=int((time.monotonic() - start) * 1000),
            model_name=response.model,
            provider="openai",
        )
```

### 4.2 Claim Extraction Integration

```
INPUT:  LLM response text
OUTPUT: list[Claim]

Trigger conditions:
  - context.policy.module_flags['hallucination_detection'] == True
  - context.llm_response_text is not None and len > 20 chars

Model used: same model as the original LLM call (reuses the already-warmed model)
Temperature: 0.0 (deterministic output required)
Max tokens: 512 (claim list rarely exceeds this)
Timeout: 10s (shorter; simpler task than generation)

Post-processing:
  1. Parse response as JSON array
  2. If JSON parse fails: regex fallback to extract [...] block
  3. If fallback fails: return empty list (log parse error, continue pipeline)
  4. Deduplicate claims (case-insensitive exact match)
  5. Truncate to config.max_claims_per_response (default: 20)
  6. Strip whitespace from each claim string
  7. Filter claims shorter than 10 characters (too short to be verifiable)
```

### 4.3 Evidence Retrieval Integration

```
INPUT:  Claim text (string), kb_id (string | None), top_k (int, default 5)
OUTPUT: list[Evidence]

For each claim:
  1. EmbeddingAdapter.embed(claim.text) → query_vector: np.ndarray (1 × D)
     - Check embedding LRU cache first (key: sha256(claim.text))
     - Cache hit: return cached vector (~0ms)
     - Cache miss: embed and insert into cache (~80ms)

  2. FAISSStore.query(kb_id, query_vector, top_k)
     - Acquire read on in-process index (no lock needed for FAISS reads)
     - index.search(query_vector, k=top_k) → (distances, faiss_ids)
     - Convert L2 distances to cosine similarity scores:
         similarity = 1.0 - (distance / 2.0)   # valid only for normalized vectors
         Note: vectors are L2-normalized before indexing to enable this conversion
     - Return faiss_ids and similarity scores

  3. ChunkRepository.fetch_by_faiss_ids(faiss_ids, session_id)
     - SQL query: kb_chunks JOIN kb_documents WHERE faiss_vector_id IN (...)
     - Enforces session_id ownership check (a session cannot retrieve another session's KB)

  4. Map DB results to Evidence objects; attach relevance_score and rank

No evidence available (kb_id is None):
  - Return empty list immediately; skip embedding and FAISS calls
```

### 4.4 Safety Classification Integration

```
INPUT:  LLM response text
OUTPUT: list[SafetyFilterResult]

Runtime: detoxify library, loaded at application startup into process memory

Detoxify inference call:
  results = detoxify_model.predict(response_text)
  # Returns dict: {
  #   "toxicity": 0.02,
  #   "severe_toxicity": 0.001,
  #   "obscene": 0.01,
  #   "threat": 0.005,
  #   "insult": 0.02,
  #   "identity_attack": 0.003,
  #   "sexual_explicit": 0.001
  # }

Harmful Instruction Pattern Check (rule-based, runs concurrently):
  PATTERNS = [
    r'(synthesize|manufacture|produce)\s+.{0,30}(explosive|poison|drug|weapon)',
    r'step[s]?\s+(to|for|by step).{0,20}(hack|bypass|exploit)',
    r'how\s+to\s+(make|build|create)\s+.{0,30}(bomb|virus|malware)',
    # ... additional patterns
  ]
  harm_detected = any(re.search(p, response_text, re.IGNORECASE) for p in PATTERNS)

Output construction:
  For each detoxify label where score > 0.01 (threshold to filter noise):
    SafetyFilterResult(
      filter_name=label,
      result='flagged' if score >= safety_block_threshold else 'clean',
      score=score
    )

  If harm_detected:
    SafetyFilterResult(
      filter_name='harmful_instruction',
      result='flagged',
      score=1.0
    )

Parallelism: asyncio.gather(detoxify_task, harmful_instruction_task)
  - detoxify is CPU-bound: dispatched to ProcessPoolExecutor
  - harmful instruction check is pure Python: runs in event loop
```

---

## 5. Inference Triggers (State Machine)

```
Request received
      │
      ▼
[TRIGGER 1] Prompt Validation
  Always triggered. No model inference in this stage (pure rule-based).

      │
      ▼ (if not blocked)
[TRIGGER 2] LLM Generation
  Always triggered (if validation passes).
  Model: user-selected (ollama/{model_name} or openai/{model_name})
  Input: validated prompt (+ RAG context block if fallback=rag)
  Temperature: config.llm_default_temperature (0.7 default; 0.4 on lower-temp retry)

      │
      ▼ (if generation succeeds)
[TRIGGER 3] Claim Extraction
  Triggered if: hallucination_detection module flag == True
  Model: config.claim_model_name (same as LLM, reuses warmed model)
  Temperature: 0.0 (always deterministic)
  Input: LLM response text

      │ (concurrent with Trigger 5)
      ▼ (if claims extracted)
[TRIGGER 4] Query Embedding (per claim)
  Triggered if: len(claims) > 0 AND kb_id is not None
  Model: SentenceTransformer (config.embedding_model)
  Input: claim.text

      │
      ▼
[TRIGGER 4b] FAISS Search (per claim)
  Triggered if: embedding generated AND FAISS index exists for kb_id

      │
      ▼
[TRIGGER 4c] Claim Verification (per claim, after evidence retrieved)
  Triggered if: evidence retrieved (may be empty list)
  Model: config.claim_model_name
  Temperature: 0.0
  Input: claim text + formatted evidence chunks

      │ (concurrent with Trigger 3-4c)
[TRIGGER 5] Safety Classification
  Triggered if: safety_filters module flag == True
  Model: detoxify + harmful instruction patterns
  Input: LLM response text

      │
      ▼ (all concurrent triggers complete)
[TRIGGER 6] Confidence Scoring
  No model inference. Pure arithmetic on collected signals.

      │
      ▼
[TRIGGER 7] Guardrail Decision
  No model inference. Policy threshold evaluation.

      │
      ▼ (if retry decision)
[TRIGGER 2 again] LLM Generation (retry attempt)
  All triggers repeat with modified context (stricter prompt / lower temp / RAG-augmented)
```

---

## 6. Confidence Scoring: Signal Integration Details

### 6.1 Signal Pipeline

Each AI component produces one or more signals that feed the confidence scoring engine. The mapping is precise:

| AI Component | Signal Produced | Contribution Weight |
|---|---|---|
| FAISS / Evidence Retrieval | `evidence_similarity` = avg top-1 cosine similarity across supported claims | 35% |
| Claim Verifier | `claim_verification_ratio` = (supported − contradicted) / total | 35% |
| Claim Extractor | `claim_density_penalty` = f(claim_count, response_word_count) | 10% |
| detoxify / harmful instruction | `safety_penalty` = −0.3 per flagged filter (capped at −1.0, normalized to 0–1) | 20% |

### 6.2 Neutral Default Substitution

When a signal is unavailable (component failed or module disabled):

| Missing Signal | Neutral Value | Rationale |
|---|---|---|
| `evidence_similarity` (no KB) | 0.5 | No evidence → no positive or negative signal; score unaffected |
| `claim_verification_ratio` (no claims) | 0.5 | No claims → cannot assess hallucination; treat as neutral |
| `claim_density_penalty` (no claims) | 1.0 (no penalty) | No claims → no density risk |
| `safety_penalty` (safety module disabled) | 1.0 (no penalty) | Safety disabled by operator; no penalty applied. UI shows "Safety filters inactive" |
| All signals unavailable | 50 (raw score) | System-level uncertainty; yields "Medium" label at default thresholds |

### 6.3 Score Stability Invariants

- The same claim with the same evidence must always produce the same `confidence_contribution`. This is guaranteed because: claim verification uses `temperature=0.0`, and cosine similarity is deterministic.
- Two requests with identical prompts, identical model, identical KB, and identical policy must produce identical confidence scores. This is the determinism invariant (enforced in the testing strategy via determinism test cases).

---

## 7. Model Integration Strategy

### 7.1 Model Selection and Versioning

| Component | Default Model | Pinned Version | Update Strategy |
|---|---|---|---|
| Claim extraction / verification | `mistral` (Ollama) or `gpt-4o-mini` (OpenAI) | Ollama model tag pinned in Dockerfile: `ollama pull mistral:7b-instruct-v0.2-q4_K_M` | Update via Ollama model pull + redeploy |
| Document / claim embedding | `all-MiniLM-L6-v2` | HuggingFace model hash pinned in config | Update via `sentence-transformers` package upgrade (evaluated against retrieval quality benchmark before deploy) |
| Safety classification | `detoxify` original model | `detoxify==1.5.2` pinned in `pyproject.toml` | Update only after regression testing against known harmful content test suite |

### 7.2 Model Loading Strategy

All models are loaded eagerly at application startup in `ApplicationContainer.initialize()`:

```python
async def initialize(self):
    # 1. Load embedding model (blocks startup; ~2s on CPU)
    self.embedding_adapter = SentenceTransformerAdapter(config.embedding_model)
    self.embedding_adapter.load()

    # 2. Load detoxify model (blocks startup; ~1s on CPU)
    self.safety_classifier = DetoxifyClassifier(config.detoxify_model)
    self.safety_classifier.load()

    # 3. Initialize database (create tables if not exist via Alembic check)
    await self.db_engine.connect()

    # 4. Load all READY FAISS indexes into memory cache
    for kb_id in await self.kb_repo.list_ready_kb_ids():
        self.vector_store.preload(kb_id)

    # 5. Start background indexing worker
    self.indexing_task = asyncio.create_task(
        kb_indexing_worker(self.indexing_queue)
    )

    # 6. Verify Ollama is reachable (warn but do not fail startup)
    try:
        await self.ollama_adapter.health_check()
    except LLMUnavailableError:
        log.warning("Ollama is not reachable at startup. Local model will be unavailable.")
```

### 7.3 Model Isolation

- LLM calls (Ollama) are fully isolated from the main Python process (separate process managed by Ollama).
- detoxify inference is dispatched to a `ProcessPoolExecutor` worker to avoid blocking the event loop during CPU-intensive classification.
- SentenceTransformer inference is similarly CPU-bound; dispatched to `ProcessPoolExecutor`.
- The `ProcessPoolExecutor` has `max_workers=2` (MVP). Each worker process loads its own copy of the embedding model and detoxify model into memory. At 2 workers, this adds ~600MB RSS overhead above the main process.

---

## 8. RAG Augmentation Pipeline (Fallback Strategy)

When the guardrail decision engine selects `rag_augmentation` as a fallback:

```
INPUT:  original prompt, kb_id
OUTPUT: augmented prompt (for retry)

Step 1: Embed the original prompt
  query_vector = EmbeddingAdapter.embed(original_prompt)

Step 2: Retrieve top-3 chunks from KB (fewer than claim evidence; prompt space is limited)
  evidence = FAISSStore.query(kb_id, query_vector, top_k=3)

Step 3: Format evidence block
  evidence_block = "\n".join([
      f"[Reference {i+1}] {e.chunk_text[:400]}"
      for i, e in enumerate(evidence)
  ])

Step 4: Construct augmented prompt
  augmented_prompt = (
      f"Answer the following question using ONLY the provided references. "
      f"If the references do not contain the answer, say so explicitly.\n\n"
      f"References:\n{evidence_block}\n\n"
      f"Question: {original_prompt}"
  )

Step 5: Update context.original_prompt with augmented_prompt
  context.fallback_strategy_applied = 'rag_augmentation'
  → Pipeline re-enters at LLM Generation with augmented_prompt

Expected effect: LLM generates a response grounded in retrieved evidence.
Verification: Claim verification in the retry will find the same evidence
  chunks via retrieval, increasing the probability of 'supported' verdicts.
```

---

## 9. Privacy Safeguards in AI Integration

### 9.1 Data Flow Boundaries

| Data | Sent to Local LLM | Sent to OpenAI | Stored in DB | Stored in Vector Store |
|---|---|---|---|---|
| Original prompt text | Yes | Yes (if selected) | No (hash + masked only) | No |
| LLM response text | As input to claim extractor | As input to claim extractor | Yes (final_response_text) | No |
| Claim text | As input to verifier | As input to verifier | Yes (claim_text column) | As embedding vector only |
| Document chunk text | No | No | Yes (chunk_text column) | As embedding vector only |
| OpenAI API key | No | Yes (in Authorization header) | No | No |

### 9.2 API Key Handling in AI Layer

The OpenAI API key travels through the system as follows:

1. Received in `X-Openai-Api-Key` HTTP header.
2. Stripped from the HTTP request by `ApiKeyStrippingMiddleware` and stored in `request.state.openai_api_key`.
3. Passed via `PipelineContext.openai_api_key` (a transient field, not serialized to JSON or DB).
4. Passed to `OpenAIAdapter.complete(api_key=...)` for the HTTP call.
5. The `openai` SDK uses it only in the `Authorization: Bearer ...` header.
6. After the request completes, the `PipelineContext` object is garbage collected. The key is never logged, never serialized, never written to any store.

Enforcement: The `ApiKeyStrippingMiddleware` logs the *presence* of the header (boolean) but not its *value*. A `structlog` processor at the logging layer strips any key matching `(api_key|api-key|authorization|bearer)` case-insensitively from all log records.

### 9.3 Prompt Privacy in AI Calls

The prompt is sent to the LLM provider (Ollama locally, or OpenAI via HTTPS). PII masking occurs *before* the claim extraction and claim verification LLM calls, using the `masked_prompt` from the validation stage. However, the *generation* call uses the original prompt (masking would alter the semantic meaning and degrade response quality). This is a documented trade-off: the original prompt is transmitted to the LLM provider but never persisted in the system's own storage.

For OpenAI: users are informed in the Privacy Notice that their prompt is sent to OpenAI for generation. OpenAI's own data retention policies apply.

### 9.4 Knowledge Base Privacy

- Documents uploaded to the KB are stored as local files and as text chunks in SQLite.
- Embeddings (vector representations) stored in FAISS contain no recoverable text. Vector embeddings are not reversible to their source text with available techniques.
- Documents are scoped to `session_id`. The FAISS query path includes a `session_id` ownership check to prevent cross-session KB access.
- Document files are stored in a flat directory (`upload_dir/{session_id}/{doc_uuid}_{filename}`). The `session_id` prefix provides filesystem-level namespacing.

---

## 10. Performance Constraints

### 10.1 LLM Token Budget

| Operation | Max Prompt Tokens | Max Output Tokens | Rationale |
|---|---|---|---|
| Primary generation | ~1200 (4000 chars ≈ 1000 tokens + system overhead) | 1024 | User prompt limit of 4000 chars + model instruction overhead |
| Claim extraction | Response text + instruction ≈ 1500 tokens | 512 | Claim list is compact JSON |
| Claim verification (per claim) | Claim + 5 evidence chunks × 300 chars ≈ 700 tokens | 256 | Verification is a classification task; short output |
| RAG augmented retry | 3 evidence chunks × 400 chars + prompt ≈ 1500 tokens | 1024 | Evidence block adds ~600 tokens to base prompt |

### 10.2 Embedding Throughput

- SentenceTransformers `all-MiniLM-L6-v2` on CPU: ~120 sentences/second (batch size 32).
- For indexing: a 10MB text file → ~20,000 words → ~2,000 chunks at 512 chars. Embedding time: ~16 seconds. Acceptable for background indexing.
- For per-claim retrieval: single claim embedding takes ~8ms (cold) or ~0ms (cache hit). 20 claims = ~160ms worst case (all cache misses).

### 10.3 FAISS Search Throughput

- `IndexFlatL2` with 50,000 vectors (384-dim): ~2ms per query on CPU (exact search).
- At 20 claims per request: 40ms total FAISS time. Well within budget.
- At 500,000 vectors: ~15ms per query. Switch to `IndexHNSWFlat` at this scale.

### 10.4 Detoxify Throughput

- `detoxify` on CPU: ~200ms per inference call for a 200-word response.
- This is dispatched concurrently with hallucination detection, so it does not add to sequential latency.
- For very long responses (1000+ words): detoxify may take 500ms+. A `truncate_to_tokens(max=512)` preprocessing step is applied before the detoxify call to cap latency.

---

## 11. Offline Inference Strategy

All AI inference in the MVP is designed to run without internet access (when using local models):

| Component | Offline Capable | Notes |
|---|---|---|
| Ollama + local model | Yes | Model weights downloaded once at deployment |
| SentenceTransformers | Yes | Model downloaded to HuggingFace cache at first use; then fully offline |
| detoxify | Yes | Model weights bundled with the package |
| FAISS | Yes | In-process, no network |
| OpenAI API | No | Requires internet. Only activated by user choice with their own key |

**First-run model download:** On first deployment, `ApplicationContainer.initialize()` triggers model downloads for SentenceTransformers and detoxify if not already cached. The Dockerfile pre-downloads model weights as a build step to eliminate cold-start delays:

```dockerfile
# In Dockerfile.backend, after pip install:
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('all-MiniLM-L6-v2')"
RUN python -c "from detoxify import Detoxify; Detoxify('original')"
```

The Ollama model must be pulled separately (it is too large for the Docker image):

```yaml
# docker-compose.yml
services:
  ollama:
    image: ollama/ollama
    volumes:
      - ollama_data:/root/.ollama
    command: serve
  ollama-model-puller:
    image: ollama/ollama
    depends_on: [ollama]
    volumes:
      - ollama_data:/root/.ollama
    command: pull mistral:7b-instruct-v0.2-q4_K_M
    restart: "no"
```

---

## 12. AI Integration Failure Matrix

| Failure | Detection | Fallback | User-Facing Behavior |
|---|---|---|---|
| Ollama unreachable | `httpx.ConnectError` on generation | Offer OpenAI; if OpenAI not configured, fail pipeline | "Local model is unavailable. Please switch to OpenAI or check the service." |
| Ollama returns empty response | `result.text.strip() == ""` | Invoke FallbackStrategyEngine | Retry with stricter prompt |
| Ollama generation timeout | `asyncio.TimeoutError` | Invoke FallbackStrategyEngine | "Request timed out. Retrying..." |
| OpenAI 401 Unauthorized | `openai.AuthenticationError` | No retry | "Invalid API key. Please verify your credentials." |
| OpenAI 429 Rate Limited | `openai.RateLimitError` | Retry ×2 with backoff | Transparent to user; if all retries fail: "Provider rate limited. Please try again shortly." |
| Claim extraction JSON parse failure | `json.JSONDecodeError` | Return empty claim list; continue | Pipeline continues; trace stage shows "Claim extraction parse error" |
| Embedding model failure | Exception from SentenceTransformer | Skip retrieval; mark all claims unsupported | Confidence score computed from safety signals only; trace notes embedding failure |
| FAISS index not found for KB | `FileNotFoundError` on index load | Return empty evidence; mark claims unsupported | UI note: "Knowledge base index not found. Please re-index your documents." |
| FAISS index corruption | Exception on `index.search` | Delete corrupt index file; mark KB as FAILED | User prompted to re-upload and re-index |
| detoxify model not loaded | `AttributeError` on inference | Skip safety filtering; log CRITICAL; set safety_penalty to 0 (neutral) | UI warning banner: "Safety filters were unavailable for this request" |
| Harmful instruction check exception | Any exception in regex engine | Skip check; log error | No user-visible change; error logged |
| Claim verifier LLM returns unexpected JSON | JSON parse failure | Mark claim as 'unverified' | Claim shown as "unverified" in analysis panel |
| All AI components fail simultaneously | Multiple exceptions | Block with PIPELINE_FAILURE | "The guardrail pipeline encountered a critical error. Request ID: {id}. Please try again." |
