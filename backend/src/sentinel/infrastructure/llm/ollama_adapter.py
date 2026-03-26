from __future__ import annotations

import asyncio
import json
import time

import httpx

from sentinel.infrastructure.llm.base import (
    LLMResponse,
    LLMUnavailableError,
)

_DEFAULT_BASE_URL = "http://localhost:11434"
_MAX_RETRIES = 3
_BACKOFF_BASE_SECONDS = 1.0  # delays: 1 s, 2 s, 4 s


class OllamaAdapter:
    """LLMAdapter implementation for a locally running Ollama server.

    Uses httpx.AsyncClient to POST to the Ollama /api/generate endpoint,
    consumes the NDJSON streaming response, and retries transient connection
    failures with exponential backoff (up to _MAX_RETRIES attempts).
    """

    def __init__(self, base_url: str = _DEFAULT_BASE_URL) -> None:
        """Initialise the adapter.

        Args:
            base_url: Base URL of the Ollama HTTP server
                      (default: http://localhost:11434).
        """
        self._base_url: str = base_url.rstrip("/")

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
        """Stream a completion from Ollama with exponential-backoff retry.

        Raises:
            LLMUnavailableError: after _MAX_RETRIES failed attempts, or on
                                 timeout, or if Ollama returns an error body.
        """
        last_exc: Exception | None = None

        for attempt in range(_MAX_RETRIES):
            if attempt > 0:
                delay = _BACKOFF_BASE_SECONDS * (2 ** (attempt - 1))
                await asyncio.sleep(delay)

            try:
                return await self._do_complete(
                    prompt=prompt,
                    model_name=model_name,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout_seconds=timeout_seconds,
                )
            except LLMUnavailableError:
                raise  # propagate non-retryable errors immediately
            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                last_exc = exc
                continue

        raise LLMUnavailableError(f"Ollama unreachable after {_MAX_RETRIES} attempts") from last_exc

    async def health_check(self) -> bool:
        """Return True if Ollama is reachable (GET /api/tags succeeds)."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                return bool(resp.status_code == 200)
        except Exception:
            return False

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _do_complete(
        self,
        prompt: str,
        model_name: str,
        temperature: float,
        max_tokens: int,
        timeout_seconds: float,
    ) -> LLMResponse:
        """Single (non-retried) request to /api/generate."""
        payload = {
            "model": model_name,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        text_parts: list[str] = []
        tokens_in = 0
        tokens_out = 0
        t_start = time.monotonic()

        timeout = httpx.Timeout(timeout=timeout_seconds)

        try:
            async with (
                httpx.AsyncClient(timeout=timeout) as client,
                client.stream(
                    "POST",
                    f"{self._base_url}/api/generate",
                    json=payload,
                ) as response,
            ):
                if response.status_code != 200:
                    body = await response.aread()
                    raise LLMUnavailableError(
                        f"Ollama returned HTTP {response.status_code}: "
                        f"{body.decode(errors='replace')}"
                    )

                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line:
                        continue
                    chunk = json.loads(line)

                    if chunk.get("error"):
                        raise LLMUnavailableError(f"Ollama error: {chunk['error']}")

                    text_parts.append(chunk.get("response", ""))

                    if chunk.get("done"):
                        tokens_in = int(chunk.get("prompt_eval_count", 0))
                        tokens_out = int(chunk.get("eval_count", 0))
                        break

        except httpx.TimeoutException as exc:
            raise httpx.TimeoutException(str(exc)) from exc  # re-raise for retry loop

        latency_ms = (time.monotonic() - t_start) * 1000.0
        return LLMResponse(
            text="".join(text_parts),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            latency_ms=latency_ms,
            model_name=model_name,
        )
