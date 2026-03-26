from __future__ import annotations

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class TextChunk:
    """An immutable segment of source text produced by TextChunker.

    Attributes:
        text:        The chunk content (may include overlap from previous chunk).
        char_start:  Inclusive start offset in the original document string.
        char_end:    Exclusive end offset in the original document string.
        chunk_index: Zero-based position of this chunk in the output list.
    """

    text: str
    char_start: int
    char_end: int
    chunk_index: int


# Sentence boundary: split after . ! ? followed by whitespace.
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


class TextChunker:
    """Sliding-window text segmenter with sentence-boundary awareness.

    Sentences are never split mid-way *unless* a single sentence exceeds
    ``chunk_size`` characters, in which case it is hard-cut at ``chunk_size``
    boundaries.  Each chunk (except the first) includes up to ``overlap``
    characters of context carried over from the end of the previous chunk.
    """

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def chunk(
        self,
        text: str,
        chunk_size: int = 512,
        overlap: int = 64,
    ) -> list[TextChunk]:
        """Segment *text* into overlapping chunks.

        Args:
            text:       Source text to segment.
            chunk_size: Target maximum number of characters per chunk
                        (excluding carried-over overlap).
            overlap:    Number of characters from the end of the previous
                        chunk to prepend to the next chunk.

        Returns:
            Ordered list of TextChunk.  Empty list if *text* is empty or
            contains only whitespace.
        """
        if not text or not text.strip():
            return []

        sentences = self._split_sentences(text)
        windows = self._build_windows(sentences, chunk_size, overlap, text)
        return windows

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _split_sentences(text: str) -> list[str]:
        """Split *text* on sentence boundaries, preserving all content."""
        parts = _SENTENCE_SPLIT_RE.split(text)
        # Filter empty strings that can arise from leading/trailing whitespace.
        return [p for p in parts if p]

    @staticmethod
    def _hard_cut(sentence: str, chunk_size: int) -> list[str]:
        """Break a sentence that exceeds chunk_size into hard sub-chunks."""
        return [sentence[i : i + chunk_size] for i in range(0, len(sentence), chunk_size)]

    def _build_windows(
        self,
        sentences: list[str],
        chunk_size: int,
        overlap: int,
        original_text: str,
    ) -> list[TextChunk]:
        """Group sentences into overlapping windows.

        Strategy:
        1. Accumulate sentences into a buffer until adding the next sentence
           would exceed ``chunk_size``.
        2. Emit the current buffer as a chunk.
        3. Seed the next buffer with up to ``overlap`` trailing characters
           from the emitted chunk (taken as whole words/sentences where
           possible, but hard-truncated to ``overlap`` if needed).
        4. Sentences longer than ``chunk_size`` are hard-cut first.
        """
        # Expand any oversized sentences into sub-sentences via hard cut.
        expanded: list[str] = []
        for sentence in sentences:
            if len(sentence) > chunk_size:
                expanded.extend(self._hard_cut(sentence, chunk_size))
            else:
                expanded.append(sentence)

        chunks: list[TextChunk] = []
        buffer: list[str] = []
        buffer_len = 0
        # Track character position within the original text.
        search_start = 0

        def emit(buf: list[str]) -> None:
            nonlocal search_start
            chunk_text = " ".join(buf)
            # Locate the chunk in the original text starting from where we
            # last left off.  Use find() to handle edge cases where the same
            # fragment appears multiple times.
            first_sentence = buf[0]
            pos = original_text.find(first_sentence, search_start)
            if pos == -1:
                # Fallback: use the previous end as start (hard-cut fragment).
                pos = search_start
            char_start = pos
            char_end = pos + len(chunk_text)
            # Advance search_start past the first sentence so the next chunk
            # resolves its own start position correctly.
            search_start = pos + len(first_sentence)
            chunks.append(
                TextChunk(
                    text=chunk_text,
                    char_start=char_start,
                    char_end=min(char_end, len(original_text)),
                    chunk_index=len(chunks),
                )
            )

        for sentence in expanded:
            sentence_len = len(sentence)
            # +1 for the joining space when appending to a non-empty buffer.
            join_cost = 1 if buffer else 0

            if buffer and (buffer_len + join_cost + sentence_len > chunk_size):
                emit(buffer)
                # Build overlap seed from the tail of the emitted chunk.
                overlap_seed = self._overlap_seed(buffer, overlap)
                buffer = overlap_seed + [sentence] if overlap_seed else [sentence]
                buffer_len = sum(len(s) for s in buffer) + max(0, len(buffer) - 1)
            else:
                buffer.append(sentence)
                buffer_len += join_cost + sentence_len

        if buffer:
            emit(buffer)

        return chunks

    @staticmethod
    def _overlap_seed(buffer: list[str], overlap: int) -> list[str]:
        """Return trailing sentences whose combined length ≤ overlap.

        Walks the buffer backwards collecting sentences until adding the
        next one would exceed *overlap* characters.  If even a single
        sentence is longer than *overlap*, returns an empty list (the hard
        overlap will be applied at the text level by the caller).
        """
        if overlap <= 0:
            return []

        seed: list[str] = []
        accumulated = 0
        for sentence in reversed(buffer):
            cost = len(sentence) + (1 if seed else 0)
            if accumulated + cost <= overlap:
                seed.insert(0, sentence)
                accumulated += cost
            else:
                break
        return seed
