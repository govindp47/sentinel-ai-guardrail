from __future__ import annotations

import time

import openai
from openai import AsyncOpenAI

from sentinel.infrastructure.llm.base import (
    LLMResponse,
    LLMUnavailableError,
)


class OpenAIAdapter:
    """LLMAdapter implementation for the OpenAI Chat Completions API.

    Uses the official openai Python SDK (>=1.0) with AsyncOpenAI.
    health_check() is a local check only — it returns True when an API key
    is configured without making a live network request.
    """

    def __init__(self, api_key: str) -> None:
        """Initialise the adapter.

        Args:
            api_key: OpenAI API key. Must be non-empty; raises
                     LLMUnavailableError immediately if blank.
        """
        if not api_key or not api_key.strip():
            raise LLMUnavailableError(
                "OpenAI API key is missing or empty. "
                "Set the OPENAI_API_KEY environment variable or pass it "
                "explicitly to OpenAIAdapter."
            )
        self._api_key: str = api_key
        self._client: AsyncOpenAI = AsyncOpenAI(api_key=api_key)

    # ------------------------------------------------------------------
    # LLMAdapter protocol
    # ------------------------------------------------------------------

    async def complete(
        self,
        prompt: str,
        model_name: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        timeout_seconds: float = 30.0,
    ) -> LLMResponse:
        """Generate a chat completion via the OpenAI API.

        Raises:
            LLMUnavailableError: on authentication failure, network error,
                                 or timeout.
        """
        t_start = time.monotonic()

        try:
            response = await self._client.chat.completions.create(
                model=model_name,
                messages=[{"role": "user", "content": prompt}],
                temperature=temperature,
                max_tokens=max_tokens,
                timeout=timeout_seconds,
            )
        except openai.AuthenticationError as exc:
            raise LLMUnavailableError(f"OpenAI authentication failed: {exc}") from exc
        except openai.APIConnectionError as exc:
            raise LLMUnavailableError(f"OpenAI connection error: {exc}") from exc
        except openai.APITimeoutError as exc:
            raise LLMUnavailableError(f"OpenAI request timed out after {timeout_seconds}s") from exc
        except openai.RateLimitError as exc:
            raise LLMUnavailableError(f"OpenAI rate limit exceeded: {exc}") from exc
        except openai.APIStatusError as exc:
            raise LLMUnavailableError(f"OpenAI API error {exc.status_code}: {exc.message}") from exc

        latency_ms = (time.monotonic() - t_start) * 1000.0

        choice = response.choices[0]
        usage = response.usage

        return LLMResponse(
            text=choice.message.content or "",
            tokens_in=usage.prompt_tokens if usage else 0,
            tokens_out=usage.completion_tokens if usage else 0,
            latency_ms=latency_ms,
            model_name=response.model,
        )

    async def health_check(self) -> bool:
        """Return True if an API key is configured (no live network call)."""
        return bool(self._api_key and self._api_key.strip())
