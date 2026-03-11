"""
Integration tests for migration 0001_initial_schema.

Verifies:
  - All 10 tables are created by upgrade()
  - All expected indexes exist
  - FK CASCADE constraints are enforced
  - CHECK constraints reject out-of-range values
  - downgrade() drops all tables cleanly
"""

from __future__ import annotations

import subprocess
import sys
import uuid
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _db_url(tmp_path: Path, name: str = "test.db") -> str:
    return f"sqlite+aiosqlite:///{tmp_path / name}"


def _run(
    *args: str,
    db_url: str,
    cwd: Path = BACKEND_ROOT,
) -> subprocess.CompletedProcess[str]:
    import os
    env = {**os.environ, "DATABASE_URL": db_url}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=env,
    )


def _get_conn(db_path: Path):
    """Return a synchronous sqlite3 connection (for DDL inspection only)."""
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _upgrade(tmp_path: Path) -> Path:
    """Run alembic upgrade head and return the db file path."""
    db_path = tmp_path / "test.db"
    url = f"sqlite+aiosqlite:///{db_path}"
    result = _run("upgrade", "head", db_url=url)
    assert result.returncode == 0, (
        f"upgrade head failed\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )
    return db_path


# ---------------------------------------------------------------------------
# Table existence
# ---------------------------------------------------------------------------

EXPECTED_TABLES = {
    "sessions",
    "policy_snapshots",
    "kb_documents",
    "kb_chunks",
    "analytics_counters",
    "requests",
    "pipeline_traces",
    "request_claims",
    "claim_evidence",
    "safety_filter_results",
}

EXPECTED_INDEXES = {
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
}


class TestUpgrade:
    def test_all_tables_created(self, tmp_path: Path) -> None:
        db_path = _upgrade(tmp_path)
        conn = _get_conn(db_path)
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'alembic_%'"
        ).fetchall()
        actual = {r[0] for r in rows}
        assert EXPECTED_TABLES == actual, f"Missing tables: {EXPECTED_TABLES - actual}"

    def test_all_indexes_created(self, tmp_path: Path) -> None:
        db_path = _upgrade(tmp_path)
        conn = _get_conn(db_path)
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
        actual = {r[0] for r in rows}
        missing = EXPECTED_INDEXES - actual
        assert not missing, f"Missing indexes: {missing}"

    def test_alembic_history_shows_0001(self, tmp_path: Path) -> None:
        db_path = tmp_path / "test.db"
        url = f"sqlite+aiosqlite:///{db_path}"
        result = _run("history", db_url=url)
        assert result.returncode == 0
        assert "0001" in result.stdout

    def test_alembic_current_shows_head(self, tmp_path: Path) -> None:
        db_path = _upgrade(tmp_path)
        url = f"sqlite+aiosqlite:///{db_path}"
        result = _run("current", db_url=url)
        assert result.returncode == 0
        assert "head" in result.stdout


# ---------------------------------------------------------------------------
# FK constraint enforcement
# ---------------------------------------------------------------------------

