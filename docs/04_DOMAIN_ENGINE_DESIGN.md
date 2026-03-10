# 04_DOMAIN_ENGINE_DESIGN.md

# SentinelAI Guardrail — Domain Engine Design

---

## 1. Domain Model Philosophy

The domain layer models the guardrail pipeline as a sequence of deterministic transformations applied to a **PipelineContext** value object. The context accumulates the outputs of each stage; no stage directly calls another. The orchestrator drives sequencing and handles control flow (short-circuit on block, retry dispatch). Domain engines are pure computational units: they receive input, produce output, and have no side effects (no database writes, no HTTP calls, no logging). All side-effectful operations are handled in the infrastructure and application layers.

**Core principles:**

1. **Determinism.** Given identical inputs and policy configuration, every stage must produce identical output. The same prompt processed twice with the same policy must yield the same guardrail decision. This is enforced by: no randomness in domain logic, no shared mutable state, stateless engine classes.

2. **Fail-safe defaults.** When a signal is unavailable (embedding model down, empty KB), the engine substitutes a neutral default value that neither artificially inflates nor deflates the confidence score. The substitution is always logged in the stage metadata.

3. **Auditability.** Every computed value (claim score, signal weight, threshold comparison) is preserved in the stage metadata. The domain layer produces rich structured outputs; the application layer persists them.

4. **Separation of policy from mechanism.** Domain engines compute facts (this claim is unsupported, this score is 62). The GuardrailDecisionEngine applies policy thresholds to those facts. Changing a confidence threshold changes the decision without changing the scoring computation.

---

## 2. Domain Model: Core Types

```python
# ── Value Objects ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class Claim:
    index: int
    text: str
    entity_type: str | None  # 'fact', 'statistic', 'date', 'entity', 'causal'

@dataclass(frozen=True)
class Evidence:
    chunk_id: str
    chunk_text: str
    document_filename: str
    relevance_score: float  # cosine similarity, 0.0–1.0
    rank: int

@dataclass(frozen=True)
class ClaimVerificationResult:
    claim: Claim
    status: Literal['supported', 'unsupported', 'contradicted', 'unverified']
    evidence: list[Evidence]
    justification: str
    confidence_contribution: float  # this claim's weighted score contribution

@dataclass(frozen=True)
class SafetyFilterResult:
    filter_name: str
    result: Literal['clean', 'flagged']
    score: float  # 0.0–1.0

@dataclass(frozen=True)
class ConfidenceScore:
    value: int                            # 0–100
    label: Literal['high', 'medium', 'low']
    signal_breakdown: dict[str, float]    # {signal_name: contribution}

@dataclass(frozen=True)
class GuardrailDecision:
    decision_type: Literal[
        'accept', 'accept_with_warning',
        'retry_prompt', 'retry_alternate_model', 'trigger_rag', 'block'
    ]
    reason: str
    triggered_rule: str | None
    safety_filter_override: bool  # True if safety filter forced block over confidence

@dataclass(frozen=True)
class PromptValidationResult:
    injection_result: Literal['pass', 'flag', 'block']
    injection_detail: str | None
    pii_result: Literal['pass', 'flag', 'block']
    pii_types: list[str]
    policy_result: Literal['pass', 'flag', 'block']
    policy_violated_category: str | None
    risk_score: int  # 0–100
    overall_status: Literal['pass', 'flag', 'block']

# ── Pipeline Context (mutable accumulator) ────────────────────────────────────

@dataclass
class PipelineContext:
    request_id: str
    session_id: str
    original_prompt: str
    masked_prompt: str
    model_provider: str
    model_name: str
    kb_id: str | None
    policy: PolicySnapshot
    attempt_number: int = 1

    # Stage outputs (populated as stages complete)
    validation_result: PromptValidationResult | None = None
    llm_response_text: str | None = None
    llm_tokens_in: int | None = None
    llm_tokens_out: int | None = None
    llm_latency_ms: int | None = None
    claims: list[Claim] = field(default_factory=list)
    claim_results: list[ClaimVerificationResult] = field(default_factory=list)
    safety_results: list[SafetyFilterResult] = field(default_factory=list)
    confidence_score: ConfidenceScore | None = None
    guardrail_decision: GuardrailDecision | None = None
    fallback_strategy_applied: str | None = None

    # Trace accumulator
    trace_stages: list[TraceStage] = field(default_factory=list)
    stage_start_times: dict[str, float] = field(default_factory=dict)

    # Control flow flags
    is_terminal: bool = False     # True after block decision; halts orchestrator
    retry_requested: bool = False # True when decision calls for retry

@dataclass
class PolicySnapshot:
    accept_threshold: int   = 70
    warn_threshold: int     = 40
    block_threshold: int    = 0
    max_retries: int        = 2
    restricted_categories: list[str] = field(default_factory=list)
    allowed_topics: list[str]        = field(default_factory=list)
    fallback_priority: list[str]     = field(default_factory=lambda: [
        'retry_prompt', 'retry_lower_temp', 'rag_augmentation', 'alternate_model'
    ])
    module_flags: dict[str, bool] = field(default_factory=lambda: {
        'injection_detection': True,
        'pii_detection': True,
        'policy_filter': True,
        'hallucination_detection': True,
        'safety_filters': True,
    })
```

