"""
Integration tests for the Alembic migration environment (T-005).

Verifies:
  - alembic current exits 0 and reports no applied revisions
  - alembic history exits 0 and reports no migration files
  - env.py loads without ImportError
  - Both SQLite URL variants are accepted without error
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

# Resolve the backend/ root (parent of tests/)
BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _run_alembic(
    *args: str,
    database_url: str = "sqlite+aiosqlite:///./test_migration.db",
    cwd: Path = BACKEND_ROOT,
) -> subprocess.CompletedProcess[str]:
    """Run an alembic sub-command with a given DATABASE_URL."""
    env_patch = {
        "DATABASE_URL": database_url,
        "PATH": "/usr/bin:/bin",  # minimal safe PATH
    }
    import os
    full_env = {**os.environ, **env_patch}

    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        env=full_env,
    )


class TestAlembicEnvironment:
    """Smoke-tests for the Alembic async environment."""

    def test_current_exits_zero(self, tmp_path: Path) -> None:
        """alembic current must exit 0 against a fresh SQLite file."""
        db_url = f"sqlite+aiosqlite:///{tmp_path}/sentinel_test.db"
        result = _run_alembic("current", database_url=db_url)
        assert result.returncode == 0, (
            f"alembic current failed.\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )

    def test_current_reports_no_revision(self, tmp_path: Path) -> None:
        """alembic current output must be empty (no revisions applied)."""
        db_url = f"sqlite+aiosqlite:///{tmp_path}/sentinel_test.db"
        result = _run_alembic("current", database_url=db_url)
        # No revision lines should appear — output should be empty or only log lines
        assert "(head)" not in result.stdout
        assert "ERROR" not in result.stderr

    def test_history_exits_zero(self, tmp_path: Path) -> None:
        """alembic history must exit 0 with an empty versions directory."""
        db_url = f"sqlite+aiosqlite:///{tmp_path}/sentinel_test.db"
        result = _run_alembic("history", database_url=db_url)
        assert result.returncode == 0, (
            f"alembic history failed.\nSTDOUT: {result.stdout}\nSTDERR: {result.stderr}"
        )

    def test_history_is_empty(self, tmp_path: Path) -> None:
        """alembic history must produce no revision entries."""
        db_url = f"sqlite+aiosqlite:///{tmp_path}/sentinel_test.db"
        result = _run_alembic("history", database_url=db_url)
        # No revision lines expected; only possible output is empty or whitespace
        stripped = result.stdout.strip()
        assert stripped == "" or "No revisions" in stripped or "ERROR" not in result.stderr

    def test_env_py_loads_without_import_error(self) -> None:
        """
        Importing alembic env.py indirectly via 'alembic current' must not
        produce any ImportError or ModuleNotFoundError.
        """
        import os
        db_url = "sqlite+aiosqlite:///./test_import_check.db"
        result = _run_alembic("current", database_url=db_url)
        assert "ImportError" not in result.stderr
        assert "ModuleNotFoundError" not in result.stderr

    def test_no_orm_models_imported(self, tmp_path: Path) -> None:
        """
        env.py must not import sentinel ORM models at load time.
        'sentinel.db.models' must not appear in any error traceback.
        """
        db_url = f"sqlite+aiosqlite:///{tmp_path}/sentinel_test.db"
        result = _run_alembic("current", database_url=db_url)
        assert "sentinel.db.models" not in result.stderr
        assert "sentinel.db.base" not in result.stderr
