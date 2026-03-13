from __future__ import annotations


class SentinelBaseError(Exception):
    """Root exception for all Sentinel domain errors.

    Carries a ``context`` dict for structlog integration::

        logger.error("pipeline failed", **exc.context)
    """

    def __init__(self, message: str, **context: object) -> None:
        super().__init__(message)
        self.message = message
        self.context: dict[str, object] = context


class PipelineStageError(SentinelBaseError):
    """Raised when a pipeline stage encounters an unrecoverable error."""

    def __init__(
        self,
        message: str,
        stage_name: str,
        cause: BaseException | None = None,
        **context: object,
    ) -> None:
        super().__init__(message, stage_name=stage_name, cause=str(cause), **context)
        self.stage_name = stage_name
        self.cause = cause


class LLMTimeoutError(SentinelBaseError):
    """Raised when the LLM provider does not respond within the deadline."""

    def __init__(
        self,
        message: str,
        provider: str,
        timeout_seconds: float,
        **context: object,
    ) -> None:
        super().__init__(
            message,
            provider=provider,
            timeout_seconds=timeout_seconds,
            **context,
        )
        self.provider = provider
        self.timeout_seconds = timeout_seconds


class LLMUnavailableError(SentinelBaseError):
    """Raised when the LLM provider endpoint is unreachable."""

    def __init__(
        self,
        message: str,
        provider: str,
        **context: object,
    ) -> None:
        super().__init__(message, provider=provider, **context)
        self.provider = provider


class EmbeddingError(SentinelBaseError):
    """Raised when the embedding model fails to produce a vector."""

    def __init__(
        self,
        message: str,
        model_name: str,
        **context: object,
    ) -> None:
        super().__init__(message, model_name=model_name, **context)
        self.model_name = model_name


class KBNotFoundError(SentinelBaseError):
    """Raised when a requested knowledge base does not exist."""

    def __init__(
        self,
        message: str,
        kb_id: str,
        **context: object,
    ) -> None:
        super().__init__(message, kb_id=kb_id, **context)
        self.kb_id = kb_id


class PolicyViolationError(SentinelBaseError):
    """Raised when request content violates an active policy rule."""

    def __init__(
        self,
        message: str,
        violated_category: str,
        risk_score: int,
        **context: object,
    ) -> None:
        super().__init__(
            message,
            violated_category=violated_category,
            risk_score=risk_score,
            **context,
        )
        self.violated_category = violated_category
        self.risk_score = risk_score


class ValidationError(SentinelBaseError):
    """Raised when input data fails structural or semantic validation."""

    def __init__(
        self,
        message: str,
        field: str,
        received_value: object = None,
        **context: object,
    ) -> None:
        super().__init__(
            message,
            field=field,
            received_value=received_value,
            **context,
        )
        self.field = field
        self.received_value = received_value
