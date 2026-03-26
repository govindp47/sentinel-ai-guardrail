from __future__ import annotations

from contextlib import suppress
from pathlib import Path
import unicodedata

_MAX_FILENAME_LENGTH = 255
# Characters that are dangerous in filenames on any OS or that enable traversal.
_UNSAFE_CHARS = frozenset('/\\:*?"<>|\x00')


class LocalFileStorage:
    """File storage adapter for KB document management on the local filesystem.

    Files are stored under ``base_path / session_id / filename``.
    All write and delete operations are synchronous (called from thread-pool
    or background workers, not the hot async request path).
    """

    def __init__(self, base_path: Path) -> None:
        """Initialise storage and create *base_path* if it does not exist.

        Args:
            base_path: root directory under which all session subdirectories
                       are created.
        """
        self._base_path: Path = base_path
        base_path.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def save(
        self,
        file_content: bytes,
        filename: str,
        session_id: str,
    ) -> Path:
        """Write *file_content* to ``base_path / session_id / safe_filename``.

        Args:
            file_content: raw bytes to persist.
            filename:     original filename (will be sanitised before use).
            session_id:   opaque session identifier used as a subdirectory
                          name.  Must be non-empty.

        Returns:
            Absolute Path to the written file.

        Raises:
            ValueError: if *session_id* is empty or *filename* sanitises to
                        an empty string.
        """
        if not session_id or not session_id.strip():
            raise ValueError("session_id must be non-empty")

        safe_name = self.sanitize_filename(filename)
        if not safe_name:
            raise ValueError(f"filename {filename!r} sanitises to an empty string")

        # Sanitise the session_id directory component as well to prevent
        # directory traversal through that parameter.
        safe_session = self.sanitize_filename(session_id)
        if not safe_session:
            raise ValueError(f"session_id {session_id!r} sanitises to an empty string")

        dest_dir = self._base_path / safe_session
        dest_dir.mkdir(parents=True, exist_ok=True)

        dest_path = dest_dir / safe_name
        dest_path.write_bytes(file_content)
        return dest_path

    def delete(self, path: Path) -> None:
        """Remove *path* from the filesystem.

        Idempotent: does not raise if *path* does not exist.

        Args:
            path: path to the file to remove (typically a value previously
                  returned by :meth:`save`).
        """
        with suppress(FileNotFoundError):
            path.unlink()

    @staticmethod
    def sanitize_filename(filename: str) -> str:
        """Return a filesystem-safe version of *filename*.

        Steps applied in order:
        1. Unicode NFKC normalisation (e.g. full-width chars → ASCII).
        2. Strip leading/trailing whitespace.
        3. Remove all occurrences of ``..`` (traversal sequences).
        4. Remove all characters in ``_UNSAFE_CHARS`` (path separators etc.).
        5. Collapse any resulting empty segments to underscores.
        6. Truncate to ``_MAX_FILENAME_LENGTH`` characters.

        Args:
            filename: raw filename string from an untrusted source.

        Returns:
            Sanitised filename string.  May be empty if the input contained
            only unsafe characters.
        """
        # Step 1 — Unicode normalisation.
        name = unicodedata.normalize("NFKC", filename)

        # Step 2 — strip surrounding whitespace.
        name = name.strip()

        # Step 3 — remove path traversal dots.  Replace ".." with "" so
        # "../../etc/passwd" becomes "etcpasswd" after the next step.
        name = name.replace("..", "")

        # Step 4 — remove unsafe characters.
        name = "".join(ch for ch in name if ch not in _UNSAFE_CHARS)

        # Step 5 — collapse sequences of dots/underscores/spaces that are
        # only left after removal (e.g. ".../" → "").  Replace leading
        # dots (hidden files on Unix) with underscores.
        if name.startswith("."):
            name = "_" + name[1:]

        # Step 6 — truncate.
        name = name[:_MAX_FILENAME_LENGTH]

        return name