---

## 3. Guardrail Pipeline Orchestrator

The orchestrator is the sole entity responsible for stage sequencing, retry coordination, and terminal state detection. It does not contain any business logic — it is a control flow mechanism.

### 3.1 Orchestrator Algorithm

```python
class GuardrailPipelineOrchestrator:

    MAX_ABSOLUTE_RETRIES = 5  # hard ceiling, regardless of policy

    async def execute(self, context: PipelineContext) -> PipelineContext:
        max_retries = min(context.policy.max_retries, self.MAX_ABSOLUTE_RETRIES)

        while context.attempt_number <= max_retries + 1:
            context = await self._run_single_attempt(context)

            if context.is_terminal:
                break  # block or unrecoverable failure

            if not context.retry_requested:
                break  # accept or accept_with_warning

            if context.attempt_number > max_retries:
                # Retry budget exhausted
                context.guardrail_decision = GuardrailDecision(
                    decision_type='block',
                    reason='Maximum retries exceeded',
                    triggered_rule='MAX_RETRIES_EXCEEDED',
                    safety_filter_override=False,
                )
                context.is_terminal = True
                break

            # Apply fallback strategy and increment attempt
            context = await self.fallback_engine.apply(context)
            context.attempt_number += 1
            context.retry_requested = False

        return context

    async def _run_single_attempt(self, context: PipelineContext) -> PipelineContext:
        # Stage 1: Prompt Validation
        context = await self._run_stage(
            context, 'prompt_validation', 1,
            self.prompt_validation_engine.validate
        )
        if context.is_terminal:
            return self._fill_not_reached(context, from_stage_order=2)

        # Stage 2: LLM Generation
        context = await self._run_stage(
            context, 'llm_generation', 2,
            self.llm_execution_layer.generate
        )
        if context.is_terminal:
            return self._fill_not_reached(context, from_stage_order=3)

        # Stage 3 + 4: Hallucination Detection + Safety Filters (parallel if both enabled)
        if context.policy.module_flags['hallucination_detection']:
            hallucination_task = asyncio.create_task(
                self._run_stage(context, 'hallucination_detection', 3,
                                self.hallucination_engine.analyze)
            )
        if context.policy.module_flags['safety_filters']:
            safety_task = asyncio.create_task(
                self._run_stage(context, 'safety_filter_checks', 4,
                                self.safety_filter.analyze)
            )

        if context.policy.module_flags['hallucination_detection']:
            context = await hallucination_task
        if context.policy.module_flags['safety_filters']:
            context = await safety_task

        # Stage 5: Confidence Scoring
        context = await self._run_stage(
            context, 'confidence_score_calculation', 5,
            self.confidence_engine.compute
        )

        # Stage 6: Guardrail Decision
        context = await self._run_stage(
            context, 'guardrail_decision', 6,
            self.decision_engine.decide
        )

        return context

    async def _run_stage(
        self,
        context: PipelineContext,
        stage_name: str,
        stage_order: int,
        stage_fn: Callable
    ) -> PipelineContext:
        stage_start = time.monotonic()
        context.stage_start_times[stage_name] = stage_start
        try:
            context = await stage_fn(context)
            latency_ms = int((time.monotonic() - stage_start) * 1000)
            context.trace_stages.append(
                TraceStage(stage_name=stage_name, stage_order=stage_order,
                           stage_status='passed', stage_latency_ms=latency_ms,
                           attempt_number=context.attempt_number)
            )
        except PipelineStageError as e:
            latency_ms = int((time.monotonic() - stage_start) * 1000)
            context.trace_stages.append(
                TraceStage(stage_name=stage_name, stage_order=stage_order,
                           stage_status='failed', stage_latency_ms=latency_ms,
                           stage_metadata={'error': str(e)},
                           attempt_number=context.attempt_number)
            )
            context = self._handle_stage_failure(context, stage_name, e)
        return context

    def _fill_not_reached(self, context: PipelineContext, from_stage_order: int) -> PipelineContext:
        all_stages = [
            (2, 'llm_generation'), (3, 'claim_extraction'), (4, 'evidence_retrieval'),
            (5, 'claim_verification'), (6, 'safety_filter_checks'),
            (7, 'confidence_score_calculation'), (8, 'guardrail_decision')
        ]
        for order, name in all_stages:
            if order >= from_stage_order:
                context.trace_stages.append(
                    TraceStage(stage_name=name, stage_order=order,
                               stage_status='not_reached',
                               attempt_number=context.attempt_number)
                )
        return context
```

