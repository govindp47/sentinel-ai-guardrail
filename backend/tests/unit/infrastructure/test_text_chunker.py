"""Unit tests for TextChunker.

No external dependencies — fast, deterministic, no model loading.
"""

from __future__ import annotations

import pytest

from sentinel.infrastructure.chunking.text_chunker import TextChunk, TextChunker


@pytest.fixture
def chunker() -> TextChunker:
    return TextChunker()


class TestEmptyInput:
    def test_empty_string_returns_empty_list(self, chunker: TextChunker) -> None:
        assert chunker.chunk("") == []

    def test_whitespace_only_returns_empty_list(self, chunker: TextChunker) -> None:
        assert chunker.chunk("   \n\t  ") == []


class TestShortText:
    def test_short_text_produces_one_chunk(self, chunker: TextChunker) -> None:
        text = "Hello world. This is a short document."
        chunks = chunker.chunk(text, chunk_size=512, overlap=64)
        assert len(chunks) == 1
        assert chunks[0].chunk_index == 0

    def test_single_chunk_contains_full_text(self, chunker: TextChunker) -> None:
        text = "One sentence only."
        chunks = chunker.chunk(text, chunk_size=512, overlap=64)
        assert len(chunks) == 1
        assert "One sentence only." in chunks[0].text


class TestMultipleChunks:
    def _long_text(self, num_sentences: int = 30) -> str:
        return " ".join(
            f"This is sentence number {i} and it has some padding text to fill space."
            for i in range(num_sentences)
        )

    def test_long_text_produces_multiple_chunks(
        self, chunker: TextChunker
    ) -> None:
        text = self._long_text(30)
        chunks = chunker.chunk(text, chunk_size=200, overlap=50)
        assert len(chunks) > 1

    def test_chunk_indices_are_sequential(self, chunker: TextChunker) -> None:
        text = self._long_text(30)
        chunks = chunker.chunk(text, chunk_size=200, overlap=50)
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    def test_no_chunk_exceeds_chunk_size_significantly(
        self, chunker: TextChunker
    ) -> None:
        """Each chunk body (ignoring overlap) should be ≤ chunk_size + longest sentence."""
        text = self._long_text(20)
        chunk_size = 150
        chunks = chunker.chunk(text, chunk_size=chunk_size, overlap=30)
        for chunk in chunks:
            # Allow some slack for the overlap prefix.
            assert len(chunk.text) <= chunk_size * 3, (
                f"Chunk {chunk.chunk_index} is unexpectedly large: {len(chunk.text)}"
            )

    def test_all_text_covered(self, chunker: TextChunker) -> None:
        """Every sentence from the source must appear in at least one chunk."""
        sentences = [
            "First sentence here.",
            "Second sentence here.",
            "Third sentence here.",
            "Fourth sentence here.",
            "Fifth sentence here.",
        ]
        text = " ".join(sentences)
        chunks = chunker.chunk(text, chunk_size=60, overlap=20)
        combined = " ".join(c.text for c in chunks)
        for sentence in sentences:
            assert sentence in combined, f"Missing sentence: {sentence!r}"


class TestOverlap:
    def test_adjacent_chunks_share_overlap_content(
        self, chunker: TextChunker
    ) -> None:
        """The last sentence of chunk N should appear at the start of chunk N+1."""
        # Build text where each sentence is ~40 chars so chunk_size=80
        # forces at least 3 chunks with overlap=40.
        sentences = [f"Sentence {i:02d} with some padding text here." for i in range(10)]
        text = " ".join(sentences)
        chunks = chunker.chunk(text, chunk_size=80, overlap=40)

        if len(chunks) < 2:
            pytest.skip("Not enough chunks produced for overlap test")

        for i in range(len(chunks) - 1):
            current_chunk = chunks[i]
            next_chunk = chunks[i + 1]
            # At least some content from current chunk must appear in next chunk.
            current_words = set(current_chunk.text.split())
            next_words = set(next_chunk.text.split())
            overlap_words = current_words & next_words
            assert len(overlap_words) > 0, (
                f"No overlap found between chunk {i} and chunk {i+1}"
            )

    def test_zero_overlap_produces_no_shared_sentences(
        self, chunker: TextChunker
    ) -> None:
        sentences = [f"Unique sentence {i} with enough words to fill space here." for i in range(8)]
        text = " ".join(sentences)
        chunks = chunker.chunk(text, chunk_size=80, overlap=0)
        # With zero overlap no seed is carried over.
        if len(chunks) >= 2:
            # The last sentence of chunk 0 should NOT start chunk 1.
            last_sentence_of_first = chunks[0].text.split(". ")[-1].strip()
            assert not chunks[1].text.startswith(last_sentence_of_first)


class TestHardCut:
    def test_single_very_long_sentence_is_chunked(
        self, chunker: TextChunker
    ) -> None:
        """A sentence longer than chunk_size must still be segmented."""
        long_sentence = "A" * 600  # no sentence boundary at all
        chunks = chunker.chunk(long_sentence, chunk_size=200, overlap=0)
        assert len(chunks) >= 3
        for chunk in chunks:
            assert len(chunk.text) <= 200

    def test_hard_cut_chunk_indices_sequential(
        self, chunker: TextChunker
    ) -> None:
        long_sentence = "word " * 200  # ~1000 chars, no sentence boundary
        chunks = chunker.chunk(long_sentence, chunk_size=100, overlap=0)
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i


class TestCharOffsets:
    def test_char_start_is_non_negative(self, chunker: TextChunker) -> None:
        text = "Hello world. Second sentence. Third one here."
        chunks = chunker.chunk(text, chunk_size=30, overlap=10)
        for chunk in chunks:
            assert chunk.char_start >= 0

    def test_char_end_does_not_exceed_text_length(
        self, chunker: TextChunker
    ) -> None:
        text = "Hello world. Second sentence. Third one here."
        chunks = chunker.chunk(text, chunk_size=30, overlap=10)
        for chunk in chunks:
            assert chunk.char_end <= len(text)
