from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class LLMUnavailableError(Exception):
    """Raised when an LLM provider is unreachable, misconfigured, or returns
    an unrecoverable error (auth failure, persistent connection error, etc.).

    Wraps the original exception in __cause__ so callers can inspect it.
    """


@dataclass(frozen=True)
class LLMResponse:
    """Immutable result returned by every LLMAdapter implementation.

    Attributes:
        text:         The raw text completion from the model.
        tokens_in:    Prompt token count reported by the provider.
        tokens_out:   Completion token count reported by the provider.
        latency_ms:   Wall-clock time of the HTTP round-trip in milliseconds.
        model_name:   The model identifier actually used for generation.
    """

    text: str
    tokens_in: int
    tokens_out: int
    latency_ms: float
    model_name: str


@runtime_checkable
class LLMAdapter(Protocol):
    """Protocol for LLM provider adapters.

    Both OllamaAdapter and OpenAIAdapter implement this interface.
    All methods are async; implementations must not block the event loop.
    """

    async def complete(
        self,
        prompt: str,
        model_name: str,
        temperature: float = 0.7,
        max_tokens: int = 1024,
        timeout_seconds: float = 30.0,
    ) -> LLMResponse:
        """Generate a text completion for *prompt*.

        Args:
            prompt:          The full prompt string to send to the model.
            model_name:      Provider-specific model identifier.
            temperature:     Sampling temperature (0.0–2.0).
            max_tokens:      Maximum completion tokens to generate.
            timeout_seconds: Per-request timeout; raises LLMUnavailableError
                             if exceeded.

        Returns:
            LLMResponse with all fields populated.

        Raises:
            LLMUnavailableError: on connection failure, timeout, or auth error.
        """
        ...

    async def health_check(self) -> bool:
        """Return True if the provider is reachable and operational.

        Must never raise; returns False on any failure.
        """
        ...
