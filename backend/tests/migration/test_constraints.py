"""
Constraint enforcement tests — verifies CHECK constraints, FK constraints,
and CASCADE behaviour by attempting violating inserts/deletes.
"""

from __future__ import annotations

import sqlite3
import uuid

import pytest


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------

def _uid() -> str:
    return str(uuid.uuid4())


def _insert_session(conn: sqlite3.Connection) -> str:
    sid = _uid()
    conn.execute("INSERT INTO sessions (id) VALUES (?)", (sid,))
    conn.commit()
    return sid


def _insert_policy(conn: sqlite3.Connection, session_id: str) -> str:
    pid = _uid()
    conn.execute(
        "INSERT INTO policy_snapshots (id, session_id) VALUES (?, ?)",
        (pid, session_id),
    )
    conn.commit()
    return pid


def _insert_request(conn: sqlite3.Connection, session_id: str, policy_id: str) -> str:
    rid = _uid()
    conn.execute(
        """INSERT INTO requests
           (id, session_id, policy_snapshot_id, prompt_hash, prompt_masked_text,
            model_provider, model_name)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (rid, session_id, policy_id, "hash", "masked", "ollama", "mistral"),
    )
    conn.commit()
    return rid


def _insert_claim(conn: sqlite3.Connection, request_id: str) -> str:
    cid = _uid()
    conn.execute(
        """INSERT INTO request_claims
           (id, request_id, claim_index, claim_text, verification_status)
           VALUES (?, ?, ?, ?, ?)""",
        (cid, request_id, 0, "Some claim.", "supported"),
    )
    conn.commit()
    return cid


# ---------------------------------------------------------------------------
# policy_snapshots CHECK constraints
# ---------------------------------------------------------------------------

class TestPolicySnapshotConstraints:

    def test_block_gte_warn_rejected(self, fresh_db: sqlite3.Connection) -> None:
        """block_threshold must be < warn_threshold."""
        sid = _insert_session(fresh_db)
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                """INSERT INTO policy_snapshots
                   (id, session_id, block_threshold, warn_threshold, accept_threshold)
                   VALUES (?, ?, ?, ?, ?)""",
                (_uid(), sid, 50, 40, 80),  # block(50) >= warn(40) — invalid
            )
            fresh_db.commit()

    def test_warn_gte_accept_rejected(self, fresh_db: sqlite3.Connection) -> None:
        """warn_threshold must be < accept_threshold."""
        sid = _insert_session(fresh_db)
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                """INSERT INTO policy_snapshots
                   (id, session_id, block_threshold, warn_threshold, accept_threshold)
                   VALUES (?, ?, ?, ?, ?)""",
                (_uid(), sid, 10, 80, 70),  # warn(80) >= accept(70) — invalid
            )
            fresh_db.commit()

    def test_accept_threshold_out_of_range(self, fresh_db: sqlite3.Connection) -> None:
        sid = _insert_session(fresh_db)
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                """INSERT INTO policy_snapshots
                   (id, session_id, block_threshold, warn_threshold, accept_threshold)
                   VALUES (?, ?, ?, ?, ?)""",
                (_uid(), sid, 0, 40, 150),  # accept > 100
            )
            fresh_db.commit()

    def test_max_retries_out_of_range(self, fresh_db: sqlite3.Connection) -> None:
        sid = _insert_session(fresh_db)
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                """INSERT INTO policy_snapshots
                   (id, session_id, block_threshold, warn_threshold, accept_threshold, max_retries)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (_uid(), sid, 0, 40, 70, 10),  # max_retries > 5
            )
            fresh_db.commit()

    def test_valid_policy_accepted(self, fresh_db: sqlite3.Connection) -> None:
        sid = _insert_session(fresh_db)
        pid = _uid()
        fresh_db.execute(
            """INSERT INTO policy_snapshots
               (id, session_id, block_threshold, warn_threshold, accept_threshold)
               VALUES (?, ?, ?, ?, ?)""",
            (pid, sid, 10, 40, 70),
        )
        fresh_db.commit()
        row = fresh_db.execute(
            "SELECT id FROM policy_snapshots WHERE id = ?", (pid,)
        ).fetchone()
        assert row is not None


# ---------------------------------------------------------------------------
# requests CHECK constraints
# ---------------------------------------------------------------------------