class TestForeignKeys:
    def test_policy_snapshots_cascade_delete(self, tmp_path: Path) -> None:
        """Deleting a session cascades to policy_snapshots."""
        db_path = _upgrade(tmp_path)
        conn = _get_conn(db_path)
        sid = str(uuid.uuid4())
        pid = str(uuid.uuid4())
        conn.execute("INSERT INTO sessions (id) VALUES (?)", (sid,))
        conn.execute(
            "INSERT INTO policy_snapshots (id, session_id) VALUES (?, ?)", (pid, sid)
        )
        conn.commit()
        conn.execute("DELETE FROM sessions WHERE id = ?", (sid,))
        conn.commit()
        row = conn.execute(
            "SELECT id FROM policy_snapshots WHERE id = ?", (pid,)
        ).fetchone()
        assert row is None, "policy_snapshots row should have been cascade-deleted"

    def test_requests_cascade_delete(self, tmp_path: Path) -> None:
        """Deleting a session cascades to requests."""
        db_path = _upgrade(tmp_path)
        conn = _get_conn(db_path)
        sid = str(uuid.uuid4())
        pid = str(uuid.uuid4())
        rid = str(uuid.uuid4())
        conn.execute("INSERT INTO sessions (id) VALUES (?)", (sid,))
        conn.execute(
            "INSERT INTO policy_snapshots (id, session_id) VALUES (?, ?)", (pid, sid)
        )
        conn.execute(
            """INSERT INTO requests
               (id, session_id, policy_snapshot_id, prompt_hash, prompt_masked_text,
                model_provider, model_name)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (rid, sid, pid, "abc", "masked", "ollama", "mistral"),
        )
        conn.commit()
        conn.execute("DELETE FROM sessions WHERE id = ?", (sid,))
        conn.commit()
        row = conn.execute(
            "SELECT id FROM requests WHERE id = ?", (rid,)
        ).fetchone()
        assert row is None, "requests row should have been cascade-deleted"

    def test_orphan_request_rejected(self, tmp_path: Path) -> None:
        """Inserting a request with a non-existent session_id raises FK error."""
        import sqlite3
        db_path = _upgrade(tmp_path)
        conn = _get_conn(db_path)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO requests
                   (id, session_id, policy_snapshot_id, prompt_hash, prompt_masked_text,
                    model_provider, model_name)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()),
                    "nonexistent-session",
                    str(uuid.uuid4()),
                    "hash",
                    "masked",
                    "ollama",
                    "mistral",
                ),
            )
            conn.commit()


# ---------------------------------------------------------------------------
# CHECK constraint enforcement
# ---------------------------------------------------------------------------

class TestCheckConstraints:
    def _insert_session_and_policy(self, conn, sid: str, pid: str) -> None:
        conn.execute("INSERT INTO sessions (id) VALUES (?)", (sid,))
        conn.execute(
            "INSERT INTO policy_snapshots (id, session_id) VALUES (?, ?)", (pid, sid)
        )
        conn.commit()

    def test_policy_threshold_order_enforced(self, tmp_path: Path) -> None:
        """block_threshold < warn_threshold must hold."""
        import sqlite3
        db_path = _upgrade(tmp_path)
        conn = _get_conn(db_path)
        sid = str(uuid.uuid4())
        conn.execute("INSERT INTO sessions (id) VALUES (?)", (sid,))
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO policy_snapshots
                   (id, session_id, block_threshold, warn_threshold, accept_threshold)
                   VALUES (?, ?, ?, ?, ?)""",
                (str(uuid.uuid4()), sid, 50, 40, 70),  # block > warn — invalid
            )
            conn.commit()

    def test_requests_invalid_model_provider(self, tmp_path: Path) -> None:
        """model_provider must be 'ollama' or 'openai'."""
        import sqlite3
        db_path = _upgrade(tmp_path)
        conn = _get_conn(db_path)
        sid = str(uuid.uuid4())
        pid = str(uuid.uuid4())
        self._insert_session_and_policy(conn, sid, pid)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO requests
                   (id, session_id, policy_snapshot_id, prompt_hash, prompt_masked_text,
                    model_provider, model_name)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (str(uuid.uuid4()), sid, pid, "h", "m", "anthropic", "claude"),
            )
            conn.commit()

    def test_requests_invalid_status(self, tmp_path: Path) -> None:
        """status must be one of the allowed values."""
        import sqlite3
        db_path = _upgrade(tmp_path)
        conn = _get_conn(db_path)
        sid = str(uuid.uuid4())
        pid = str(uuid.uuid4())
        self._insert_session_and_policy(conn, sid, pid)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO requests
                   (id, session_id, policy_snapshot_id, prompt_hash, prompt_masked_text,
                    model_provider, model_name, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (str(uuid.uuid4()), sid, pid, "h", "m", "ollama", "mistral", "invalid"),
            )
            conn.commit()

    def test_safety_filter_invalid_score(self, tmp_path: Path) -> None:
        """score must be BETWEEN 0.0 AND 1.0."""
        import sqlite3
        db_path = _upgrade(tmp_path)
        conn = _get_conn(db_path)
        sid = str(uuid.uuid4())
        pid = str(uuid.uuid4())
        rid = str(uuid.uuid4())
        self._insert_session_and_policy(conn, sid, pid)
        conn.execute(
            """INSERT INTO requests
               (id, session_id, policy_snapshot_id, prompt_hash, prompt_masked_text,
                model_provider, model_name)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (rid, sid, pid, "h", "m", "ollama", "mistral"),
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO safety_filter_results
                   (id, request_id, filter_name, result, score)
                   VALUES (?, ?, ?, ?, ?)""",
                (str(uuid.uuid4()), rid, "toxicity", "clean", 1.5),
            )
            conn.commit()

    def test_analytics_negative_counter(self, tmp_path: Path) -> None:
        """total_requests must be >= 0."""
        import sqlite3
        db_path = _upgrade(tmp_path)
        conn = _get_conn(db_path)
        sid = str(uuid.uuid4())
        conn.execute("INSERT INTO sessions (id) VALUES (?)", (sid,))
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                """INSERT INTO analytics_counters
                   (id, session_id, date_bucket, model_provider, model_name, total_requests)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (str(uuid.uuid4()), sid, "2024-01-01", "ollama", "mistral", -1),
            )
            conn.commit()


# ---------------------------------------------------------------------------
# Downgrade
# ---------------------------------------------------------------------------

class TestDowngrade:
    def test_downgrade_base_drops_all_tables(self, tmp_path: Path) -> None:
        db_path = _upgrade(tmp_path)
        url = f"sqlite+aiosqlite:///{db_path}"
        result = _run("downgrade", "base", db_url=url)
        assert result.returncode == 0, (
            f"downgrade base failed\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )
        conn = _get_conn(db_path)
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'alembic_%'"
        ).fetchall()
        assert rows == [], f"Tables remain after downgrade: {[r[0] for r in rows]}"

    def test_upgrade_after_downgrade(self, tmp_path: Path) -> None:
        """upgrade → downgrade → upgrade must be idempotent."""
        db_path = _upgrade(tmp_path)
        url = f"sqlite+aiosqlite:///{db_path}"
        _run("downgrade", "base", db_url=url)
        result = _run("upgrade", "head", db_url=url)
        assert result.returncode == 0
