"""Integration tests for OpenAIAdapter.

All tests use respx to mock HTTP calls — no real OpenAI API key required.
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from sentinel.infrastructure.llm.base import LLMResponse, LLMUnavailableError
from sentinel.infrastructure.llm.openai_adapter import OpenAIAdapter

_FAKE_KEY = "sk-test-0000000000000000"
_MODEL = "gpt-4o-mini"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _chat_response_body(
    text: str = "Hello!",
    model: str = _MODEL,
    prompt_tokens: int = 10,
    completion_tokens: int = 5,
) -> dict:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 1700000000,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": text},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestMissingAPIKey:
    def test_empty_key_raises_immediately(self) -> None:
        with pytest.raises(LLMUnavailableError, match="API key"):
            OpenAIAdapter(api_key="")

    def test_whitespace_key_raises_immediately(self) -> None:
        with pytest.raises(LLMUnavailableError, match="API key"):
            OpenAIAdapter(api_key="   ")


class TestHealthCheck:
    @pytest.mark.asyncio
    async def test_health_check_true_with_valid_key(self) -> None:
        adapter = OpenAIAdapter(api_key=_FAKE_KEY)
        assert await adapter.health_check() is True


class TestSuccessfulCompletion:
    @pytest.mark.asyncio
    @respx.mock
    async def test_complete_returns_llm_response(self) -> None:
        respx.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=Response(
                200, json=_chat_response_body(text="Hello!", prompt_tokens=8, completion_tokens=3)
            )
        )

        adapter = OpenAIAdapter(api_key=_FAKE_KEY)
        response = await adapter.complete(
            prompt="Say hello.",
            model_name=_MODEL,
        )

        assert isinstance(response, LLMResponse)
        assert response.text == "Hello!"
        assert response.tokens_in == 8
        assert response.tokens_out == 3
        assert response.latency_ms > 0.0
        assert response.model_name == _MODEL

    @pytest.mark.asyncio
    @respx.mock
    async def test_complete_uses_returned_model_name(self) -> None:
        """model_name in LLMResponse must match what the API returns."""
        respx.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=Response(
                200,
                json=_chat_response_body(model="gpt-4o-mini-2024-07-18"),
            )
        )

        adapter = OpenAIAdapter(api_key=_FAKE_KEY)
        response = await adapter.complete(prompt="hi", model_name=_MODEL)
        assert response.model_name == "gpt-4o-mini-2024-07-18"


class TestErrorMapping:
    @pytest.mark.asyncio
    @respx.mock
    async def test_auth_error_maps_to_llm_unavailable(self) -> None:
        respx.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=Response(
                401,
                json={
                    "error": {
                        "message": "Incorrect API key",
                        "type": "invalid_request_error",
                        "code": "invalid_api_key",
                    }
                },
            )
        )

        adapter = OpenAIAdapter(api_key=_FAKE_KEY)
        with pytest.raises(LLMUnavailableError, match="authentication"):
            await adapter.complete(prompt="hello", model_name=_MODEL)

    @pytest.mark.asyncio
    @respx.mock
    async def test_rate_limit_maps_to_llm_unavailable(self) -> None:
        respx.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=Response(
                429,
                json={
                    "error": {
                        "message": "Rate limit exceeded",
                        "type": "requests",
                        "code": "rate_limit_exceeded",
                    }
                },
            )
        )

        adapter = OpenAIAdapter(api_key=_FAKE_KEY)
        with pytest.raises(LLMUnavailableError, match="rate limit"):
            await adapter.complete(prompt="hello", model_name=_MODEL)

    @pytest.mark.asyncio
    @respx.mock
    async def test_server_error_maps_to_llm_unavailable(self) -> None:
        respx.post("https://api.openai.com/v1/chat/completions").mock(
            return_value=Response(
                500,
                json={"error": {"message": "Server error", "type": "server_error"}},
            )
        )

        adapter = OpenAIAdapter(api_key=_FAKE_KEY)
        with pytest.raises(LLMUnavailableError):
            await adapter.complete(prompt="hello", model_name=_MODEL)