---

## 4. Prompt Validation Engine

### 4.1 Business Rules

| Rule | Condition | Result |
|---|---|---|
| R-PV-01 | Prompt is empty or whitespace-only | BLOCK (handled at API layer before engine) |
| R-PV-02 | Injection pattern detected with high confidence | BLOCK |
| R-PV-03 | Injection pattern detected with medium confidence | FLAG |
| R-PV-04 | PII detected (email, phone, SSN, credit card, API key) | FLAG (not block by default; configurable) |
| R-PV-05 | Prompt matches restricted content category | BLOCK |
| R-PV-06 | Risk score ≥ 80 (aggregate) | Elevates to BLOCK if not already blocked |
| R-PV-07 | All checks pass | PASS |

### 4.2 Injection Detector Algorithm

```python
class InjectionDetector:
    # High-confidence patterns → BLOCK
    BLOCK_PATTERNS = [
        r'ignore\s+(all\s+)?(previous|prior|above)\s+instructions',
        r'you\s+are\s+now\s+(a\s+)?(?!SentinelAI)',  # role override
        r'(system|assistant)\s*:\s*',                 # message boundary injection
        r'<\s*/?system\s*>',                          # XML role tags
        r'forget\s+your\s+(previous\s+)?(instructions|training)',
        r'do\s+anything\s+now',                       # DAN patterns
        r'jailbreak',
        r'pretend\s+you\s+(are|have\s+no)',
    ]

    # Medium-confidence patterns → FLAG
    FLAG_PATTERNS = [
        r'disregard\s+',
        r'bypass\s+(your\s+)?(safety|filter|guardrail)',
        r'act\s+as\s+if\s+you\s+(have\s+no|are\s+not)',
        r'hypothetically\s+speaking.*?instructions',
        r'roleplay\s+as',
        r'for\s+educational\s+purposes\s+only.*?(how|explain)',
    ]

    def check(self, prompt: str) -> InjectionCheckResult:
        prompt_lower = prompt.lower()
        normalized = re.sub(r'\s+', ' ', prompt_lower)

        for pattern in self.BLOCK_PATTERNS:
            if re.search(pattern, normalized, re.IGNORECASE):
                return InjectionCheckResult(
                    status='block',
                    detail=f'Injection pattern detected: {pattern[:40]}'
                )

        flag_hits = []
        for pattern in self.FLAG_PATTERNS:
            if re.search(pattern, normalized, re.IGNORECASE):
                flag_hits.append(pattern[:40])

        if flag_hits:
            return InjectionCheckResult(status='flag', detail=f'Suspicious patterns: {flag_hits}')

        return InjectionCheckResult(status='pass', detail=None)
```

### 4.3 PII Detector Algorithm

```python
class PIIDetector:
    PATTERNS = {
        'email':       r'\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Z|a-z]{2,}\b',
        'phone_us':    r'\b(\+1[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b',
        'ssn':         r'\b\d{3}[-\s]?\d{2}[-\s]?\d{4}\b',
        'credit_card': r'\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13})\b',
        'api_key':     r'\b(sk-[a-zA-Z0-9]{32,}|AIza[a-zA-Z0-9_\-]{35}|[a-zA-Z0-9]{32,40})\b',
        'ipv4':        r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
    }

    def check(self, prompt: str) -> PIICheckResult:
        detected_types = []
        masked_text = prompt

        for pii_type, pattern in self.PATTERNS.items():
            matches = list(re.finditer(pattern, masked_text))
            if matches:
                detected_types.append(pii_type)
                for match in reversed(matches):  # reverse to preserve positions
                    replacement = f'[{pii_type.upper()}_REDACTED]'
                    masked_text = masked_text[:match.start()] + replacement + masked_text[match.end():]

        if detected_types:
            return PIICheckResult(
                status='flag',
                pii_types=detected_types,
                masked_text=masked_text
            )
        return PIICheckResult(status='pass', pii_types=[], masked_text=prompt)
```

### 4.4 Risk Scorer Algorithm

```python
class RiskScorer:
    WEIGHTS = {
        'injection_block': 80,
        'injection_flag':  40,
        'pii_flag':        20,
        'policy_block':    70,
        'policy_flag':     35,
    }

    def score(self, validation_sub_results: list[SubCheckResult]) -> int:
        total = 0
        for result in validation_sub_results:
            key = f'{result.check_type}_{result.status}'
            total += self.WEIGHTS.get(key, 0)
        return min(total, 100)
```

