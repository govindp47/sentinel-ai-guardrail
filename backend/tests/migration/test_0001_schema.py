"""
Schema structure tests — verifies all 10 tables, their columns,
nullability, and server defaults after `alembic upgrade head`.
"""

from __future__ import annotations

import sqlite3

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _columns(conn: sqlite3.Connection, table: str) -> dict[str, sqlite3.Row]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    assert rows, f"Table '{table}' does not exist or has no columns"
    return {row["name"]: row for row in rows}


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# Table existence
# ---------------------------------------------------------------------------

EXPECTED_TABLES = [
    "sessions",
    "policy_snapshots",
    "kb_documents",
    "kb_chunks",
    "requests",
    "pipeline_traces",
    "request_claims",
    "claim_evidence",
    "safety_filter_results",
    "analytics_counters",
]


@pytest.mark.parametrize("table", EXPECTED_TABLES)
def test_table_exists(migrated_db: sqlite3.Connection, table: str) -> None:
    assert _table_exists(migrated_db, table), f"Table '{table}' is missing"


# ---------------------------------------------------------------------------
# sessions
# ---------------------------------------------------------------------------

def test_sessions_columns(migrated_db: sqlite3.Connection) -> None:
    cols = _columns(migrated_db, "sessions")
    assert "id" in cols
    assert "policy_snapshot_id" in cols
    assert "created_at" in cols
    assert "last_active_at" in cols


def test_sessions_nullability(migrated_db: sqlite3.Connection) -> None:
    cols = _columns(migrated_db, "sessions")
    assert cols["id"]["notnull"] == 1       # PRIMARY KEY — SQLite allows null check to vary
    assert cols["policy_snapshot_id"]["notnull"] == 0   # nullable
    assert cols["created_at"]["notnull"] == 1
    assert cols["last_active_at"]["notnull"] == 1


# ---------------------------------------------------------------------------
# policy_snapshots
# ---------------------------------------------------------------------------

def test_policy_snapshots_columns(migrated_db: sqlite3.Connection) -> None:
    cols = _columns(migrated_db, "policy_snapshots")
    expected = [
        "id", "session_id", "accept_threshold", "warn_threshold",
        "block_threshold", "max_retries", "restricted_categories",
        "allowed_topics", "fallback_priority", "module_flags", "created_at",
    ]
    for col in expected:
        assert col in cols, f"Column '{col}' missing from policy_snapshots"


def test_policy_snapshots_not_null(migrated_db: sqlite3.Connection) -> None:
    cols = _columns(migrated_db, "policy_snapshots")
    for col in ["session_id", "accept_threshold", "warn_threshold",
                "block_threshold", "max_retries", "restricted_categories",
                "allowed_topics", "fallback_priority", "module_flags", "created_at"]:
        assert cols[col]["notnull"] == 1, f"policy_snapshots.{col} should be NOT NULL"


def test_policy_snapshots_defaults(migrated_db: sqlite3.Connection) -> None:
    cols = _columns(migrated_db, "policy_snapshots")
    assert cols["accept_threshold"]["dflt_value"] == "70"
    assert cols["warn_threshold"]["dflt_value"] == "40"
    assert cols["block_threshold"]["dflt_value"] == "0"
    assert cols["max_retries"]["dflt_value"] == "2"


# ---------------------------------------------------------------------------
# kb_documents
# ---------------------------------------------------------------------------

def test_kb_documents_columns(migrated_db: sqlite3.Connection) -> None:
    cols = _columns(migrated_db, "kb_documents")
    expected = [
        "id", "session_id", "filename", "original_filename",
        "file_size_bytes", "mime_type", "storage_path", "status",
        "chunk_count", "chunk_size", "chunk_overlap",
        "error_message", "created_at", "indexed_at",
    ]
    for col in expected:
        assert col in cols, f"Column '{col}' missing from kb_documents"


