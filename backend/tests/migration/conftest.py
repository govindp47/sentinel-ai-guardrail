"""
Shared fixtures for the migration test suite.

`migrated_db` runs `alembic upgrade head` against a temp SQLite file,
yields a synchronous sqlite3 connection for DDL inspection, then tears down.

A synchronous sqlite3 connection (not SQLAlchemy) is used for schema
introspection tests because sqlite_master queries are simpler and
do not require an async event loop in plain pytest functions.
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _alembic(*args: str, db_path: Path) -> subprocess.CompletedProcess[str]:
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite+aiosqlite:///{db_path}",
    }
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=str(BACKEND_ROOT),
        capture_output=True,
        text=True,
        env=env,
    )


@pytest.fixture(scope="module")
def migrated_db(tmp_path_factory: pytest.TempPathFactory) -> sqlite3.Connection:
    """
    Runs `alembic upgrade head` once per test module against a fresh SQLite
    file.  Yields a sqlite3 connection with foreign_keys=ON.
    Tears down by closing the connection (file is cleaned up by tmp_path_factory).
    """
    db_path = tmp_path_factory.mktemp("migration") / "test.db"

    result = _alembic("upgrade", "head", db_path=db_path)
    assert result.returncode == 0, (
        f"alembic upgrade head failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row

    yield conn

    conn.close()


@pytest.fixture(scope="function")
def fresh_db(tmp_path: Path) -> sqlite3.Connection:
    """
    Per-test fresh upgraded database.  Used by constraint tests that
    INSERT and DELETE rows (module-scoped db would accumulate state).
    """
    db_path = tmp_path / "test.db"

    result = _alembic("upgrade", "head", db_path=db_path)
    assert result.returncode == 0, (
        f"alembic upgrade head failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row

    yield conn

    conn.close()


@pytest.fixture(scope="function")
def downgrade_db(tmp_path: Path) -> Path:
    """Yields a db_path that has been upgraded — for downgrade tests."""
    db_path = tmp_path / "test.db"
    result = _alembic("upgrade", "head", db_path=db_path)
    assert result.returncode == 0
    return db_path