### 4.5 Overall Prompt Validation Status

```
overall_status = BLOCK  if any sub-check == BLOCK or risk_score >= 80
overall_status = FLAG   if any sub-check == FLAG (and no block)
overall_status = PASS   otherwise
```

---

## 5. LLM Execution Layer

### 5.1 Business Rules

| Rule | Condition | Action |
|---|---|---|
| R-LLM-01 | Ollama selected | Route to OllamaAdapter with configured model |
| R-LLM-02 | OpenAI selected + key present | Route to OpenAIAdapter with user key |
| R-LLM-03 | OpenAI selected + key absent | Return AUTH_REQUIRED error immediately |
| R-LLM-04 | LLM returns empty string | Treat as generation failure |
| R-LLM-05 | HTTP timeout after `llm_timeout_seconds` | Raise `LLMTimeoutError` |
| R-LLM-06 | Provider HTTP 429 | Retry up to 2 times with exponential backoff (1s, 2s); then raise `RateLimitError` |
| R-LLM-07 | Provider HTTP 401 | Raise `AuthenticationError` immediately (no retry) |
| R-LLM-08 | Response text returned | Populate `context.llm_response_text`, `tokens_in`, `tokens_out`, `llm_latency_ms` |

### 5.2 Adapter Interface

```python
class LLMAdapter(Protocol):
    async def complete(
        self,
        prompt: str,
        model_name: str,
        temperature: float,
        max_tokens: int,
        timeout_seconds: float,
        api_key: str | None = None,
    ) -> LLMResult:
        ...

@dataclass
class LLMResult:
    text: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    model_name: str
    provider: str
```

### 5.3 Retry with Backoff (within LLM layer)

```python
async def complete_with_retry(self, adapter, **kwargs) -> LLMResult:
    backoff_seconds = [1.0, 2.0]
    for attempt, wait in enumerate(backoff_seconds + [None]):
        try:
            result = await adapter.complete(**kwargs)
            if not result.text.strip():
                raise EmptyResponseError("LLM returned empty response")
            return result
        except RateLimitError:
            if wait is None:
                raise
            await asyncio.sleep(wait)
        except (AuthenticationError, LLMTimeoutError):
            raise  # no retry for auth errors or timeouts
```

---

## 6. Hallucination Detection Engine

### 6.1 Claim Extractor

Claims are extracted via a targeted LLM prompt that instructs the model to return a JSON list of factual assertions from the response text. This avoids brittle regex-based NLP for entity and claim detection.

```python
CLAIM_EXTRACTION_PROMPT = """
You are a fact-extraction assistant. Given the following text, extract all discrete factual claims.
A factual claim is a statement that asserts something verifiable about the world:
- Named entities with attributes (e.g., "Einstein was born in 1879")
- Statistics or numeric assertions (e.g., "The population is 8 billion")
- Dates and historical events (e.g., "World War II ended in 1945")
- Causal assertions (e.g., "Smoking causes lung cancer")

Do NOT include:
- Opinions or recommendations
- Conversational filler
- Questions

Return ONLY a JSON array of strings, one string per claim. If no factual claims exist, return [].

Text:
{response_text}
"""

class ClaimExtractor:
    async def extract(self, response_text: str) -> list[Claim]:
        if len(response_text.strip()) < 20:
            return []  # Too short to contain verifiable claims

        raw_json = await self.llm_adapter.complete(
            prompt=CLAIM_EXTRACTION_PROMPT.format(response_text=response_text),
            model_name=self.claim_model,
            temperature=0.0,    # deterministic
            max_tokens=512,
            timeout_seconds=10.0
        )
        try:
            claim_texts: list[str] = json.loads(raw_json.text)
        except json.JSONDecodeError:
            # Attempt to extract JSON array from response using regex fallback
            match = re.search(r'\[.*?\]', raw_json.text, re.DOTALL)
            if match:
                claim_texts = json.loads(match.group())
            else:
                return []  # Cannot parse; treat as no claims

        return [
            Claim(index=i, text=text.strip(), entity_type=None)
            for i, text in enumerate(claim_texts)
            if text.strip()
        ]
```

### 6.2 Claim Verifier Algorithm