class TestRequestConstraints:

    def test_invalid_model_provider_rejected(self, fresh_db: sqlite3.Connection) -> None:
        sid = _insert_session(fresh_db)
        pid = _insert_policy(fresh_db, sid)
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                """INSERT INTO requests
                   (id, session_id, policy_snapshot_id, prompt_hash,
                    prompt_masked_text, model_provider, model_name)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (_uid(), sid, pid, "h", "m", "anthropic", "claude"),
            )
            fresh_db.commit()

    def test_invalid_status_rejected(self, fresh_db: sqlite3.Connection) -> None:
        sid = _insert_session(fresh_db)
        pid = _insert_policy(fresh_db, sid)
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                """INSERT INTO requests
                   (id, session_id, policy_snapshot_id, prompt_hash,
                    prompt_masked_text, model_provider, model_name, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (_uid(), sid, pid, "h", "m", "ollama", "mistral", "unknown"),
            )
            fresh_db.commit()

    def test_invalid_confidence_label_rejected(self, fresh_db: sqlite3.Connection) -> None:
        sid = _insert_session(fresh_db)
        pid = _insert_policy(fresh_db, sid)
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                """INSERT INTO requests
                   (id, session_id, policy_snapshot_id, prompt_hash, prompt_masked_text,
                    model_provider, model_name, confidence_label)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (_uid(), sid, pid, "h", "m", "ollama", "mistral", "super_high"),
            )
            fresh_db.commit()

    def test_risk_score_out_of_range(self, fresh_db: sqlite3.Connection) -> None:
        sid = _insert_session(fresh_db)
        pid = _insert_policy(fresh_db, sid)
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                """INSERT INTO requests
                   (id, session_id, policy_snapshot_id, prompt_hash, prompt_masked_text,
                    model_provider, model_name, risk_score)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (_uid(), sid, pid, "h", "m", "ollama", "mistral", 150),
            )
            fresh_db.commit()

    def test_pii_detected_invalid_value(self, fresh_db: sqlite3.Connection) -> None:
        sid = _insert_session(fresh_db)
        pid = _insert_policy(fresh_db, sid)
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                """INSERT INTO requests
                   (id, session_id, policy_snapshot_id, prompt_hash, prompt_masked_text,
                    model_provider, model_name, pii_detected)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (_uid(), sid, pid, "h", "m", "ollama", "mistral", 2),
            )
            fresh_db.commit()


# ---------------------------------------------------------------------------
# FK constraints
# ---------------------------------------------------------------------------

class TestForeignKeyConstraints:

    def test_orphan_kb_document_rejected(self, fresh_db: sqlite3.Connection) -> None:
        """kb_documents.session_id must reference a valid session."""
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                """INSERT INTO kb_documents
                   (id, session_id, filename, original_filename,
                    file_size_bytes, mime_type, storage_path)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (_uid(), "nonexistent-session", "f.pdf", "f.pdf",
                 1024, "application/pdf", f"/tmp/{_uid()}.pdf"),
            )
            fresh_db.commit()

    def test_orphan_request_rejected(self, fresh_db: sqlite3.Connection) -> None:
        """requests.session_id must reference a valid session."""
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                """INSERT INTO requests
                   (id, session_id, policy_snapshot_id, prompt_hash,
                    prompt_masked_text, model_provider, model_name)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (_uid(), "ghost-session", _uid(), "h", "m", "ollama", "mistral"),
            )
            fresh_db.commit()

    def test_orphan_pipeline_trace_rejected(self, fresh_db: sqlite3.Connection) -> None:
        """pipeline_traces.request_id must reference a valid request."""
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                """INSERT INTO pipeline_traces
                   (id, request_id, stage_order, stage_name, stage_status)
                   VALUES (?, ?, ?, ?, ?)""",
                (_uid(), "nonexistent-request", 1, "prompt_received", "passed"),
            )
            fresh_db.commit()

    def test_orphan_safety_result_rejected(self, fresh_db: sqlite3.Connection) -> None:
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                """INSERT INTO safety_filter_results
                   (id, request_id, filter_name, result, score)
                   VALUES (?, ?, ?, ?, ?)""",
                (_uid(), "nonexistent-request", "toxicity", "clean", 0.01),
            )
            fresh_db.commit()


# ---------------------------------------------------------------------------
# CASCADE DELETE behaviour
# ---------------------------------------------------------------------------

class TestCascadeDelete:

    def test_session_delete_cascades_to_policy_snapshots(
        self, fresh_db: sqlite3.Connection
    ) -> None:
        sid = _insert_session(fresh_db)
        pid = _insert_policy(fresh_db, sid)
        fresh_db.execute("DELETE FROM sessions WHERE id = ?", (sid,))
        fresh_db.commit()
        row = fresh_db.execute(
            "SELECT id FROM policy_snapshots WHERE id = ?", (pid,)
        ).fetchone()
        assert row is None, "policy_snapshots row should cascade-delete with session"

    def test_session_delete_cascades_to_requests(
        self, fresh_db: sqlite3.Connection
    ) -> None:
        sid = _insert_session(fresh_db)
        pid = _insert_policy(fresh_db, sid)
        rid = _insert_request(fresh_db, sid, pid)
        fresh_db.execute("DELETE FROM sessions WHERE id = ?", (sid,))
        fresh_db.commit()
        row = fresh_db.execute(
            "SELECT id FROM requests WHERE id = ?", (rid,)
        ).fetchone()
        assert row is None, "requests row should cascade-delete with session"

    def test_request_delete_cascades_to_claim_evidence(
        self, fresh_db: sqlite3.Connection
    ) -> None:
        sid = _insert_session(fresh_db)
        pid = _insert_policy(fresh_db, sid)
        rid = _insert_request(fresh_db, sid, pid)
        cid = _insert_claim(fresh_db, rid)
        eid = _uid()
        fresh_db.execute(
            """INSERT INTO claim_evidence (id, claim_id, relevance_score, rank)
               VALUES (?, ?, ?, ?)""",
            (eid, cid, 0.88, 1),
        )
        fresh_db.commit()

        # Delete request — cascades through request_claims → claim_evidence
        fresh_db.execute("DELETE FROM requests WHERE id = ?", (rid,))
        fresh_db.commit()

        row = fresh_db.execute(
            "SELECT id FROM claim_evidence WHERE id = ?", (eid,)
        ).fetchone()
        assert row is None, "claim_evidence should cascade-delete with request"

    def test_request_delete_cascades_to_pipeline_traces(
        self, fresh_db: sqlite3.Connection
    ) -> None:
        sid = _insert_session(fresh_db)
        pid = _insert_policy(fresh_db, sid)
        rid = _insert_request(fresh_db, sid, pid)
        tid = _uid()
        fresh_db.execute(
            """INSERT INTO pipeline_traces
               (id, request_id, stage_order, stage_name, stage_status)
               VALUES (?, ?, ?, ?, ?)""",
            (tid, rid, 1, "prompt_received", "passed"),
        )
        fresh_db.commit()
        fresh_db.execute("DELETE FROM requests WHERE id = ?", (rid,))
        fresh_db.commit()
        row = fresh_db.execute(
            "SELECT id FROM pipeline_traces WHERE id = ?", (tid,)
        ).fetchone()
        assert row is None

    def test_request_delete_cascades_to_safety_results(
        self, fresh_db: sqlite3.Connection
    ) -> None:
        sid = _insert_session(fresh_db)
        pid = _insert_policy(fresh_db, sid)
        rid = _insert_request(fresh_db, sid, pid)
        sfid = _uid()
        fresh_db.execute(
            """INSERT INTO safety_filter_results
               (id, request_id, filter_name, result, score)
               VALUES (?, ?, ?, ?, ?)""",
            (sfid, rid, "toxicity", "clean", 0.01),
        )
        fresh_db.commit()
        fresh_db.execute("DELETE FROM requests WHERE id = ?", (rid,))
        fresh_db.commit()
        row = fresh_db.execute(
            "SELECT id FROM safety_filter_results WHERE id = ?", (sfid,)
        ).fetchone()
        assert row is None

    def test_kb_document_delete_cascades_to_chunks(
        self, fresh_db: sqlite3.Connection
    ) -> None:
        sid = _insert_session(fresh_db)
        doc_id = _uid()
        fresh_db.execute(
            """INSERT INTO kb_documents
               (id, session_id, filename, original_filename,
                file_size_bytes, mime_type, storage_path)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (doc_id, sid, "f.pdf", "f.pdf", 512, "application/pdf", f"/tmp/{_uid()}.pdf"),
        )
        chunk_id = _uid()
        fresh_db.execute(
            """INSERT INTO kb_chunks
               (id, document_id, chunk_index, chunk_text, chunk_char_start, chunk_char_end)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (chunk_id, doc_id, 0, "text", 0, 4),
        )
        fresh_db.commit()
        fresh_db.execute("DELETE FROM kb_documents WHERE id = ?", (doc_id,))
        fresh_db.commit()
        row = fresh_db.execute(
            "SELECT id FROM kb_chunks WHERE id = ?", (chunk_id,)
        ).fetchone()
        assert row is None

    def test_session_delete_cascades_to_analytics_counters(
        self, fresh_db: sqlite3.Connection
    ) -> None:
        sid = _insert_session(fresh_db)
        aid = _uid()
        fresh_db.execute(
            """INSERT INTO analytics_counters
               (id, session_id, date_bucket, model_provider, model_name)
               VALUES (?, ?, ?, ?, ?)""",
            (aid, sid, "2024-03-15", "ollama", "mistral"),
        )
        fresh_db.commit()
        fresh_db.execute("DELETE FROM sessions WHERE id = ?", (sid,))
        fresh_db.commit()
        row = fresh_db.execute(
            "SELECT id FROM analytics_counters WHERE id = ?", (aid,)
        ).fetchone()
        assert row is None


# ---------------------------------------------------------------------------
# safety_filter_results CHECK constraints
# ---------------------------------------------------------------------------

class TestSafetyFilterConstraints:

    def test_score_above_1_rejected(self, fresh_db: sqlite3.Connection) -> None:
        sid = _insert_session(fresh_db)
        pid = _insert_policy(fresh_db, sid)
        rid = _insert_request(fresh_db, sid, pid)
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                """INSERT INTO safety_filter_results
                   (id, request_id, filter_name, result, score)
                   VALUES (?, ?, ?, ?, ?)""",
                (_uid(), rid, "toxicity", "clean", 1.5),
            )
            fresh_db.commit()

    def test_invalid_result_value_rejected(self, fresh_db: sqlite3.Connection) -> None:
        sid = _insert_session(fresh_db)
        pid = _insert_policy(fresh_db, sid)
        rid = _insert_request(fresh_db, sid, pid)
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                """INSERT INTO safety_filter_results
                   (id, request_id, filter_name, result, score)
                   VALUES (?, ?, ?, ?, ?)""",
                (_uid(), rid, "toxicity", "unknown", 0.5),
            )
            fresh_db.commit()


# ---------------------------------------------------------------------------
# analytics_counters CHECK constraints
# ---------------------------------------------------------------------------

class TestAnalyticsConstraints:

    def test_negative_total_requests_rejected(self, fresh_db: sqlite3.Connection) -> None:
        sid = _insert_session(fresh_db)
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                """INSERT INTO analytics_counters
                   (id, session_id, date_bucket, model_provider, model_name, total_requests)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (_uid(), sid, "2024-01-01", "ollama", "mistral", -1),
            )
            fresh_db.commit()

    def test_analytics_unique_constraint(self, fresh_db: sqlite3.Connection) -> None:
        sid = _insert_session(fresh_db)
        params = (_uid(), sid, "2024-01-01", "ollama", "mistral")
        fresh_db.execute(
            "INSERT INTO analytics_counters (id, session_id, date_bucket, model_provider, model_name) VALUES (?, ?, ?, ?, ?)",
            params,
        )
        fresh_db.commit()
        with pytest.raises(sqlite3.IntegrityError):
            fresh_db.execute(
                "INSERT INTO analytics_counters (id, session_id, date_bucket, model_provider, model_name) VALUES (?, ?, ?, ?, ?)",
                (_uid(), sid, "2024-01-01", "ollama", "mistral"),  # duplicate composite key
            )
            fresh_db.commit()