def test_kb_documents_nullable(migrated_db: sqlite3.Connection) -> None:
    cols = _columns(migrated_db, "kb_documents")
    assert cols["error_message"]["notnull"] == 0
    assert cols["indexed_at"]["notnull"] == 0


def test_kb_documents_not_null(migrated_db: sqlite3.Connection) -> None:
    cols = _columns(migrated_db, "kb_documents")
    for col in ["session_id", "filename", "original_filename",
                "file_size_bytes", "mime_type", "storage_path",
                "status", "chunk_count", "created_at"]:
        assert cols[col]["notnull"] == 1, f"kb_documents.{col} should be NOT NULL"


def test_kb_documents_defaults(migrated_db: sqlite3.Connection) -> None:
    cols = _columns(migrated_db, "kb_documents")
    assert cols["chunk_count"]["dflt_value"] == "0"
    assert cols["chunk_size"]["dflt_value"] == "512"
    assert cols["chunk_overlap"]["dflt_value"] == "64"


# ---------------------------------------------------------------------------
# kb_chunks
# ---------------------------------------------------------------------------

def test_kb_chunks_columns(migrated_db: sqlite3.Connection) -> None:
    cols = _columns(migrated_db, "kb_chunks")
    expected = [
        "id", "document_id", "chunk_index", "chunk_text",
        "chunk_char_start", "chunk_char_end", "faiss_vector_id",
        "token_count", "created_at",
    ]
    for col in expected:
        assert col in cols, f"Column '{col}' missing from kb_chunks"


def test_kb_chunks_nullable(migrated_db: sqlite3.Connection) -> None:
    cols = _columns(migrated_db, "kb_chunks")
    assert cols["faiss_vector_id"]["notnull"] == 0
    assert cols["token_count"]["notnull"] == 0


# ---------------------------------------------------------------------------
# requests
# ---------------------------------------------------------------------------

def test_requests_columns(migrated_db: sqlite3.Connection) -> None:
    cols = _columns(migrated_db, "requests")
    expected = [
        "id", "session_id", "policy_snapshot_id", "kb_document_set_id",
        "replayed_from_request_id", "prompt_hash", "prompt_masked_text",
        "pii_detected", "pii_types_detected", "model_provider", "model_name",
        "status", "retry_count", "total_latency_ms", "tokens_in", "tokens_out",
        "risk_score", "confidence_score", "confidence_label",
        "confidence_signal_breakdown", "guardrail_decision", "decision_reason",
        "decision_triggered_rule", "final_response_text", "block_reason",
        "fallback_strategy_used", "created_at", "completed_at",
    ]
    for col in expected:
        assert col in cols, f"Column '{col}' missing from requests"


def test_requests_not_null(migrated_db: sqlite3.Connection) -> None:
    cols = _columns(migrated_db, "requests")
    for col in ["session_id", "policy_snapshot_id", "prompt_hash",
                "prompt_masked_text", "pii_detected", "pii_types_detected",
                "model_provider", "model_name", "status", "retry_count", "created_at"]:
        assert cols[col]["notnull"] == 1, f"requests.{col} should be NOT NULL"


def test_requests_nullable(migrated_db: sqlite3.Connection) -> None:
    cols = _columns(migrated_db, "requests")
    for col in ["kb_document_set_id", "replayed_from_request_id", "total_latency_ms",
                "tokens_in", "tokens_out", "risk_score", "confidence_score",
                "confidence_label", "confidence_signal_breakdown", "guardrail_decision",
                "decision_reason", "decision_triggered_rule", "final_response_text",
                "block_reason", "fallback_strategy_used", "completed_at"]:
        assert cols[col]["notnull"] == 0, f"requests.{col} should be nullable"


def test_requests_defaults(migrated_db: sqlite3.Connection) -> None:
    cols = _columns(migrated_db, "requests")
    assert cols["pii_detected"]["dflt_value"] == "0"
    assert cols["retry_count"]["dflt_value"] == "0"