```python
CLAIM_VERIFICATION_PROMPT = """
You are a fact-checking assistant. Determine whether the following claim is supported, unsupported, or contradicted by the provided evidence.

Claim: {claim_text}

Evidence:
{evidence_text}

Respond with ONLY a JSON object:
{{
  "status": "supported" | "unsupported" | "contradicted",
  "justification": "<one sentence explanation>"
}}

If no evidence is provided, always return "unsupported".
"""

class ClaimVerifier:
    async def verify_batch(
        self, claims: list[Claim], evidence_map: dict[int, list[Evidence]]
    ) -> list[ClaimVerificationResult]:
        """
        Batch up to MAX_BATCH_SIZE claims into a single prompt to reduce LLM calls.
        Falls back to individual verification if batch parse fails.
        """
        results = []
        for claim in claims:
            evidence = evidence_map.get(claim.index, [])
            evidence_text = self._format_evidence(evidence)

            if not evidence:
                results.append(ClaimVerificationResult(
                    claim=claim,
                    status='unsupported',
                    evidence=[],
                    justification='No evidence retrieved from knowledge base.',
                    confidence_contribution=0.0
                ))
                continue

            raw = await self.llm_adapter.complete(
                prompt=CLAIM_VERIFICATION_PROMPT.format(
                    claim_text=claim.text,
                    evidence_text=evidence_text
                ),
                model_name=self.verify_model,
                temperature=0.0,
                max_tokens=256,
                timeout_seconds=8.0
            )

            try:
                parsed = json.loads(raw.text)
                status = parsed.get('status', 'unverified')
                justification = parsed.get('justification', '')
                if status not in ('supported', 'unsupported', 'contradicted'):
                    status = 'unverified'
            except json.JSONDecodeError:
                status = 'unverified'
                justification = 'Verification parse error.'

            results.append(ClaimVerificationResult(
                claim=claim,
                status=status,
                evidence=evidence,
                justification=justification,
                confidence_contribution=self._score_claim(status, evidence)
            ))

        return results

    def _score_claim(self, status: str, evidence: list[Evidence]) -> float:
        """
        Returns a 0.0–1.0 score for this claim's contribution.
        Supported + high similarity → near 1.0
        Unsupported → 0.0
        Contradicted → negative contribution (capped at -0.5)
        """
        if status == 'supported':
            avg_similarity = sum(e.relevance_score for e in evidence) / len(evidence)
            return 0.5 + (avg_similarity * 0.5)  # 0.5–1.0 range
        elif status == 'unsupported':
            return 0.0
        elif status == 'contradicted':
            return -0.3  # penalize but don't make it unboundedly negative
        else:
            return 0.1  # unverified: slight positive (benefit of doubt)

    def _format_evidence(self, evidence: list[Evidence]) -> str:
        if not evidence:
            return "No evidence available."
        lines = []
        for i, e in enumerate(evidence[:5], 1):  # max 5 evidence chunks
            lines.append(f"[{i}] (Source: {e.document_filename}) {e.chunk_text[:300]}")
        return "\n".join(lines)
```

---

## 7. Confidence Scoring Engine

### 7.1 Signal Definitions

| Signal | Source | Weight | Range | Description |
|---|---|---|---|---|
| `evidence_similarity` | Avg top-1 evidence relevance across supported claims | 0.35 | 0.0–1.0 | How strongly the evidence matches the claims |
| `claim_verification_ratio` | (supported - contradicted) / total_claims | 0.35 | -1.0–1.0 | Ratio of supported to contradicted/unsupported |
| `claim_density_penalty` | Function of claim count relative to response length | 0.10 | 0.0–1.0 (inverted) | High claim density relative to response length → lower score |
| `safety_penalty` | 0 if no filters triggered; -0.3 per filter flagged, up to -1.0 | 0.20 | -1.0–0.0 | Safety filter outcomes |

### 7.2 Scoring Algorithm

