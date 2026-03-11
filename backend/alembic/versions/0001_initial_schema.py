"""initial schema

Creates all 10 application tables with complete column definitions,
CHECK constraints, UNIQUE constraints, foreign keys, and indexes.

Revision ID: 0001
Revises: None
Create Date: 2024-01-01 00:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# ---------------------------------------------------------------------------
# Revision identifiers
# ---------------------------------------------------------------------------
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ---------------------------------------------------------------------------
# Upgrade
# ---------------------------------------------------------------------------

def upgrade() -> None:
    # ------------------------------------------------------------------ #
    # NOTE: sessions.policy_snapshot_id creates a circular FK with        #
    # policy_snapshots.session_id. SQLite does not support ALTER TABLE     #
    # ADD CONSTRAINT, so this FK is intentionally omitted from the DDL    #
    # and enforced at the application layer. The column is present and     #
    # nullable; integrity is guaranteed by application code.               #
    # On PostgreSQL the FK can be added manually via:                      #
    #   ALTER TABLE sessions ADD CONSTRAINT fk_sessions_policy_snapshot_id #
    #   FOREIGN KEY (policy_snapshot_id)                                   #
    #   REFERENCES policy_snapshots(id) ON DELETE SET NULL;               #
    # ------------------------------------------------------------------ #

    # ------------------------------------------------------------------
    # 1. sessions
    # ------------------------------------------------------------------
    op.create_table(
        "sessions",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("policy_snapshot_id", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "last_active_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_sessions"),
    )
    op.create_index("idx_sessions_created_at", "sessions", ["created_at"])

    # ------------------------------------------------------------------
    # 2. policy_snapshots
    # ------------------------------------------------------------------
    op.create_table(
        "policy_snapshots",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column(
            "accept_threshold",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("70"),
        ),
        sa.Column(
            "warn_threshold",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("40"),
        ),
        sa.Column(
            "block_threshold",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "max_retries",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("2"),
        ),
        sa.Column(
            "restricted_categories",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "allowed_topics",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column(
            "fallback_priority",
            sa.Text(),
            nullable=False,
            server_default=sa.text(
                """'["retry_prompt","retry_lower_temp","rag_augmentation","alternate_model"]'"""
            ),
        ),
        sa.Column(
            "module_flags",
            sa.Text(),
            nullable=False,
            server_default=sa.text(
                """'{"injection_detection":true,"pii_detection":true,"policy_filter":true,"hallucination_detection":true,"safety_filters":true}'"""
            ),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_policy_snapshots"),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_policy_snapshots_session_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "accept_threshold BETWEEN 0 AND 100",
            name="ck_policy_accept_threshold",
        ),
        sa.CheckConstraint(
            "warn_threshold BETWEEN 0 AND 100",
            name="ck_policy_warn_threshold",
        ),
        sa.CheckConstraint(
            "block_threshold BETWEEN 0 AND 100",
            name="ck_policy_block_threshold",
        ),
        sa.CheckConstraint(
            "max_retries BETWEEN 0 AND 5",
            name="ck_policy_max_retries",
        ),
        sa.CheckConstraint(
            "block_threshold < warn_threshold",
            name="ck_policy_block_lt_warn",
        ),
        sa.CheckConstraint(
            "warn_threshold < accept_threshold",
            name="ck_policy_warn_lt_accept",
        ),
    )
    op.create_index(
        "idx_policy_snapshots_session",
        "policy_snapshots",
        ["session_id", sa.text("created_at DESC")],
    )

    # ------------------------------------------------------------------
    # 3. kb_documents
    # ------------------------------------------------------------------
    op.create_table(
        "kb_documents",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("filename", sa.Text(), nullable=False),
        sa.Column("original_filename", sa.Text(), nullable=False),
        sa.Column("file_size_bytes", sa.Integer(), nullable=False),
        sa.Column("mime_type", sa.Text(), nullable=False),
        sa.Column("storage_path", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "chunk_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "chunk_size",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("512"),
        ),
        sa.Column(
            "chunk_overlap",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("64"),
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("indexed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_kb_documents"),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_kb_documents_session_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("storage_path", name="uq_kb_documents_storage_path"),
        sa.CheckConstraint(
            "status IN ('pending','indexing','ready','failed')",
            name="ck_kb_documents_status",
        ),
    )
    op.create_index(
        "idx_kb_docs_session",
        "kb_documents",
        ["session_id", sa.text("created_at DESC")],
    )
    op.create_index("idx_kb_docs_status", "kb_documents", ["status"])

    # ------------------------------------------------------------------
    # 4. kb_chunks
    # ------------------------------------------------------------------
    op.create_table(
        "kb_chunks",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("document_id", sa.Text(), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("chunk_char_start", sa.Integer(), nullable=False),
        sa.Column("chunk_char_end", sa.Integer(), nullable=False),
        sa.Column("faiss_vector_id", sa.Integer(), nullable=True),
        sa.Column("token_count", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_kb_chunks"),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["kb_documents.id"],
            name="fk_kb_chunks_document_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "document_id", "chunk_index", name="uq_kb_chunks_document_chunk"
        ),
    )
    op.create_index(
        "idx_chunks_document", "kb_chunks", ["document_id", "chunk_index"]
    )
    op.create_index("idx_chunks_faiss_id", "kb_chunks", ["faiss_vector_id"])

    # ------------------------------------------------------------------
    # 5. analytics_counters
    # ------------------------------------------------------------------
    op.create_table(
        "analytics_counters",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("date_bucket", sa.Text(), nullable=False),
        sa.Column("model_provider", sa.Text(), nullable=False),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column(
            "total_requests",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "total_accepted",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "total_warned",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "total_retried",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "total_blocked",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "total_hallucinations_detected",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "total_safety_triggered",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "sum_confidence_score",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "sum_latency_ms",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "sum_tokens_in",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "sum_tokens_out",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_analytics_counters"),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_analytics_counters_session_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("total_requests >= 0", name="ck_analytics_total_requests"),
        sa.CheckConstraint("total_accepted >= 0", name="ck_analytics_total_accepted"),
        sa.CheckConstraint("total_warned >= 0", name="ck_analytics_total_warned"),
        sa.CheckConstraint("total_retried >= 0", name="ck_analytics_total_retried"),
        sa.CheckConstraint("total_blocked >= 0", name="ck_analytics_total_blocked"),
        sa.CheckConstraint(
            "total_hallucinations_detected >= 0",
            name="ck_analytics_total_hallucinations",
        ),
        sa.CheckConstraint(
            "total_safety_triggered >= 0",
            name="ck_analytics_total_safety",
        ),
    )
    op.create_index(
        "idx_analytics_key",
        "analytics_counters",
        ["session_id", "date_bucket", "model_provider", "model_name"],
        unique=True,
    )
    op.create_index(
        "idx_analytics_session",
        "analytics_counters",
        ["session_id", sa.text("date_bucket DESC")],
    )

    # ------------------------------------------------------------------
    # 6. requests
    # ------------------------------------------------------------------
    op.create_table(
        "requests",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("session_id", sa.Text(), nullable=False),
        sa.Column("policy_snapshot_id", sa.Text(), nullable=False),
        sa.Column("kb_document_set_id", sa.Text(), nullable=True),
        sa.Column("replayed_from_request_id", sa.Text(), nullable=True),
        sa.Column("prompt_hash", sa.Text(), nullable=False),
        sa.Column("prompt_masked_text", sa.Text(), nullable=False),
        sa.Column(
            "pii_detected",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "pii_types_detected",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("model_provider", sa.Text(), nullable=False),
        sa.Column("model_name", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'pending'"),
        ),
        sa.Column(
            "retry_count",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("total_latency_ms", sa.Integer(), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("risk_score", sa.Integer(), nullable=True),
        sa.Column("confidence_score", sa.Integer(), nullable=True),
        sa.Column("confidence_label", sa.Text(), nullable=True),
        sa.Column("confidence_signal_breakdown", sa.Text(), nullable=True),
        sa.Column("guardrail_decision", sa.Text(), nullable=True),
        sa.Column("decision_reason", sa.Text(), nullable=True),
        sa.Column("decision_triggered_rule", sa.Text(), nullable=True),
        sa.Column("final_response_text", sa.Text(), nullable=True),
        sa.Column("block_reason", sa.Text(), nullable=True),
        sa.Column("fallback_strategy_used", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id", name="pk_requests"),
        sa.ForeignKeyConstraint(
            ["session_id"],
            ["sessions.id"],
            name="fk_requests_session_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["policy_snapshot_id"],
            ["policy_snapshots.id"],
            name="fk_requests_policy_snapshot_id",
        ),
        sa.ForeignKeyConstraint(
            ["replayed_from_request_id"],
            ["requests.id"],
            name="fk_requests_replayed_from",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "pii_detected IN (0, 1)",
            name="ck_requests_pii_detected",
        ),
        sa.CheckConstraint(
            "model_provider IN ('ollama', 'openai')",
            name="ck_requests_model_provider",
        ),
        sa.CheckConstraint(
            "status IN ('pending','processing','completed','failed','blocked')",
            name="ck_requests_status",
        ),
        sa.CheckConstraint(
            "risk_score BETWEEN 0 AND 100",
            name="ck_requests_risk_score",
        ),
        sa.CheckConstraint(
            "confidence_score BETWEEN 0 AND 100",
            name="ck_requests_confidence_score",
        ),
        sa.CheckConstraint(
            "confidence_label IN ('high','medium','low')",
            name="ck_requests_confidence_label",
        ),
        sa.CheckConstraint(
            "guardrail_decision IN ('accept','accept_with_warning','retry_prompt',"
            "'retry_alternate_model','trigger_rag','block')",
            name="ck_requests_guardrail_decision",
        ),
    )
    op.create_index(
        "idx_requests_session",
        "requests",
        ["session_id", sa.text("created_at DESC")],
    )
    op.create_index("idx_requests_status", "requests", ["status"])
    op.create_index("idx_requests_decision", "requests", ["guardrail_decision"])
    op.create_index("idx_requests_confidence", "requests", ["confidence_score"])
    op.create_index(
        "idx_requests_model", "requests", ["model_provider", "model_name"]
    )
    op.create_index(
        "idx_requests_created", "requests", [sa.text("created_at DESC")]
    )
    op.create_index("idx_requests_prompt_hash", "requests", ["prompt_hash"])

    # ------------------------------------------------------------------
    # 7. pipeline_traces
    # ------------------------------------------------------------------
    op.create_table(
        "pipeline_traces",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column(
            "attempt_number",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("stage_order", sa.Integer(), nullable=False),
        sa.Column("stage_name", sa.Text(), nullable=False),
        sa.Column("stage_status", sa.Text(), nullable=False),
        sa.Column("stage_latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "stage_metadata",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_pipeline_traces"),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["requests.id"],
            name="fk_pipeline_traces_request_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "request_id",
            "attempt_number",
            "stage_name",
            name="uq_pipeline_traces_request_attempt_stage",
        ),
        sa.CheckConstraint(
            "stage_name IN ("
            "'prompt_received','prompt_validation','llm_generation',"
            "'claim_extraction','evidence_retrieval','claim_verification',"
            "'safety_filter_checks','confidence_score_calculation',"
            "'guardrail_decision','fallback_executed','final_response_returned'"
            ")",
            name="ck_pipeline_traces_stage_name",
        ),
        sa.CheckConstraint(
            "stage_status IN ('passed','flagged','failed','skipped','not_reached','in_progress')",
            name="ck_pipeline_traces_stage_status",
        ),
    )
    op.create_index(
        "idx_traces_request",
        "pipeline_traces",
        ["request_id", "attempt_number", "stage_order"],
    )

    # ------------------------------------------------------------------
    # 8. request_claims
    # ------------------------------------------------------------------
    op.create_table(
        "request_claims",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column(
            "attempt_number",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("claim_index", sa.Integer(), nullable=False),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("verification_status", sa.Text(), nullable=False),
        sa.Column("justification", sa.Text(), nullable=True),
        sa.Column("confidence_contribution", sa.Float(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_request_claims"),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["requests.id"],
            name="fk_request_claims_request_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "verification_status IN ('supported','unsupported','contradicted','unverified')",
            name="ck_request_claims_verification_status",
        ),
    )
    op.create_index(
        "idx_claims_request",
        "request_claims",
        ["request_id", "attempt_number", "claim_index"],
    )

    # ------------------------------------------------------------------
    # 9. claim_evidence
    # ------------------------------------------------------------------
    op.create_table(
        "claim_evidence",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("claim_id", sa.Text(), nullable=False),
        sa.Column("kb_chunk_id", sa.Text(), nullable=True),
        sa.Column("relevance_score", sa.Float(), nullable=False),
        sa.Column("rank", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_claim_evidence"),
        sa.ForeignKeyConstraint(
            ["claim_id"],
            ["request_claims.id"],
            name="fk_claim_evidence_claim_id",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["kb_chunk_id"],
            ["kb_chunks.id"],
            name="fk_claim_evidence_kb_chunk_id",
            ondelete="SET NULL",
        ),
        sa.CheckConstraint(
            "relevance_score BETWEEN 0.0 AND 1.0",
            name="ck_claim_evidence_relevance_score",
        ),
    )
    op.create_index(
        "idx_evidence_claim", "claim_evidence", ["claim_id", "rank"]
    )

    # ------------------------------------------------------------------
    # 10. safety_filter_results
    # ------------------------------------------------------------------
    op.create_table(
        "safety_filter_results",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column(
            "attempt_number",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("filter_name", sa.Text(), nullable=False),
        sa.Column("result", sa.Text(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id", name="pk_safety_filter_results"),
        sa.ForeignKeyConstraint(
            ["request_id"],
            ["requests.id"],
            name="fk_safety_filter_results_request_id",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "filter_name IN ("
            "'toxicity','hate_speech','harmful_instruction','severe_toxicity',"
            "'obscene','threat','insult','identity_attack','sexual_explicit'"
            ")",
            name="ck_safety_filter_results_filter_name",
        ),
        sa.CheckConstraint(
            "result IN ('clean','flagged')",
            name="ck_safety_filter_results_result",
        ),
        sa.CheckConstraint(
            "score BETWEEN 0.0 AND 1.0",
            name="ck_safety_filter_results_score",
        ),
    )
    op.create_index(
        "idx_safety_request",
        "safety_filter_results",
        ["request_id", "attempt_number"],
    )


# ---------------------------------------------------------------------------
# Downgrade — drop in reverse dependency order
# ---------------------------------------------------------------------------

def downgrade() -> None:
    op.drop_table("safety_filter_results")
    op.drop_table("claim_evidence")
    op.drop_table("request_claims")
    op.drop_table("pipeline_traces")
    op.drop_table("requests")
    op.drop_table("analytics_counters")
    op.drop_table("kb_chunks")
    op.drop_table("kb_documents")
    op.drop_table("policy_snapshots")
    op.drop_table("sessions")