# ---------------------------------------------------------------------------
# pipeline_traces
# ---------------------------------------------------------------------------

def test_pipeline_traces_columns(migrated_db: sqlite3.Connection) -> None:
    cols = _columns(migrated_db, "pipeline_traces")
    expected = [
        "id", "request_id", "attempt_number", "stage_order",
        "stage_name", "stage_status", "stage_latency_ms",
        "stage_metadata", "created_at",
    ]
    for col in expected:
        assert col in cols, f"Column '{col}' missing from pipeline_traces"


def test_pipeline_traces_defaults(migrated_db: sqlite3.Connection) -> None:
    cols = _columns(migrated_db, "pipeline_traces")
    assert cols["attempt_number"]["dflt_value"] == "1"


# ---------------------------------------------------------------------------
# request_claims
# ---------------------------------------------------------------------------

def test_request_claims_columns(migrated_db: sqlite3.Connection) -> None:
    cols = _columns(migrated_db, "request_claims")
    expected = [
        "id", "request_id", "attempt_number", "claim_index",
        "claim_text", "verification_status", "justification",
        "confidence_contribution", "created_at",
    ]
    for col in expected:
        assert col in cols, f"Column '{col}' missing from request_claims"


def test_request_claims_nullable(migrated_db: sqlite3.Connection) -> None:
    cols = _columns(migrated_db, "request_claims")
    assert cols["justification"]["notnull"] == 0
    assert cols["confidence_contribution"]["notnull"] == 0


# ---------------------------------------------------------------------------
# claim_evidence
# ---------------------------------------------------------------------------

def test_claim_evidence_columns(migrated_db: sqlite3.Connection) -> None:
    cols = _columns(migrated_db, "claim_evidence")
    expected = ["id", "claim_id", "kb_chunk_id", "relevance_score", "rank", "created_at"]
    for col in expected:
        assert col in cols, f"Column '{col}' missing from claim_evidence"


def test_claim_evidence_nullable(migrated_db: sqlite3.Connection) -> None:
    cols = _columns(migrated_db, "claim_evidence")
    assert cols["kb_chunk_id"]["notnull"] == 0


# ---------------------------------------------------------------------------
# safety_filter_results
# ---------------------------------------------------------------------------

def test_safety_filter_results_columns(migrated_db: sqlite3.Connection) -> None:
    cols = _columns(migrated_db, "safety_filter_results")
    expected = [
        "id", "request_id", "attempt_number",
        "filter_name", "result", "score", "created_at",
    ]
    for col in expected:
        assert col in cols, f"Column '{col}' missing from safety_filter_results"


# ---------------------------------------------------------------------------
# analytics_counters
# ---------------------------------------------------------------------------

def test_analytics_counters_columns(migrated_db: sqlite3.Connection) -> None:
    cols = _columns(migrated_db, "analytics_counters")
    expected = [
        "id", "session_id", "date_bucket", "model_provider", "model_name",
        "total_requests", "total_accepted", "total_warned", "total_retried",
        "total_blocked", "total_hallucinations_detected", "total_safety_triggered",
        "sum_confidence_score", "sum_latency_ms", "sum_tokens_in",
        "sum_tokens_out", "updated_at",
    ]
    for col in expected:
        assert col in cols, f"Column '{col}' missing from analytics_counters"


def test_analytics_counters_defaults(migrated_db: sqlite3.Connection) -> None:
    cols = _columns(migrated_db, "analytics_counters")
    for col in ["total_requests", "total_accepted", "total_warned", "total_retried",
                "total_blocked", "total_hallucinations_detected", "total_safety_triggered",
                "sum_confidence_score", "sum_latency_ms", "sum_tokens_in", "sum_tokens_out"]:
        assert cols[col]["dflt_value"] == "0", f"analytics_counters.{col} default should be 0"
