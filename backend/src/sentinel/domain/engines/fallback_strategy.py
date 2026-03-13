from __future__ import annotations

from sentinel.domain.models.pipeline_context import PipelineContext

_STRICTER_PROMPT_SUFFIX = (
    "\n\nIMPORTANT: Respond only with verified factual information. "
    "If you are uncertain, explicitly state your uncertainty. "
    "Do not fabricate facts, statistics, or citations."
)

_DEFAULT_ALTERNATE_PROVIDER = "openai"
_DEFAULT_ALTERNATE_MODEL = "gpt-4o-mini"


class FallbackStrategyEngine:
    """Pure synchronous fallback strategy engine — no I/O, no side effects.

    ``apply(context, strategy)`` applies the named strategy and resets
    pipeline stage outputs for the next attempt.

    Strategy tracking uses ``context.stage_start_times`` sentinel keys
    ``"_attempted:<strategy>"`` so ``GuardrailDecisionEngine._select_fallback_strategy``
    can skip already-tried strategies.
    """

    def apply(self, context: PipelineContext, strategy: str) -> PipelineContext:
        """Apply *strategy* to *context* and prepare it for the next attempt.

        Args:
            context:  The current mutable pipeline context.
            strategy: One of 'retry_prompt', 'retry_lower_temp',
                      'rag_augmentation', 'alternate_model'.

        Returns:
            The same *context* object, mutated in-place.
        """
        # Mark strategy as attempted
        context.stage_start_times[f"_attempted:{strategy}"] = 1.0

        if strategy == "retry_prompt":
            context.masked_prompt = context.masked_prompt + _STRICTER_PROMPT_SUFFIX
            context.fallback_strategy_applied = "retry_prompt"

        elif strategy == "retry_lower_temp":
            current_temp = context.stage_start_times.get("_temperature_hint", 1.0)
            context.stage_start_times["_temperature_hint"] = max(0.0, current_temp - 0.3)
            context.fallback_strategy_applied = "retry_lower_temp"

        elif strategy == "rag_augmentation":
            if context.kb_id:
                context.stage_start_times["_rag_requested"] = 1.0
                context.fallback_strategy_applied = "rag_augmentation"
            else:
                context.fallback_strategy_applied = None

        elif strategy == "alternate_model":
            if context.model_provider == "ollama":
                context.model_provider = _DEFAULT_ALTERNATE_PROVIDER
                context.model_name = _DEFAULT_ALTERNATE_MODEL
            context.fallback_strategy_applied = "alternate_model"

        else:
            context.fallback_strategy_applied = None

        # Reset stage outputs for next pipeline attempt
        context.llm_response_text = None
        context.claims = []
        context.claim_results = []
        context.safety_results = []
        context.confidence_score = None
        context.guardrail_decision = None
        context.retry_requested = False
        context.attempt_number += 1

        return context
