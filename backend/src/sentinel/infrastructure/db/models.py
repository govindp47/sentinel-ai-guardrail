"""
SQLAlchemy 2.x ORM models for all 10 SentinelAI Guardrail tables.

Column names, types, constraints, indexes, and relationships exactly mirror
Alembic migration 0001_initial_schema.py.

JSON columns use a JsonText TypeDecorator so the DB stores TEXT (matching the
migration's sa.Text() DDL) while Python sees native dict/list values.
"""

from __future__ import annotations

from datetime import datetime
import json

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
)
from sqlalchemy.types import TypeDecorator

# ---------------------------------------------------------------------------
# JsonText — stores JSON as TEXT in SQLite/PostgreSQL, returns Python objects
# ---------------------------------------------------------------------------


class JsonText(TypeDecorator):  # type: ignore[type-arg]
    """
    Stores JSON-serialisable values as TEXT in the database.
    Matches the migration's sa.Text() DDL so alembic check sees no type drift.
    Returns Python dict/list on read without any manual json.loads() calls.
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value: object, dialect: object) -> str | None:
        if value is None:
            return None
        return json.dumps(value, ensure_ascii=False)

    def process_result_value(self, value: str | None, dialect: object) -> object:
        if value is None:
            return None
        return json.loads(value)


# ---------------------------------------------------------------------------
# Declarative base
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    """Shared declarative base — target_metadata = Base.metadata in env.py."""

    pass


# ---------------------------------------------------------------------------
# 1. sessions
# ---------------------------------------------------------------------------


class SessionModel(Base):
    __tablename__ = "sessions"
    __table_args__ = (Index("idx_sessions_created_at", "created_at"),)

    id: Mapped[str] = mapped_column(Text(), primary_key=True)
    # Circular FK to policy_snapshots is intentionally omitted from the DDL
    # (matches the migration). Stored as a plain nullable TEXT column.
    # Application layer enforces integrity.
    policy_snapshot_id: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(), nullable=False, server_default=func.current_timestamp()
    )
    last_active_at: Mapped[datetime] = mapped_column(
        DateTime(), nullable=False, server_default=func.current_timestamp()
    )

    # Relationships
    policy_snapshots: Mapped[list[PolicySnapshotModel]] = relationship(
        "PolicySnapshotModel",
        back_populates="session",
        foreign_keys="PolicySnapshotModel.session_id",
        cascade="all, delete-orphan",
    )
    requests: Mapped[list[RequestModel]] = relationship(
        "RequestModel",
        back_populates="session",
        cascade="all, delete-orphan",
    )
    kb_documents: Mapped[list[KbDocumentModel]] = relationship(
        "KbDocumentModel",
        back_populates="session",
        cascade="all, delete-orphan",
    )
    analytics_counters: Mapped[list[AnalyticsCounterModel]] = relationship(
        "AnalyticsCounterModel",
        back_populates="session",
        cascade="all, delete-orphan",
    )


# ---------------------------------------------------------------------------
# 2. policy_snapshots
# ---------------------------------------------------------------------------


class PolicySnapshotModel(Base):
    __tablename__ = "policy_snapshots"
    __table_args__ = (
        CheckConstraint("accept_threshold BETWEEN 0 AND 100", name="ck_policy_accept_threshold"),
        CheckConstraint("warn_threshold BETWEEN 0 AND 100", name="ck_policy_warn_threshold"),
        CheckConstraint("block_threshold BETWEEN 0 AND 100", name="ck_policy_block_threshold"),
        CheckConstraint("max_retries BETWEEN 0 AND 5", name="ck_policy_max_retries"),
        CheckConstraint("block_threshold < warn_threshold", name="ck_policy_block_lt_warn"),
        CheckConstraint("warn_threshold < accept_threshold", name="ck_policy_warn_lt_accept"),
        Index("idx_policy_snapshots_session", "session_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(Text(), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        Text(), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    accept_threshold: Mapped[int] = mapped_column(Integer(), nullable=False, server_default="70")
    warn_threshold: Mapped[int] = mapped_column(Integer(), nullable=False, server_default="40")
    block_threshold: Mapped[int] = mapped_column(Integer(), nullable=False, server_default="0")
    max_retries: Mapped[int] = mapped_column(Integer(), nullable=False, server_default="2")
    restricted_categories: Mapped[object] = mapped_column(
        JsonText(), nullable=False, server_default="'[]'"
    )
    allowed_topics: Mapped[object] = mapped_column(
        JsonText(), nullable=False, server_default="'[]'"
    )
    fallback_priority: Mapped[object] = mapped_column(
        JsonText(),
        nullable=False,
        server_default=sa.text(
            """'["retry_prompt","retry_lower_temp","rag_augmentation","alternate_model"]'"""
        ),
    )
    module_flags: Mapped[object] = mapped_column(
        JsonText(),
        nullable=False,
        server_default=sa.text(
            """'{"injection_detection":true,"pii_detection":true,"policy_filter":true,"hallucination_detection":true,"safety_filters":true}'"""
        ),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(), nullable=False, server_default=func.current_timestamp()
    )

    # Relationships
    session: Mapped[SessionModel] = relationship(
        "SessionModel",
        back_populates="policy_snapshots",
        foreign_keys=[session_id],
    )
    requests: Mapped[list[RequestModel]] = relationship(
        "RequestModel",
        back_populates="policy_snapshot",
        foreign_keys="RequestModel.policy_snapshot_id",
    )


# ---------------------------------------------------------------------------
# 3. kb_documents
# ---------------------------------------------------------------------------


class KbDocumentModel(Base):
    __tablename__ = "kb_documents"
    __table_args__ = (
        UniqueConstraint("storage_path", name="uq_kb_documents_storage_path"),
        CheckConstraint(
            "status IN ('pending','indexing','ready','failed')",
            name="ck_kb_documents_status",
        ),
        Index("idx_kb_docs_session", "session_id", "created_at"),
        Index("idx_kb_docs_status", "status"),
    )

    id: Mapped[str] = mapped_column(Text(), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        Text(), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(Text(), nullable=False)
    original_filename: Mapped[str] = mapped_column(Text(), nullable=False)
    file_size_bytes: Mapped[int] = mapped_column(Integer(), nullable=False)
    mime_type: Mapped[str] = mapped_column(Text(), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text(), nullable=False)
    status: Mapped[str] = mapped_column(Text(), nullable=False, server_default="'pending'")
    chunk_count: Mapped[int] = mapped_column(Integer(), nullable=False, server_default="0")
    chunk_size: Mapped[int] = mapped_column(Integer(), nullable=False, server_default="512")
    chunk_overlap: Mapped[int] = mapped_column(Integer(), nullable=False, server_default="64")
    error_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(), nullable=False, server_default=func.current_timestamp()
    )
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)

    # Relationships
    session: Mapped[SessionModel] = relationship("SessionModel", back_populates="kb_documents")
    chunks: Mapped[list[KbChunkModel]] = relationship(
        "KbChunkModel",
        back_populates="document",
        cascade="all, delete-orphan",
    )


# ---------------------------------------------------------------------------
# 4. kb_chunks
# ---------------------------------------------------------------------------


class KbChunkModel(Base):
    __tablename__ = "kb_chunks"
    __table_args__ = (
        UniqueConstraint("document_id", "chunk_index", name="uq_kb_chunks_document_chunk"),
        Index("idx_chunks_document", "document_id", "chunk_index"),
        Index("idx_chunks_faiss_id", "faiss_vector_id"),
    )

    id: Mapped[str] = mapped_column(Text(), primary_key=True)
    document_id: Mapped[str] = mapped_column(
        Text(), ForeignKey("kb_documents.id", ondelete="CASCADE"), nullable=False
    )
    chunk_index: Mapped[int] = mapped_column(Integer(), nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text(), nullable=False)
    chunk_char_start: Mapped[int] = mapped_column(Integer(), nullable=False)
    chunk_char_end: Mapped[int] = mapped_column(Integer(), nullable=False)
    faiss_vector_id: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    token_count: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(), nullable=False, server_default=func.current_timestamp()
    )

    # Relationships
    document: Mapped[KbDocumentModel] = relationship("KbDocumentModel", back_populates="chunks")
    evidence_links: Mapped[list[ClaimEvidenceModel]] = relationship(
        "ClaimEvidenceModel",
        back_populates="kb_chunk",
    )


# ---------------------------------------------------------------------------
# 5. analytics_counters
# ---------------------------------------------------------------------------


class AnalyticsCounterModel(Base):
    __tablename__ = "analytics_counters"
    __table_args__ = (
        # Unique index (not UniqueConstraint) — matches op.create_index(..., unique=True)
        Index(
            "idx_analytics_key",
            "session_id",
            "date_bucket",
            "model_provider",
            "model_name",
            unique=True,
        ),
        Index("idx_analytics_session", "session_id", "date_bucket"),
        CheckConstraint("total_requests >= 0", name="ck_analytics_total_requests"),
        CheckConstraint("total_accepted >= 0", name="ck_analytics_total_accepted"),
        CheckConstraint("total_warned >= 0", name="ck_analytics_total_warned"),
        CheckConstraint("total_retried >= 0", name="ck_analytics_total_retried"),
        CheckConstraint("total_blocked >= 0", name="ck_analytics_total_blocked"),
        CheckConstraint(
            "total_hallucinations_detected >= 0", name="ck_analytics_total_hallucinations"
        ),
        CheckConstraint("total_safety_triggered >= 0", name="ck_analytics_total_safety"),
    )

    id: Mapped[str] = mapped_column(Text(), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        Text(), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    date_bucket: Mapped[str] = mapped_column(Text(), nullable=False)
    model_provider: Mapped[str] = mapped_column(Text(), nullable=False)
    model_name: Mapped[str] = mapped_column(Text(), nullable=False)
    total_requests: Mapped[int] = mapped_column(Integer(), nullable=False, server_default="0")
    total_accepted: Mapped[int] = mapped_column(Integer(), nullable=False, server_default="0")
    total_warned: Mapped[int] = mapped_column(Integer(), nullable=False, server_default="0")
    total_retried: Mapped[int] = mapped_column(Integer(), nullable=False, server_default="0")
    total_blocked: Mapped[int] = mapped_column(Integer(), nullable=False, server_default="0")
    total_hallucinations_detected: Mapped[int] = mapped_column(
        Integer(), nullable=False, server_default="0"
    )
    total_safety_triggered: Mapped[int] = mapped_column(
        Integer(), nullable=False, server_default="0"
    )
    sum_confidence_score: Mapped[int] = mapped_column(Integer(), nullable=False, server_default="0")
    sum_latency_ms: Mapped[int] = mapped_column(BigInteger(), nullable=False, server_default="0")
    sum_tokens_in: Mapped[int] = mapped_column(BigInteger(), nullable=False, server_default="0")
    sum_tokens_out: Mapped[int] = mapped_column(BigInteger(), nullable=False, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(), nullable=False, server_default=func.current_timestamp()
    )

    # Relationships
    session: Mapped[SessionModel] = relationship(
        "SessionModel", back_populates="analytics_counters"
    )


# ---------------------------------------------------------------------------
# 6. requests
# ---------------------------------------------------------------------------


class RequestModel(Base):
    __tablename__ = "requests"
    __table_args__ = (
        CheckConstraint("pii_detected IN (0, 1)", name="ck_requests_pii_detected"),
        CheckConstraint(
            "model_provider IN ('ollama', 'openai')", name="ck_requests_model_provider"
        ),
        CheckConstraint(
            "status IN ('pending','processing','completed','failed','blocked')",
            name="ck_requests_status",
        ),
        CheckConstraint("risk_score BETWEEN 0 AND 100", name="ck_requests_risk_score"),
        CheckConstraint("confidence_score BETWEEN 0 AND 100", name="ck_requests_confidence_score"),
        CheckConstraint(
            "confidence_label IN ('high','medium','low')",
            name="ck_requests_confidence_label",
        ),
        CheckConstraint(
            "guardrail_decision IN ('accept','accept_with_warning','retry_prompt',"
            "'retry_alternate_model','trigger_rag','block')",
            name="ck_requests_guardrail_decision",
        ),
        Index("idx_requests_session", "session_id", "created_at"),
        Index("idx_requests_status", "status"),
        Index("idx_requests_decision", "guardrail_decision"),
        Index("idx_requests_confidence", "confidence_score"),
        Index("idx_requests_model", "model_provider", "model_name"),
        Index("idx_requests_created", "created_at"),
        Index("idx_requests_prompt_hash", "prompt_hash"),
    )

    id: Mapped[str] = mapped_column(Text(), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        Text(), ForeignKey("sessions.id", ondelete="CASCADE"), nullable=False
    )
    policy_snapshot_id: Mapped[str] = mapped_column(
        Text(), ForeignKey("policy_snapshots.id"), nullable=False
    )
    kb_document_set_id: Mapped[str | None] = mapped_column(Text(), nullable=True)
    replayed_from_request_id: Mapped[str | None] = mapped_column(
        Text(), ForeignKey("requests.id", ondelete="SET NULL"), nullable=True
    )
    prompt_hash: Mapped[str] = mapped_column(Text(), nullable=False)
    prompt_masked_text: Mapped[str] = mapped_column(Text(), nullable=False)
    pii_detected: Mapped[int] = mapped_column(Integer(), nullable=False, server_default="0")
    pii_types_detected: Mapped[object] = mapped_column(
        JsonText(), nullable=False, server_default="'[]'"
    )
    model_provider: Mapped[str] = mapped_column(Text(), nullable=False)
    model_name: Mapped[str] = mapped_column(Text(), nullable=False)
    status: Mapped[str] = mapped_column(Text(), nullable=False, server_default="'pending'")
    retry_count: Mapped[int] = mapped_column(Integer(), nullable=False, server_default="0")
    total_latency_ms: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    tokens_in: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    tokens_out: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    risk_score: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    confidence_score: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    confidence_label: Mapped[str | None] = mapped_column(Text(), nullable=True)
    confidence_signal_breakdown: Mapped[object | None] = mapped_column(JsonText(), nullable=True)
    guardrail_decision: Mapped[str | None] = mapped_column(Text(), nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    decision_triggered_rule: Mapped[str | None] = mapped_column(Text(), nullable=True)
    final_response_text: Mapped[str | None] = mapped_column(Text(), nullable=True)
    block_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)
    fallback_strategy_used: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(), nullable=False, server_default=func.current_timestamp()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(), nullable=True)

    # Relationships
    session: Mapped[SessionModel] = relationship("SessionModel", back_populates="requests")
    policy_snapshot: Mapped[PolicySnapshotModel] = relationship(
        "PolicySnapshotModel",
        back_populates="requests",
        foreign_keys=[policy_snapshot_id],
    )
    replayed_from: Mapped[RequestModel | None] = relationship(
        "RequestModel",
        remote_side="RequestModel.id",
        foreign_keys=[replayed_from_request_id],
        uselist=False,
    )
    pipeline_traces: Mapped[list[PipelineTraceModel]] = relationship(
        "PipelineTraceModel",
        back_populates="request",
        cascade="all, delete-orphan",
    )
    claims: Mapped[list[RequestClaimModel]] = relationship(
        "RequestClaimModel",
        back_populates="request",
        cascade="all, delete-orphan",
    )
    safety_filter_results: Mapped[list[SafetyFilterResultModel]] = relationship(
        "SafetyFilterResultModel",
        back_populates="request",
        cascade="all, delete-orphan",
    )


# ---------------------------------------------------------------------------
# 7. pipeline_traces
# ---------------------------------------------------------------------------


class PipelineTraceModel(Base):
    __tablename__ = "pipeline_traces"
    __table_args__ = (
        UniqueConstraint(
            "request_id",
            "attempt_number",
            "stage_name",
            name="uq_pipeline_traces_request_attempt_stage",
        ),
        CheckConstraint(
            "stage_name IN ("
            "'prompt_received','prompt_validation','llm_generation',"
            "'claim_extraction','evidence_retrieval','claim_verification',"
            "'safety_filter_checks','confidence_score_calculation',"
            "'guardrail_decision','fallback_executed','final_response_returned'"
            ")",
            name="ck_pipeline_traces_stage_name",
        ),
        CheckConstraint(
            "stage_status IN ('passed','flagged','failed','skipped','not_reached','in_progress')",
            name="ck_pipeline_traces_stage_status",
        ),
        Index("idx_traces_request", "request_id", "attempt_number", "stage_order"),
    )

    id: Mapped[str] = mapped_column(Text(), primary_key=True)
    request_id: Mapped[str] = mapped_column(
        Text(), ForeignKey("requests.id", ondelete="CASCADE"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer(), nullable=False, server_default="1")
    stage_order: Mapped[int] = mapped_column(Integer(), nullable=False)
    stage_name: Mapped[str] = mapped_column(Text(), nullable=False)
    stage_status: Mapped[str] = mapped_column(Text(), nullable=False)
    stage_latency_ms: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    stage_metadata: Mapped[object] = mapped_column(
        JsonText(), nullable=False, server_default="'{}'"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(), nullable=False, server_default=func.current_timestamp()
    )

    # Relationships
    request: Mapped[RequestModel] = relationship("RequestModel", back_populates="pipeline_traces")


# ---------------------------------------------------------------------------
# 8. request_claims
# ---------------------------------------------------------------------------


class RequestClaimModel(Base):
    __tablename__ = "request_claims"
    __table_args__ = (
        CheckConstraint(
            "verification_status IN ('supported','unsupported','contradicted','unverified')",
            name="ck_request_claims_verification_status",
        ),
        Index("idx_claims_request", "request_id", "attempt_number", "claim_index"),
    )

    id: Mapped[str] = mapped_column(Text(), primary_key=True)
    request_id: Mapped[str] = mapped_column(
        Text(), ForeignKey("requests.id", ondelete="CASCADE"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer(), nullable=False, server_default="1")
    claim_index: Mapped[int] = mapped_column(Integer(), nullable=False)
    claim_text: Mapped[str] = mapped_column(Text(), nullable=False)
    verification_status: Mapped[str] = mapped_column(Text(), nullable=False)
    justification: Mapped[str | None] = mapped_column(Text(), nullable=True)
    confidence_contribution: Mapped[float | None] = mapped_column(Float(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(), nullable=False, server_default=func.current_timestamp()
    )

    # Relationships
    request: Mapped[RequestModel] = relationship("RequestModel", back_populates="claims")
    evidence: Mapped[list[ClaimEvidenceModel]] = relationship(
        "ClaimEvidenceModel",
        back_populates="claim",
        cascade="all, delete-orphan",
    )


# ---------------------------------------------------------------------------
# 9. claim_evidence
# ---------------------------------------------------------------------------


class ClaimEvidenceModel(Base):
    __tablename__ = "claim_evidence"
    __table_args__ = (
        CheckConstraint(
            "relevance_score BETWEEN 0.0 AND 1.0",
            name="ck_claim_evidence_relevance_score",
        ),
        Index("idx_evidence_claim", "claim_id", "rank"),
    )

    id: Mapped[str] = mapped_column(Text(), primary_key=True)
    claim_id: Mapped[str] = mapped_column(
        Text(), ForeignKey("request_claims.id", ondelete="CASCADE"), nullable=False
    )
    kb_chunk_id: Mapped[str | None] = mapped_column(
        Text(), ForeignKey("kb_chunks.id", ondelete="SET NULL"), nullable=True
    )
    relevance_score: Mapped[float] = mapped_column(Float(), nullable=False)
    rank: Mapped[int] = mapped_column(Integer(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(), nullable=False, server_default=func.current_timestamp()
    )

    # Relationships
    claim: Mapped[RequestClaimModel] = relationship("RequestClaimModel", back_populates="evidence")
    kb_chunk: Mapped[KbChunkModel | None] = relationship(
        "KbChunkModel", back_populates="evidence_links"
    )


# ---------------------------------------------------------------------------
# 10. safety_filter_results
# ---------------------------------------------------------------------------


class SafetyFilterResultModel(Base):
    __tablename__ = "safety_filter_results"
    __table_args__ = (
        CheckConstraint(
            "filter_name IN ("
            "'toxicity','hate_speech','harmful_instruction','severe_toxicity',"
            "'obscene','threat','insult','identity_attack','sexual_explicit'"
            ")",
            name="ck_safety_filter_results_filter_name",
        ),
        CheckConstraint("result IN ('clean','flagged')", name="ck_safety_filter_results_result"),
        CheckConstraint("score BETWEEN 0.0 AND 1.0", name="ck_safety_filter_results_score"),
        Index("idx_safety_request", "request_id", "attempt_number"),
    )

    id: Mapped[str] = mapped_column(Text(), primary_key=True)
    request_id: Mapped[str] = mapped_column(
        Text(), ForeignKey("requests.id", ondelete="CASCADE"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer(), nullable=False, server_default="1")
    filter_name: Mapped[str] = mapped_column(Text(), nullable=False)
    result: Mapped[str] = mapped_column(Text(), nullable=False)
    score: Mapped[float] = mapped_column(Float(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(), nullable=False, server_default=func.current_timestamp()
    )

    # Relationships
    request: Mapped[RequestModel] = relationship(
        "RequestModel", back_populates="safety_filter_results"
    )