```python
class ConfidenceScoringEngine:

    SIGNAL_WEIGHTS = {
        'evidence_similarity':      0.35,
        'claim_verification_ratio': 0.35,
        'claim_density_penalty':    0.10,
        'safety_penalty':           0.20,
    }

    def compute(self, context: PipelineContext) -> PipelineContext:
        signals: dict[str, float] = {}

        # Signal 1: Evidence Similarity
        if context.claim_results:
            supported = [r for r in context.claim_results if r.status == 'supported']
            if supported:
                signals['evidence_similarity'] = sum(
                    max((e.relevance_score for e in r.evidence), default=0.0)
                    for r in supported
                ) / len(supported)
            else:
                signals['evidence_similarity'] = 0.0
        else:
            signals['evidence_similarity'] = 0.5  # neutral: no claims to verify

        # Signal 2: Claim Verification Ratio
        if context.claim_results:
            n = len(context.claim_results)
            n_supported    = sum(1 for r in context.claim_results if r.status == 'supported')
            n_contradicted = sum(1 for r in context.claim_results if r.status == 'contradicted')
            # Normalize to 0.0–1.0 (from -1.0–1.0)
            raw_ratio = (n_supported - n_contradicted) / n
            signals['claim_verification_ratio'] = (raw_ratio + 1.0) / 2.0
        else:
            signals['claim_verification_ratio'] = 0.5  # neutral

        # Signal 3: Claim Density Penalty
        if context.llm_response_text and context.claim_results:
            response_word_count = len(context.llm_response_text.split())
            claim_count = len(context.claim_results)
            claims_per_100_words = (claim_count / max(response_word_count, 1)) * 100
            # >5 claims per 100 words is considered high density
            density_score = max(0.0, 1.0 - (claims_per_100_words / 10.0))
            signals['claim_density_penalty'] = density_score
        else:
            signals['claim_density_penalty'] = 1.0  # no penalty

        # Signal 4: Safety Penalty
        flagged_filters = [r for r in context.safety_results if r.result == 'flagged']
        safety_penalty = max(-1.0, len(flagged_filters) * -0.3)
        # Normalize to 0.0–1.0 for weight aggregation
        signals['safety_penalty'] = (safety_penalty + 1.0) / 1.0  # 0.0 if fully penalized

        # Weighted aggregation
        raw_score: float = sum(
            self.SIGNAL_WEIGHTS[k] * v for k, v in signals.items()
        )

        # Clamp to 0.0–1.0 then scale to 0–100
        clamped = max(0.0, min(1.0, raw_score))
        final_score = int(round(clamped * 100))

        # Label classification using policy thresholds
        policy = context.policy
        if final_score >= policy.accept_threshold:
            label = 'high'
        elif final_score >= policy.warn_threshold:
            label = 'medium'
        else:
            label = 'low'

        context.confidence_score = ConfidenceScore(
            value=final_score,
            label=label,
            signal_breakdown={k: round(v, 4) for k, v in signals.items()}
        )
        return context
```

---

## 8. Guardrail Decision Engine

### 8.1 Decision Logic (Deterministic)

```python
class GuardrailDecisionEngine:

    def decide(self, context: PipelineContext) -> PipelineContext:
        policy = context.policy
        score = context.confidence_score.value
        flagged_safety = [r for r in context.safety_results if r.result == 'flagged']

        # Rule priority order (highest priority first):

        # Rule 1: Safety filter override (always takes precedence for block)
        if flagged_safety:
            most_severe = max(flagged_safety, key=lambda r: r.score)
            if most_severe.score >= 0.7:  # high confidence safety flag → block
                context.guardrail_decision = GuardrailDecision(
                    decision_type='block',
                    reason=f'Safety filter triggered: {most_severe.filter_name}',
                    triggered_rule='SAFETY_FILTER_BLOCK',
                    safety_filter_override=True,
                )
                context.is_terminal = True
                return context
            else:
                # Low-confidence safety flag → warn but don't block
                pass  # falls through to confidence-based decision with a warning flag

        # Rule 2: Prompt validation block (should already be terminal; defensive check)
        if context.validation_result and context.validation_result.overall_status == 'block':
            context.guardrail_decision = GuardrailDecision(
                decision_type='block',
                reason=f'Prompt blocked at validation: {context.validation_result.injection_detail or context.validation_result.policy_violated_category}',
                triggered_rule='PROMPT_VALIDATION_BLOCK',
                safety_filter_override=False,
            )
            context.is_terminal = True
            return context

        # Rule 3: Confidence-based decision
        if score >= policy.accept_threshold and not flagged_safety:
            context.guardrail_decision = GuardrailDecision(
                decision_type='accept',
                reason=f'Confidence score {score} meets accept threshold {policy.accept_threshold}',
                triggered_rule=None,
                safety_filter_override=False,
            )

        elif score >= policy.warn_threshold:
            # Accept with warning (low-confidence safety flag also lands here)
            warning_reason = (
                f'Safety filter low-confidence flag: {flagged_safety[0].filter_name}. '
                if flagged_safety else ''
            )
            warning_reason += f'Confidence score {score} is in warn range [{policy.warn_threshold},{policy.accept_threshold})'
            context.guardrail_decision = GuardrailDecision(
                decision_type='accept_with_warning',
                reason=warning_reason,
                triggered_rule='CONFIDENCE_WARN_THRESHOLD',
                safety_filter_override=bool(flagged_safety),
            )

        elif score >= policy.block_threshold:
            # Score is low enough to trigger retry
            # Select retry strategy from fallback priority
            next_strategy = self._select_fallback_strategy(context)
            if next_strategy and context.attempt_number <= policy.max_retries:
                context.guardrail_decision = GuardrailDecision(
                    decision_type=self._strategy_to_decision_type(next_strategy),
                    reason=f'Confidence score {score} below warn threshold {policy.warn_threshold}; attempting fallback: {next_strategy}',
                    triggered_rule='CONFIDENCE_RETRY_THRESHOLD',
                    safety_filter_override=False,
                )
                context.retry_requested = True
            else:
                context.guardrail_decision = GuardrailDecision(
                    decision_type='block',
                    reason=f'Confidence score {score} below threshold; no further fallback strategies available',
                    triggered_rule='CONFIDENCE_BLOCK_THRESHOLD',
                    safety_filter_override=False,
                )
                context.is_terminal = True

        else:
            # score < block_threshold (threshold configured at 0 by default; this branch
            # only activates if the operator raises block_threshold above 0)
            context.guardrail_decision = GuardrailDecision(
                decision_type='block',
                reason=f'Confidence score {score} below block threshold {policy.block_threshold}',
                triggered_rule='CONFIDENCE_ABSOLUTE_BLOCK',
                safety_filter_override=False,
            )
            context.is_terminal = True

        return context

    def _select_fallback_strategy(self, context: PipelineContext) -> str | None:
        for strategy in context.policy.fallback_priority:
            if strategy == 'rag_augmentation' and not context.kb_id:
                continue  # skip RAG if no KB is active
            if strategy not in context.strategies_attempted:
                return strategy
        return None

    def _strategy_to_decision_type(self, strategy: str) -> str:
        mapping = {
            'retry_prompt':     'retry_prompt',
            'retry_lower_temp': 'retry_prompt',
            'rag_augmentation': 'trigger_rag',
            'alternate_model':  'retry_alternate_model',
        }
        return mapping.get(strategy, 'retry_prompt')
```

