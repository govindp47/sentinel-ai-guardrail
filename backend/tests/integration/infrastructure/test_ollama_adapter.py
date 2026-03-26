"""Integration tests for OllamaAdapter.

All tests are skipped unless the environment variable OLLAMA_AVAILABLE=1
is set, confirming that a local Ollama server is running.
"""

from __future__ import annotations

import os

import pytest

from sentinel.infrastructure.llm.base import LLMUnavailableError
from sentinel.infrastructure.llm.ollama_adapter import OllamaAdapter

_OLLAMA_RUNNING = bool(os.getenv("OLLAMA_AVAILABLE"))

pytestmark = pytest.mark.skipif(
    not _OLLAMA_RUNNING,
    reason="Ollama server not available (set OLLAMA_AVAILABLE=1 to enable)",
)

# Change this to any model pulled in your local Ollama instance.
_TEST_MODEL = os.getenv("OLLAMA_TEST_MODEL", "phi3")


@pytest.fixture(scope="module")
def adapter() -> OllamaAdapter:
    return OllamaAdapter()


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_returns_true(
        self, adapter: OllamaAdapter
    ) -> None:
        result = await adapter.health_check()
        assert result is True


class TestComplete:
    @pytest.mark.asyncio
    async def test_complete_returns_non_empty_text(
        self, adapter: OllamaAdapter
    ) -> None:
        response = await adapter.complete(
            prompt="Reply with exactly one word: hello",
            model_name=_TEST_MODEL,
            temperature=0.0,
            max_tokens=10,
            timeout_seconds=60.0,
        )
        assert response.text.strip() != ""
        assert response.model_name == _TEST_MODEL

    @pytest.mark.asyncio
    async def test_complete_returns_token_counts(
        self, adapter: OllamaAdapter
    ) -> None:
        response = await adapter.complete(
            prompt="Say yes.",
            model_name=_TEST_MODEL,
            temperature=0.0,
            max_tokens=5,
            timeout_seconds=60.0,
        )
        assert response.tokens_in >= 0
        assert response.tokens_out >= 0

    @pytest.mark.asyncio
    async def test_complete_latency_is_positive(
        self, adapter: OllamaAdapter
    ) -> None:
        response = await adapter.complete(
            prompt="Say yes.",
            model_name=_TEST_MODEL,
            temperature=0.0,
            max_tokens=5,
            timeout_seconds=60.0,
        )
        assert response.latency_ms > 0.0

    @pytest.mark.asyncio
    async def test_timeout_raises_llm_unavailable(self) -> None:
        adapter = OllamaAdapter()
        with pytest.raises(LLMUnavailableError):
            await adapter.complete(
                prompt="Write a 10000 word essay.",
                model_name=_TEST_MODEL,
                temperature=0.0,
                max_tokens=9999,
                timeout_seconds=0.001,  # intentionally tiny
            )

    @pytest.mark.asyncio
    async def test_unreachable_host_raises_llm_unavailable(self) -> None:
        bad_adapter = OllamaAdapter(base_url="http://127.0.0.1:19999")
        with pytest.raises(LLMUnavailableError):
            await bad_adapter.complete(
                prompt="hello",
                model_name=_TEST_MODEL,
            )
