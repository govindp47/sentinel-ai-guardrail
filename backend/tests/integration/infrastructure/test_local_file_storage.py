"""Integration tests for LocalFileStorage."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from sentinel.infrastructure.storage.local_file_storage import LocalFileStorage


@pytest.fixture
def storage(tmp_path: Path) -> LocalFileStorage:
    return LocalFileStorage(base_path=tmp_path / "uploads")


class TestSave:
    def test_save_returns_path_object(self, storage: LocalFileStorage) -> None:
        path = storage.save(b"hello", "doc.pdf", session_id="sess-001")
        assert isinstance(path, Path)

    def test_saved_file_exists(self, storage: LocalFileStorage) -> None:
        path = storage.save(b"content bytes", "report.txt", session_id="sess-001")
        assert path.exists()

    def test_saved_file_has_correct_content(self, storage: LocalFileStorage) -> None:
        content = b"binary\x00content\xff"
        path = storage.save(content, "data.bin", session_id="sess-002")
        assert path.read_bytes() == content

    def test_save_creates_session_subdirectory(self, storage: LocalFileStorage) -> None:
        path = storage.save(b"x", "file.txt", session_id="new-session")
        assert path.parent.name == "new-session"

    def test_save_creates_base_path_if_missing(self, tmp_path: Path) -> None:
        new_base = tmp_path / "deep" / "nested" / "uploads"
        s = LocalFileStorage(base_path=new_base)
        path = s.save(b"data", "f.txt", session_id="s1")
        assert path.exists()

    def test_empty_session_id_raises(self, storage: LocalFileStorage) -> None:
        with pytest.raises(ValueError, match="session_id"):
            storage.save(b"data", "file.txt", session_id="")

    def test_empty_filename_after_sanitise_raises(
        self, storage: LocalFileStorage
    ) -> None:
        with pytest.raises(ValueError, match="sanitises"):
            storage.save(b"data", "/\\", session_id="sess")


class TestDelete:
    def test_delete_removes_file(self, storage: LocalFileStorage) -> None:
        path = storage.save(b"to be deleted", "temp.txt", session_id="s1")
        assert path.exists()
        storage.delete(path)
        assert not path.exists()

    def test_delete_is_idempotent(self, storage: LocalFileStorage) -> None:
        path = storage.save(b"data", "temp.txt", session_id="s1")
        storage.delete(path)
        # Second delete must not raise.
        storage.delete(path)

    def test_delete_non_existent_path_does_not_raise(
        self, tmp_path: Path, storage: LocalFileStorage
    ) -> None:
        ghost = tmp_path / "does_not_exist.txt"
        storage.delete(ghost)  # must not raise


class TestSanitizeFilename:
    def test_path_traversal_removed(self) -> None:
        result = LocalFileStorage.sanitize_filename("../../../etc/passwd")
        assert "/" not in result
        assert "\\" not in result
        assert ".." not in result

    def test_path_traversal_result_is_safe(self) -> None:
        result = LocalFileStorage.sanitize_filename("../../../etc/passwd")
        # Must not be empty and must not start with a dot.
        assert result
        assert not result.startswith("..")

    def test_windows_separators_replaced(self) -> None:
        result = LocalFileStorage.sanitize_filename("C:\\Windows\\system32\\cmd.exe")
        assert "\\" not in result
        assert ":" not in result

    def test_normal_filename_preserved(self) -> None:
        result = LocalFileStorage.sanitize_filename("report_2024-01.pdf")
        assert result == "report_2024-01.pdf"

    def test_max_length_enforced(self) -> None:
        long_name = "a" * 500 + ".txt"
        result = LocalFileStorage.sanitize_filename(long_name)
        assert len(result) <= 255

    def test_unicode_normalisation(self) -> None:
        # Full-width latin letters → ASCII via NFKC
        result = LocalFileStorage.sanitize_filename("ｆｉｌｅ.txt")
        assert len(result) <= 255
        assert result  # must not be empty

    def test_null_byte_removed(self) -> None:
        result = LocalFileStorage.sanitize_filename("file\x00name.txt")
        assert "\x00" not in result

    def test_leading_dot_replaced(self) -> None:
        result = LocalFileStorage.sanitize_filename(".hidden")
        assert not result.startswith(".")