---

## 9. Fallback Strategy Engine

### 9.1 Strategy Implementations

```python
class FallbackStrategyEngine:

    STRICTER_PROMPT_SUFFIX = (
        "\n\nIMPORTANT: Respond only with verified factual information. "
        "If you are uncertain, explicitly state your uncertainty. "
        "Do not fabricate facts, statistics, or citations."
    )

    async def apply(self, context: PipelineContext) -> PipelineContext:
        strategy = context.guardrail_decision.decision_type
        context.strategies_attempted.add(strategy)

        if strategy == 'retry_prompt':
            context.original_prompt = context.original_prompt + self.STRICTER_PROMPT_SUFFIX
            context.fallback_strategy_applied = 'retry_prompt'

        elif strategy == 'retry_lower_temp':
            # Lower temperature is passed via context; LLMExecutionLayer reads it
            context.llm_temperature = max(0.0, context.llm_temperature - 0.3)
            context.fallback_strategy_applied = 'retry_lower_temp'

        elif strategy == 'trigger_rag':
            # Retrieve context for the prompt and inject it
            if context.kb_id:
                prompt_evidence = await self.retrieval_layer.retrieve(
                    query=context.original_prompt,
                    kb_id=context.kb_id,
                    top_k=3
                )
                evidence_block = "\n".join(
                    f"[Evidence {i+1}]: {e.chunk_text[:400]}"
                    for i, e in enumerate(prompt_evidence)
                )
                context.original_prompt = (
                    f"Use the following evidence to answer accurately:\n\n"
                    f"{evidence_block}\n\n"
                    f"Question: {context.original_prompt}"
                )
                context.fallback_strategy_applied = 'rag_augmentation'
            else:
                # KB not available; skip to next strategy
                context.strategies_attempted.add('trigger_rag')
                next_strategy = self.decision_engine._select_fallback_strategy(context)
                if next_strategy:
                    return await self.apply_strategy(context, next_strategy)

        elif strategy == 'retry_alternate_model':
            # Switch from local to OpenAI (if key available) or vice versa
            if context.model_provider == 'ollama' and context.openai_key_available:
                context.model_provider = 'openai'
                context.model_name = 'gpt-4o-mini'
            else:
                # No alternate model; cannot proceed with this strategy
                context.fallback_strategy_applied = None

        # Reset stage outputs for the next attempt
        context.llm_response_text = None
        context.claims = []
        context.claim_results = []
        context.safety_results = []
        context.confidence_score = None
        context.guardrail_decision = None
        context.retry_requested = False

        return context
```

---

## 10. Idempotency Safeguards

| Operation | Idempotency Mechanism |
|---|---|
| Request submission | `request_id` is server-generated UUID on receipt. Duplicate detection via `prompt_hash` check within the same session (informational only; not rejected). |
| KB document upload | `storage_path` is unique-constrained in the DB. Re-uploading the same file from the same session creates a new document record (not overwrite), because filenames can differ. |
| Analytics counter update | UPSERT with atomic increment. A counter update applied twice would double-count; the application layer ensures the update is applied exactly once per request completion (using a `status` flag check before the write). |
| Retry attempts | Each retry is a new pipeline cycle with a new `attempt_number`. The orchestrator tracks `attempt_number` in the context to prevent the same strategy from being applied twice (via `strategies_attempted` set). |
| Claim verification | Verification is deterministic (temperature=0). Re-running verification on the same claim with the same evidence produces the same result. No deduplication is needed. |

---