# ---------------------------------------------------------------------------
# Downgrade and re-upgrade
# ---------------------------------------------------------------------------

class TestDowngradeUpgrade:

    def test_downgrade_base_drops_all_tables(
        self, downgrade_db: object, tmp_path: object
    ) -> None:
        import os
        import subprocess
        import sys
        from pathlib import Path

        db_path = downgrade_db  # type: ignore[assignment]
        backend_root = Path(__file__).resolve().parents[2]
        env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{db_path}"}

        result = subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "base"],
            cwd=str(backend_root),
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0, f"downgrade failed: {result.stderr}"

        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'alembic_%'"
        ).fetchall()
        conn.close()
        assert rows == [], f"Tables remain after downgrade: {[r[0] for r in rows]}"

    def test_upgrade_after_downgrade_succeeds(
        self, downgrade_db: object
    ) -> None:
        import os
        import subprocess
        import sys
        from pathlib import Path

        db_path = downgrade_db  # type: ignore[assignment]
        backend_root = Path(__file__).resolve().parents[2]
        env = {**os.environ, "DATABASE_URL": f"sqlite+aiosqlite:///{db_path}"}

        subprocess.run(
            [sys.executable, "-m", "alembic", "downgrade", "base"],
            cwd=str(backend_root), env=env, capture_output=True,
        )
        result = subprocess.run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=str(backend_root),
            capture_output=True,
            text=True,
            env=env,
        )
        assert result.returncode == 0, f"re-upgrade failed: {result.stderr}"
