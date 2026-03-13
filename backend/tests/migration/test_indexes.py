"""
Index existence tests — verifies all named indexes from the schema document
exist in sqlite_master after `alembic upgrade head`.
"""

from __future__ import annotations

import sqlite3

import pytest

# All indexes from 03_DATABASE_SCHEMA.md section 9 full DDL.
# Unique indexes created via op.create_index(..., unique=True) also appear here.
EXPECTED_INDEXES = [
    "idx_sessions_created_at",
    "idx_policy_snapshots_session",
    "idx_kb_docs_session",
    "idx_kb_docs_status",
    "idx_chunks_document",
    "idx_chunks_faiss_id",
    "idx_requests_session",
    "idx_requests_status",
    "idx_requests_decision",
    "idx_requests_confidence",
    "idx_requests_model",
    "idx_requests_created",
    "idx_requests_prompt_hash",
    "idx_traces_request",
    "idx_claims_request",
    "idx_evidence_claim",
    "idx_safety_request",
    "idx_analytics_key",
    "idx_analytics_session",
]


def _all_index_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index'"
    ).fetchall()
    return {row[0] for row in rows}


@pytest.mark.parametrize("index_name", EXPECTED_INDEXES)
def test_index_exists(migrated_db: sqlite3.Connection, index_name: str) -> None:
    all_indexes = _all_index_names(migrated_db)
    assert index_name in all_indexes, (
        f"Index '{index_name}' is missing. Found: {sorted(all_indexes)}"
    )


def test_no_unexpected_index_loss(migrated_db: sqlite3.Connection) -> None:
    """All expected indexes are present — count check as a guard."""
    all_indexes = _all_index_names(migrated_db)
    missing = set(EXPECTED_INDEXES) - all_indexes
    assert not missing, f"Missing indexes after upgrade: {missing}"