## 11. Concurrency Safety Rules

| Scenario | Risk | Mitigation |
|---|---|---|
| Concurrent requests modifying the same FAISS index | Index corruption | A per-KB asyncio.Lock is acquired before any write to the FAISS index. Reads (queries) do not acquire the lock (FAISS reads are thread-safe on CPU mode). |
| Concurrent analytics counter updates for the same session | Race condition → lost updates | DB-level UPSERT with atomic increment. SQLite's WAL mode serializes writes. PostgreSQL uses SELECT FOR UPDATE or advisory locks. |
| Multiple indexing jobs for the same document | Duplicate chunks in FAISS | The indexing worker is a single serial coroutine (queue consumer). Only one job runs at a time per queue. |
| Concurrent session creation with the same session_id | PK conflict | Session creation uses INSERT OR IGNORE; the application layer then SELECT the existing row. |
| Concurrent WebSocket events from the same request | Out-of-order delivery | Events are serialized through a per-request asyncio.Queue with a single writer (the orchestrator) and a single reader (the WebSocket handler). |

---

## 12. Failure Recovery Strategy (Domain Layer)

```
Stage failure handling logic:

IF stage failure is RECOVERABLE (vector store timeout, embedding model slow):
  → Log warning, substitute neutral default value, continue pipeline
  → Mark stage as 'failed' in trace with error detail
  → Confidence score computed from reduced signal set

IF stage failure is UNRECOVERABLE (LLM completely unavailable, DB write failed after retries):
  → Mark context.is_terminal = True
  → Set guardrail_decision = Block with reason = PIPELINE_FAILURE
  → Persist partial trace up to failed stage
  → Return error response to client with request_id for reference

IF LLM generation fails:
  → Invoke FallbackStrategyEngine
  → If all strategies exhausted → Block with MAX_RETRIES_EXCEEDED

IF claim extraction fails (parse error, model returns invalid JSON):
  → Log error
  → context.claims = [] (empty)
  → Hallucination detection skipped (stage marked 'skipped')
  → Confidence computed without claim signal (evidence_similarity = 0.5 neutral)
  → Pipeline continues

IF safety filter model unavailable:
  → Log critical error
  → All safety signals set to neutral (not flagged)
  → Stage marked 'skipped' in trace with reason
  → This is the only case where safety filtering is effectively bypassed;
     the UI displays a WARNING banner: "Safety filters were unavailable for this request"
```

---

## 13. Edge Case Matrix

| Edge Case | Handling |
|---|---|
| Prompt is a single word | Passes all validation; LLM generates response; claim extractor likely returns []; confidence scored from safety signals only |
| Response is 10,000 characters with 30+ claims | All claims processed; high claim density signal penalizes score; total verification latency may exceed budget — capped at max 20 claims processed; remaining claims logged as 'unverified' |
| KB has 0 indexed documents | Evidence retrieval skipped; all claims → 'unsupported'; confidence scored without evidence signal |
| All claims are supported at high similarity | Score = 90+; decision = accept; no retry |
| All claims are contradicted | Score < 20; decision = block (assuming default thresholds) |
| Claim text is identical to evidence text (verbatim copy) | Cosine similarity ≈ 1.0; marked 'supported'; correct behavior — the LLM reproduced source material accurately |
| LLM generates a response with no sentences (e.g., a JSON blob) | Claim extractor returns []; pipeline continues; confidence neutral |
| Policy accept_threshold set to 0 | Every response is accepted; score computed and stored but never blocks; analytics still track score distribution |
| Policy accept_threshold set to 100 | Only a score of exactly 100 would be accepted; in practice, all responses are blocked or warned; user receives block with CONFIDENCE_BLOCK_THRESHOLD reason |
| Retry produces a worse score than the original | The second attempt's result replaces the first; there is no score comparison across attempts. The final attempt's result is always used. (Future: best-of-N selection can be added.) |
| Safety filter model returns score of exactly 0.7 | The threshold check is `>= 0.7` → triggers block. Threshold is configurable in the safety adapter. |
| Knowledge base document is empty (0 bytes or whitespace only) | DocumentChunker returns 0 chunks; document is marked 'ready' with chunk_count=0; retrieval against this KB returns empty results |
| OpenAI API key is valid but account has no quota | OpenAI returns HTTP 429 (quota exceeded, not rate limit); treated as RateLimitError; retried twice; then fails with PROVIDER_RATE_LIMITED |
| Prompt contains only emoji or non-ASCII characters | PII detection runs (no matches); injection detection runs (no matches); LLM processes normally; claim extraction likely returns [] |
| Very high claim density response (30 claims, 200 words) | Claim density penalty drives score down; first 20 claims are processed; remaining 10 are marked 'unverified'; UI shows note about truncated claim processing |
