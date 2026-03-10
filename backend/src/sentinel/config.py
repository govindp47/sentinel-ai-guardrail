"""Application configuration.

All runtime configuration is declared here via Pydantic Settings.
Environment variables override defaults.  No application logic lives in this
module — it is a pure declaration layer.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppConfig(BaseSettings):
    """Central configuration for the SentinelAI Guardrail service.

    All fields are sourced from environment variables (case-insensitive).
    A ``.env`` file in the working directory is loaded automatically when
    present.  Missing required fields without defaults raise a ``ValidationError``
    at startup rather than failing silently at runtime.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ------------------------------------------------------------------
    # Application
    # ------------------------------------------------------------------

    app_env: str = Field(
        default="development",
        description=(
            "Runtime environment. One of: development | staging | production. "
            "Controls log level defaults, debug behaviour, and CORS origins."
        ),
    )

    app_host: str = Field(
        default="0.0.0.0",  # nosec B104
        description="Host address the Uvicorn server binds to.",
    )

    app_port: int = Field(
        default=8000,
        description="TCP port the Uvicorn server listens on.",
    )

    app_workers: int = Field(
        default=1,
        description=(
            "Number of Uvicorn worker processes. "
            "Set to 1 for SQLite (no multi-process shared state). "
            "Increase for PostgreSQL deployments."
        ),
    )

    debug: bool = Field(
        default=False,
        description=(
            "Enable FastAPI debug mode (detailed tracebacks in HTTP responses). "
            "Never True in production."
        ),
    )

    log_level: str = Field(
        default="INFO",
        description="Logging level. One of: DEBUG | INFO | WARNING | ERROR | CRITICAL.",
    )

    log_format: str = Field(
        default="json",
        description=(
            "Log output format. One of: json | console. " "Use 'console' for local development."
        ),
    )

    # ------------------------------------------------------------------
    # CORS
    # ------------------------------------------------------------------

    cors_origins: list[str] = Field(
        default=["http://localhost:5173", "http://localhost:3000"],
        description=(
            "List of allowed CORS origins. "
            "The Vite dev server runs on :5173 by default. "
            "Expand for staging/production frontend URLs."
        ),
    )

    cors_allow_credentials: bool = Field(
        default=True,
        description="Whether to allow cookies/credentials in CORS requests.",
    )

    # ------------------------------------------------------------------
    # Database
    # ------------------------------------------------------------------

    database_url: str = Field(
        default="sqlite+aiosqlite:///./sentinel.db",
        description=(
            "SQLAlchemy async database URL. "
            "SQLite (default): sqlite+aiosqlite:///./sentinel.db. "
            "PostgreSQL: postgresql+asyncpg://user:pass@host:5432/dbname."
        ),
    )

    database_pool_size: int = Field(
        default=5,
        description=(
            "SQLAlchemy connection pool size. " "Ignored for SQLite (which uses a StaticPool)."
        ),
    )

    database_max_overflow: int = Field(
        default=10,
        description="Maximum connections above pool_size. Ignored for SQLite.",
    )

    database_echo: bool = Field(
        default=False,
        description="Emit all SQL statements to the logger. Enable only for debugging.",
    )

    # ------------------------------------------------------------------
    # Vector Store
    # ------------------------------------------------------------------

    vector_store_backend: str = Field(
        default="faiss",
        description="Vector store implementation. One of: faiss | chroma.",
    )

    faiss_index_dir: str = Field(
        default="./data/faiss_indexes",
        description="Directory where per-KB FAISS index files are persisted.",
    )

    chroma_host: str = Field(
        default="localhost",
        description="ChromaDB server host. Only used when vector_store_backend=chroma.",
    )

    chroma_port: int = Field(
        default=8001,
        description="ChromaDB server port. Only used when vector_store_backend=chroma.",
    )

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------

    embedding_model: str = Field(
        default="all-MiniLM-L6-v2",
        description=(
            "SentenceTransformers model name used for embedding document chunks and claims. "
            "Alternatives: BAAI/bge-small-en-v1.5 (higher quality, larger). "
            "Model files are downloaded to the HuggingFace cache on first use."
        ),
    )

    embedding_device: str = Field(
        default="cpu",
        description="Torch device for embedding inference. One of: cpu | cuda | mps.",
    )

    embedding_batch_size: int = Field(
        default=32,
        description="Batch size for embedding document chunks during KB indexing.",
    )

    # ------------------------------------------------------------------
    # Ollama (local LLM)
    # ------------------------------------------------------------------

    ollama_base_url: str = Field(
        default="http://localhost:11434",
        description="Base URL of the Ollama HTTP API.",
    )

    ollama_default_model: str = Field(
        default="mistral",
        description=(
            "Default Ollama model tag used when the caller does not specify a model. "
            "Must be pulled in Ollama before use: `ollama pull mistral`."
        ),
    )

    ollama_timeout: int = Field(
        default=120,
        description="HTTP timeout in seconds for Ollama inference requests.",
    )

    # ------------------------------------------------------------------
    # OpenAI
    # ------------------------------------------------------------------

    openai_default_model: str = Field(
        default="gpt-4o-mini",
        description=(
            "Default OpenAI model used when the caller selects the openai provider "
            "but does not specify a model. OpenAI API keys are supplied per-request "
            "via the X-Openai-Api-Key header, not stored server-side."
        ),
    )

    openai_timeout: int = Field(
        default=60,
        description="HTTP timeout in seconds for OpenAI API requests.",
    )

    # ------------------------------------------------------------------
    # Hallucination Detection
    # ------------------------------------------------------------------

    claim_extraction_model: str = Field(
        default="ollama/mistral",
        description=(
            "Model used for claim extraction from LLM responses. "
            "Format: provider/model-name. "
            "Supported providers: ollama, openai."
        ),
    )

    claim_verification_top_k: int = Field(
        default=5,
        description=(
            "Number of KB chunks retrieved per claim during hallucination verification. "
            "Higher values improve recall at the cost of verification latency."
        ),
    )

    # ------------------------------------------------------------------
    # Safety / Toxicity
    # ------------------------------------------------------------------

    detoxify_model: str = Field(
        default="original",
        description=(
            "Detoxify model variant. "
            "One of: original | unbiased | multilingual. "
            "'multilingual' supports non-English content but requires ~250MB download."
        ),
    )

    toxicity_threshold: float = Field(
        default=0.7,
        description=(
            "Detoxify toxicity score threshold [0.0, 1.0] above which a response is blocked. "
            "Higher values are more permissive."
        ),
    )

    hate_speech_threshold: float = Field(
        default=0.7,
        description=(
            "Detoxify identity_attack + threat combined score threshold [0.0, 1.0] "
            "above which a response is blocked."
        ),
    )

    # ------------------------------------------------------------------
    # Confidence Scoring
    # ------------------------------------------------------------------

    confidence_accept_threshold: float = Field(
        default=0.70,
        description=(
            "Normalised confidence score at or above which the guardrail decision is ACCEPT. "
            "Score range: [0.0, 1.0]."
        ),
    )

    confidence_warn_threshold: float = Field(
        default=0.40,
        description=(
            "Normalised confidence score at or above which the decision is WARN (below ACCEPT). "
            "Scores below this threshold trigger BLOCK or RETRY."
        ),
    )

    # ------------------------------------------------------------------
    # Chunking (KB indexing)
    # ------------------------------------------------------------------

    chunk_size: int = Field(
        default=512,
        description="Maximum token count per document chunk during KB indexing.",
    )

    chunk_overlap: int = Field(
        default=64,
        description=(
            "Token overlap between consecutive chunks. " "Preserves context at chunk boundaries."
        ),
    )

    # ------------------------------------------------------------------
    # File Storage
    # ------------------------------------------------------------------

    storage_backend: str = Field(
        default="local",
        description="File storage backend for uploaded KB documents. Currently: local.",
    )

    storage_local_dir: str = Field(
        default="./data/uploads",
        description="Local filesystem directory for uploaded document storage.",
    )

    max_upload_size_mb: int = Field(
        default=50,
        description="Maximum allowed file upload size in megabytes.",
    )

    # ------------------------------------------------------------------
    # Security
    # ------------------------------------------------------------------

    secret_key: str = Field(
        default="change-me-in-production-use-a-random-32-byte-hex-string",
        description=(
            "Secret key used for signing internal tokens. "
            "MUST be overridden in staging and production. "
            'Generate with: python -c "import secrets; print(secrets.token_hex(32))"'
        ),
    )

    api_key_header: str = Field(
        default="X-API-Key",
        description="HTTP header name used for server-to-server API key authentication.",
    )

    # ------------------------------------------------------------------
    # Rate Limiting
    # ------------------------------------------------------------------

    rate_limit_enabled: bool = Field(
        default=False,
        description="Enable per-IP rate limiting on the guardrail submit endpoint.",
    )

    rate_limit_requests_per_minute: int = Field(
        default=60,
        description="Maximum requests per minute per IP when rate limiting is enabled.",
    )

    # ------------------------------------------------------------------
    # Background Workers
    # ------------------------------------------------------------------

    kb_indexing_max_concurrency: int = Field(
        default=2,
        description="Maximum number of concurrent KB document indexing tasks.",
    )

    # ------------------------------------------------------------------
    # WebSocket
    # ------------------------------------------------------------------

    ws_heartbeat_interval: int = Field(
        default=30,
        description="WebSocket ping/heartbeat interval in seconds.",
    )

    ws_max_connections_per_request: int = Field(
        default=5,
        description="Maximum concurrent WebSocket connections per guardrail request_id.",
    )
