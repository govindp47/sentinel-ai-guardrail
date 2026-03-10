# SentinelAI Guardrail — Product Specification (PRD)

**Version:** 1.0  
**Status:** Draft  
**Document Type:** Product Requirements Document  
**Audience:** Product, Engineering, Design

---

## Table of Contents

1. [Product Overview](#1-product-overview)
2. [Problem Definition](#2-problem-definition)
3. [Product Goals](#3-product-goals)
4. [Target Users & Personas](#4-target-users--personas)
5. [Product Scope](#5-product-scope)
6. [Core Product Features](#6-core-product-features)
7. [UX Architecture](#7-ux-architecture)
8. [Detailed User Flows](#8-detailed-user-flows)
9. [UI / UX Specifications](#9-ui--ux-specifications)
10. [Functional Requirements](#10-functional-requirements)
11. [Non-Functional Product Requirements](#11-non-functional-product-requirements)
12. [External Integrations (Product Perspective)](#12-external-integrations-product-perspective)
13. [Edge Cases & Error Scenarios](#13-edge-cases--error-scenarios)
14. [Privacy & User Data Considerations](#14-privacy--user-data-considerations)
15. [Development Phases (Product Roadmap)](#15-development-phases-product-roadmap)
16. [Future Enhancements](#16-future-enhancements)
17. [Open Questions / Assumptions](#17-open-questions--assumptions)

---

## 1. Product Overview

### Product Summary

SentinelAI Guardrail is a model-agnostic AI reliability middleware that intercepts requests between client applications and LLM providers. It validates incoming prompts, runs the LLM, extracts claims from the response, verifies those claims against a knowledge base, applies safety filters, computes a confidence score, and enforces a guardrail decision — all before returning the result to the caller.

The product is delivered as two surfaces:

- **Public Playground** — a free, open web UI where any user can submit prompts and observe the full guardrail pipeline in action without signing up.
- **Developer REST API** — a programmatic interface that developers integrate into their own LLM-powered applications.

### Value Proposition

SentinelAI Guardrail provides transparent, observable AI reliability infrastructure. It is the only layer a developer needs to detect hallucinations, enforce safety policies, and understand why an AI response was accepted, modified, or blocked — without replacing or retraining the underlying LLM.

### Target Users

- AI application developers building LLM-powered products
- Backend engineers integrating LLM APIs into services
- ML / LLM engineers evaluating AI safety mechanisms
- AI platform teams benchmarking guardrail systems
- Recruiters and engineers assessing AI reliability architectures
- Students and learners exploring AI safety infrastructure

---

## 2. Problem Definition

### Current User Pain Points

- **No prompt validation before LLM calls.** Developers send raw user input directly to LLM APIs with no checks for prompt injection, sensitive data exposure, or policy violations.
- **No hallucination visibility.** LLM responses containing fabricated facts are indistinguishable from accurate ones at the application layer.
- **No structured safety layer.** Toxic, harmful, or policy-violating outputs reach end users unless developers build custom filters, which most do not.
- **No confidence signal.** Applications have no programmatic indicator of how reliable a given LLM response is.
- **No observability into the generation pipeline.** Developers cannot inspect how a response was produced, verified, or rejected.
- **No low-cost demonstration infrastructure.** Existing AI safety tools are either proprietary, expensive, or require significant setup to evaluate.

### Why Solving This Problem Matters

LLM outputs directly affect user trust and product safety. Without a reliability layer, hallucinated facts propagate into user-facing products, unsafe content reaches end users, and developers have no structured way to debug or improve response quality. SentinelAI Guardrail makes the reliability pipeline visible, testable, and integrable without requiring developers to build these systems from scratch.

---

## 3. Product Goals

### Primary Goals

- Provide a working, publicly accessible demonstration of an AI guardrail pipeline.
- Enable developers to integrate prompt validation, hallucination detection, safety filtering, and confidence scoring via a simple API.
- Default to entirely free, local model execution with no API cost requirement.
- Make every stage of the guardrail pipeline inspectable by the user.

### Secondary Goals

- Allow side-by-side comparison between local models and OpenAI models when users supply their own API key.
- Serve as a portfolio and evaluation artifact for engineers and recruiters assessing AI reliability architecture.
- Provide an educational surface for students learning AI safety infrastructure patterns.

### Success Metrics (Product-Level KPIs)

| Metric | Target |
|---|---|
| Playground requests processed | Measurable from day one |
| Guardrail pipeline completion rate | ≥ 95% of submitted requests reach a final decision |
| Hallucination detection trigger rate | Tracked per model, per session |
| Guardrail decision distribution | Breakdown of Accept / Warn / Retry / Block decisions logged |
| Evidence retrieval success rate | % of claims for which supporting evidence is retrieved |
| API integration requests | Count of developer API calls outside of playground |
| Execution trace views | Count of users who expand and inspect trace details |
| Mean pipeline latency | Tracked and surfaced in the UI |

---

## 4. Target Users & Personas

### Persona 1 — The Integration Engineer

**Description:** A backend or full-stack developer building an LLM-powered feature (chatbot, Q&A, summarization) inside an existing application.

**Motivations:**

- Ship LLM features reliably without building safety layers from scratch.
- Understand when and why the LLM is producing bad output.
- Have a drop-in middleware layer they can configure quickly.

**Problems they face:**

- No guardrails on production LLM calls today.
- No visibility into hallucination rate across prompts.
- No structured error handling when the LLM returns unsafe content.

**Typical usage scenarios:**

- Sends test prompts through the playground to validate guardrail behavior before integrating the API.
- Uses the execution trace to understand why a specific response was flagged.
- Reads the developer API docs and integrates the SDK into their service.

---

### Persona 2 — The ML / LLM Engineer

**Description:** An engineer evaluating AI safety tooling and reliability patterns for a team or platform.

**Motivations:**

- Benchmark different LLM models on hallucination rate and response safety.
- Understand how claim extraction, evidence retrieval, and verification work in practice.
- Identify patterns in guardrail triggers across different prompt types.

**Problems they face:**

- No simple open system to test and compare guardrail behavior across models.
- Existing tools require significant infrastructure or are behind paywalls.
- Limited access to observable, explainable AI safety pipelines.

**Typical usage scenarios:**

- Submits varied prompts across local and OpenAI models to compare hallucination rates.
- Inspects the Analytics Dashboard for model reliability comparisons.
- Reviews the Audit Trail for specific request traces.

---

### Persona 3 — The Recruiter / Technical Evaluator

**Description:** A technical recruiter or senior engineer reviewing SentinelAI Guardrail as a portfolio or demonstration artifact.

**Motivations:**

- Understand the architecture and design decisions behind the system.
- Confirm the system works end-to-end by testing it live.
- Evaluate the depth and breadth of the AI reliability pipeline.

**Problems they face:**

- No quick way to evaluate a developer's AI infrastructure work without running it locally.
- Portfolio projects often lack a working public interface.

**Typical usage scenarios:**

- Opens the public playground and submits several prompts.
- Clicks through the execution trace and evidence view.
- Reviews the Analytics Dashboard for aggregate metrics.

---

### Persona 4 — The AI Safety Learner

**Description:** A student or junior developer learning about AI safety, hallucination detection, and reliability infrastructure.

**Motivations:**

- Understand how guardrail systems work in practice.
- See a real implementation of claim verification and confidence scoring.
- Learn from an observable, documented pipeline.

**Problems they face:**

- Most AI safety content is theoretical with no runnable reference implementation.
- Existing tools are too complex or too expensive to experiment with.

**Typical usage scenarios:**

- Submits prompts and inspects the step-by-step execution trace.
- Toggles individual guardrail modules on and off to observe effects.
- Explores the knowledge base management screen to understand retrieval.

---

## 5. Product Scope

### In Scope

- Public web playground (no account required)
- Prompt validation pipeline (injection detection, PII/secret detection, policy filtering, risk scoring)
- LLM execution layer supporting local models by default and optional OpenAI via user-supplied API key
- Hallucination detection pipeline (claim extraction, evidence retrieval, LLM-based verification, confidence scoring)
- Output safety filters (toxicity, hate speech, harmful instruction detection)
- Guardrail decision engine (Accept / Accept with Warning / Retry / Block)
- Fallback strategy execution (retry with stricter prompt, lower temperature, alternate model, RAG augmentation)
- Confidence scoring engine producing a final reliability score per response
- Execution trace viewer (step-by-step pipeline visualization in the UI)
- Audit trail per request (prompt, response, evidence, decision, score)
- Analytics dashboard (hallucination rate, guardrail trigger frequency, confidence distribution, latency, cost)
- Request Explorer (search by request ID, inspect full trace)
- Knowledge Base Management UI (upload documents, preview chunking, view indexing status)
- Policy Configuration panel (configurable guardrail rules, confidence thresholds, allowed/restricted topics)
- Developer REST API for programmatic integration
- Developer SDK (client libraries, async support, error handling)
- Observability and logging (request logs, token usage, latency, guardrail decisions, failure reasons)

### Out of Scope (Non Goals)

- Training or fine-tuning custom foundation models
- Building a consumer chatbot or conversational product
- Replacing or competing with existing LLM providers
- Fully autonomous AI agent workflows
- Large-scale SaaS platform with billing, subscriptions, or multi-tenant accounts
- Mobile native applications
- Custom enterprise SSO or access control systems
- Real-time collaborative editing of prompts or policies
- Any form of paid tier in the initial release

---

## 6. Core Product Features

---

### Feature 1 — Prompt Validation Engine

**Description:** Before the prompt reaches the LLM, the system analyzes it for injection attempts, sensitive data, policy violations, and assigns a risk score.

**User Value:** Prevents malformed, dangerous, or policy-violating prompts from reaching the model, reducing attack surface and compliance risk.

**Functional Behavior:**

- On prompt submission, the system runs four sequential sub-checks in order: injection detection → PII/secret detection → policy filtering → risk scoring.
- Each sub-check produces a result: Pass, Flag, or Block.
- A Block result on any sub-check halts execution and returns a blocked response with the reason displayed.
- A Flag result allows execution to continue but records the flag in the audit trail.
- A numeric risk score (0–100) is computed and attached to the request record.
- Results of all sub-checks are surfaced in the Guardrail Analysis Panel.

**Feature Rules and Constraints:**

- Prompt validation must complete before LLM generation begins.
- PII detection covers at minimum: email addresses, phone numbers, credit card numbers, Social Security Numbers, and API keys/tokens.
- Injection detection targets: prompt override attempts, role-hijacking patterns, jailbreak phrasing.
- The user must be able to see which specific check triggered a flag or block.

**Edge Cases:**

- Prompt contains no detectable issues: all checks pass, pipeline proceeds normally.
- Prompt is entirely blocked: no LLM call is made; user sees a clear blocked state with reason.
- PII detected but not a block-level risk: prompt proceeds with a flag logged; playground displays a PII warning indicator.
- Prompt is empty or whitespace-only: validation catches this as an input error before any checks run.

---

### Feature 2 — LLM Execution Layer

**Description:** A model-agnostic execution layer that routes the validated prompt to the selected LLM, manages retries, timeouts, and token tracking.

**User Value:** Abstracts provider differences so that users and developers interact with a single consistent interface regardless of the underlying model.

**Functional Behavior:**

- User selects a model from the playground dropdown: Local Model (default) or OpenAI (requires user-supplied API key).
- If OpenAI is selected and no API key is provided, the system prompts the user to enter one before proceeding.
- The API key is used only for the current request and is not stored.
- The system applies a configurable timeout per request. If the timeout is exceeded, the request fails gracefully with a timeout error.
- If the LLM call fails (non-timeout error), the system retries up to a configurable maximum number of attempts before declaring failure.
- Token usage (input and output) is tracked per request and recorded in the audit trail.

**Feature Rules and Constraints:**

- Local model is always the default selection.
- OpenAI API key must not be persisted beyond the current session.
- Token count is always surfaced in the execution trace and audit record.
- If no model is available (e.g., local service is down), the user receives a clear error with a suggestion to check model availability.

**Edge Cases:**

- User provides an invalid OpenAI API key: system returns an authentication error from the provider; user is notified to check their key.
- LLM returns an empty response: system treats this as a generation failure and applies the fallback strategy.
- Request times out: pipeline halts at the LLM stage; trace shows timeout at generation step; fallback may retry.

---

### Feature 3 — Hallucination Detection Engine

**Description:** After LLM generation, the system extracts factual claims from the response, retrieves supporting evidence, and uses a verification step to assess each claim's accuracy.

**User Value:** Makes hallucinations visible and measurable. Developers and users can see exactly which claims are supported, unsupported, or contradicted.

**Functional Behavior:**

- The system parses the LLM response and extracts discrete factual claims (e.g., named entities, statistics, dates, causal statements).
- Each claim is passed to the Knowledge Retrieval Layer to find supporting evidence.
- A verification step compares each claim against retrieved evidence and returns: Supported, Unsupported, or Contradicted.
- Each claim receives an individual confidence classification.
- The set of claims, their evidence, and their verification results are displayed in the Guardrail Analysis Panel.
- Claims labeled Contradicted or Unsupported contribute negatively to the overall confidence score.

**Feature Rules and Constraints:**

- Claim extraction runs only after a response has been generated.
- If no factual claims are detected (e.g., the response is purely conversational), the system notes this and skips verification.
- Evidence citations must link to source documents in the knowledge base by title or chunk reference.
- The user must be able to see which claim maps to which evidence.

**Edge Cases:**

- Response contains no verifiable factual claims: verification is skipped; confidence score is computed from available signals only; UI shows "No factual claims detected."
- Knowledge base is empty or not selected: evidence retrieval returns zero results; all claims are classified as Unsupported; user is notified that no knowledge base is active.
- Response is very long with a high claim density: all claims are still processed; high claim density is flagged as a risk signal in the confidence engine.

---

### Feature 4 — Knowledge Retrieval Layer

**Description:** A vector search system that retrieves relevant evidence from an indexed knowledge base in response to claim queries.

**User Value:** Provides grounding for claim verification. Without retrieval, hallucination detection would rely solely on the LLM's self-assessment.

**Functional Behavior:**

- Users can upload documents or select a pre-loaded knowledge base in the playground.
- Uploaded documents are chunked and indexed into the vector store.
- During hallucination detection, each claim is converted to an embedding and the top-k most relevant chunks are retrieved.
- Retrieved chunks are ranked by relevance and passed to the verification step.
- The Knowledge Base Management screen shows indexing status and allows users to preview how documents were chunked.

**Feature Rules and Constraints:**

- Document upload is supported in the playground UI; accepted file types must be defined (see Open Questions).
- Chunking preview must show the user how their document was split before indexing begins.
- Users must be able to remove or replace uploaded documents.
- If no knowledge base is selected, retrieval is skipped; the UI indicates that no grounding source is active.

**Edge Cases:**

- Document upload fails (unsupported format or size limit exceeded): user receives an upload error with guidance.
- Indexed knowledge base has no relevant content for the claim: retrieval returns zero results; claim is marked Unsupported.
- User uploads a very large document: indexing may take longer than expected; progress indicator is shown; user is notified when indexing is complete.

---

### Feature 5 — Output Safety Filters

**Description:** Post-generation content filters that detect toxicity, hate speech, harmful instructions, and malware/exploit content in the LLM response.

**User Value:** Prevents unsafe content from reaching the user or downstream applications. Provides a clear record of what was filtered and why.

**Functional Behavior:**

- After LLM generation (and concurrently with or after hallucination detection), the response is passed through each safety filter in sequence.
- Each filter returns: Clean or Flagged.
- If any filter flags the response, the guardrail decision engine receives the flag and may issue a warning or block the response depending on the severity and configured policy.
- The specific filter(s) that triggered are recorded in the audit trail and shown in the Guardrail Analysis Panel.

**Feature Rules and Constraints:**

- Safety filters run on every response, regardless of prompt risk score.
- Filter results are always logged even when the response is ultimately accepted.
- The user cannot disable individual safety filters in the public playground (they may be toggleable via API policy configuration for developer use).

**Edge Cases:**

- Response triggers multiple filters simultaneously: all triggered filters are recorded; the most severe filter result drives the guardrail decision.
- Response is blocked by safety filter but prompt was validated successfully: both events are recorded; user sees block with safety filter reason.

---

### Feature 6 — Confidence Scoring Engine

**Description:** Aggregates signals from the hallucination detection, evidence retrieval, safety filters, and model uncertainty into a single reliability score for the response.

**User Value:** Gives developers and users a single, actionable signal indicating how much to trust the current response.

**Functional Behavior:**

- The engine receives inputs from: evidence similarity scores, claim verification results, claim density, safety filter outcomes, and model uncertainty estimation.
- A weighted aggregation produces a final reliability score on a 0–100 scale.
- The score is displayed as a badge in the playground UI with a clear label (e.g., High / Medium / Low confidence).
- A breakdown of the individual signal contributions is shown in the Guardrail Analysis Panel.
- The score is recorded in the audit trail for every request.

**Feature Rules and Constraints:**

- Score must always be present in the response output, even if some signals are unavailable (missing signals use a neutral default value).
- The confidence label thresholds (High / Medium / Low) are configurable in the Policy Configuration panel.
- Score breakdown must be human-readable, not just numeric.

**Edge Cases:**

- All claims are unsupported and a safety filter is triggered: score should be very low (near 0); guardrail decision is likely Block.
- Response has no factual claims and passes all safety filters: score reflects available signals only; UI explains reduced signal availability.

---

### Feature 7 — Guardrail Decision Engine

**Description:** Evaluates all pipeline signals and issues a final decision for how to handle the response.

**User Value:** Automates the reliability enforcement decision. Developers do not need to write their own logic for handling unsafe or unreliable responses.

**Functional Behavior:**

- After all pipeline stages complete, the engine evaluates: prompt risk score, safety filter results, confidence score, and configured policy thresholds.
- Possible decisions:
  - **Accept** — Response is returned as-is.
  - **Accept with Warning** — Response is returned with a visible warning attached.
  - **Retry with Safer Prompt** — Pipeline re-runs with a modified prompt template.
  - **Retry with Alternate Model** — Pipeline re-runs using a different model.
  - **Trigger RAG Augmentation** — Response is regenerated with retrieved context injected.
  - **Block** — Response is suppressed; user receives a block notification with reason.
- The decision, its reason, and the signals that drove it are displayed in the UI and recorded in the audit trail.

**Feature Rules and Constraints:**

- Decision logic must be deterministic given the same inputs and policy configuration.
- Only one decision is issued per request cycle; if a retry occurs, the retry is treated as a new pipeline cycle.
- Maximum retry attempts per request must be configurable and bounded to prevent infinite loops (default: 2 retries).
- The user must always see the final decision outcome in the playground UI, including which rule or threshold triggered it.

**Edge Cases:**

- Retry limit reached without an acceptable response: system issues a Block with reason "Maximum retries exceeded."
- Conflicting signals (e.g., high confidence score but safety filter triggered): safety filter always takes priority over confidence score for block decisions.

---

### Feature 8 — Fallback Strategy Engine

**Description:** Executes a specific remediation strategy when the guardrail decision calls for retry or augmentation.

**User Value:** Automates recovery from unreliable responses rather than returning a raw failure.

**Functional Behavior:**

- Available fallback strategies:
  - Retry with a stricter prompt template (injects additional instructions for accuracy or safety).
  - Retry with a lower temperature setting.
  - Switch to an alternate model provider.
  - Inject retrieved context (RAG augmentation) into the prompt before retrying.
  - Escalate to human review (in this release, represented as a flag in the audit trail with a notification state in the UI).
- The strategy applied is recorded in the execution trace and audit trail.
- The user sees the fallback strategy that was used in the execution trace viewer.

**Feature Rules and Constraints:**

- Fallback strategies are applied in a configured priority order.
- RAG augmentation requires an active knowledge base; if none is selected, this strategy is skipped.
- Human review escalation does not send notifications to any external system in the MVP; it sets a flag in the audit record.

**Edge Cases:**

- No fallback strategy succeeds within the retry limit: Block decision is issued.
- RAG augmentation is selected as a strategy but no knowledge base is indexed: strategy is skipped; next strategy in the priority order is attempted.

---

### Feature 9 — Policy Configuration System

**Description:** Allows developers (via UI or API) to configure guardrail rules, confidence thresholds, allowed/restricted content categories, and fallback strategy priority.

**User Value:** Makes the guardrail system configurable for different use cases without requiring code changes.

**Functional Behavior:**

- In the playground, a Policy Configuration panel exposes configurable settings:
  - Confidence threshold levels for Accept / Warn / Block decisions.
  - Allowed topic lists (comma-separated or tag-based).
  - Restricted content categories (selectable from a defined list).
  - Enable/disable specific guardrail modules (for developer exploration only; safety filters are always on).
  - Fallback strategy priority ordering.
- Configuration changes take effect on the next submitted request.
- Via the API, all policy parameters are settable per request or as a persistent configuration for developer integrations.

**Feature Rules and Constraints:**

- Output safety filters cannot be disabled from the public playground UI.
- Confidence threshold defaults must be set to reasonable values out of the box (configurable values defined in Open Questions).
- Policy configuration is not persisted between playground sessions unless the user is authenticated (authentication is out of scope for MVP; see Open Questions).

**Edge Cases:**

- User sets confidence threshold to 0 (Accept everything): system accepts all responses but still logs all pipeline results.
- User sets confidence threshold to 100 (Block everything): system blocks all responses; user is notified that the threshold is set to maximum restrictiveness.

---

### Feature 10 — Execution Trace Viewer

**Description:** A step-by-step visual breakdown of the entire guardrail pipeline for a given request, surfaced in the playground UI.

**User Value:** Makes the pipeline transparent and educational. Users can see exactly what happened at each stage and why.

**Functional Behavior:**

- After a request completes, the Execution Trace Viewer displays stages in sequential order:
  1. Prompt Received
  2. Prompt Validation (with sub-results per check)
  3. LLM Generation (model used, token count, latency)
  4. Claim Extraction (number of claims found)
  5. Evidence Retrieval (number of evidence chunks retrieved)
  6. Claim Verification (per-claim results)
  7. Safety Filter Checks (per-filter results)
  8. Confidence Score Calculation (signal breakdown)
  9. Guardrail Decision (decision + reason)
  10. Fallback Executed (if applicable, strategy used)
  11. Final Response Returned
- Each stage shows status (Passed / Flagged / Failed / Skipped) and relevant metadata.
- Stages that were skipped (e.g., evidence retrieval with no knowledge base) are shown as Skipped with a reason.

**Feature Rules and Constraints:**

- The trace is always generated for every request.
- The trace must be expandable/collapsible per stage for readability.
- The trace must be available in the Request Explorer for historical requests by request ID.

**Edge Cases:**

- Pipeline halts at prompt validation (Block): trace shows all subsequent stages as Not Reached.
- Retry occurred: trace shows the original cycle and the retry cycle separately, labeled accordingly.

---

### Feature 11 — Analytics Dashboard

**Description:** Aggregate metrics across all processed requests, displayed in a dedicated dashboard screen.

**User Value:** Gives developers and evaluators a high-level view of system behavior, model performance, and reliability patterns over time.

**Functional Behavior:**

- Metrics displayed:
  - Hallucination detection rate (per model)
  - Guardrail trigger frequency (by decision type)
  - Response confidence score distribution (histogram)
  - Mean pipeline latency
  - Token usage and estimated cost per request
  - Model reliability comparison (when multiple models have been used)
- Charts update based on available request history.
- Time range filter allows narrowing metrics to a recent window (e.g., last 100 requests, last 24 hours).

**Feature Rules and Constraints:**

- Dashboard reflects only requests processed in the current deployment session (no cross-session persistence in MVP unless a database is configured).
- No personally identifiable information is shown in aggregate metrics.
- Empty state is shown with placeholder charts and a prompt to submit requests when no data exists.

**Edge Cases:**

- No requests have been processed: all charts show empty state with instructional copy.
- Only one model has been used: model comparison chart shows single-model data without comparison columns.

---

### Feature 12 — Request Explorer & Audit Trail

**Description:** A searchable log of all processed requests, each with a full audit record including prompt, response, evidence, guardrail decisions, and confidence score.

**User Value:** Enables post-hoc investigation of specific requests, debugging of guardrail behavior, and compliance review.

**Functional Behavior:**

- Requests are listed in reverse chronological order with: request ID, timestamp, model used, confidence score, and final guardrail decision.
- User can search by request ID or filter by decision type, model, or confidence range.
- Selecting a request opens the full audit record:
  - Original prompt
  - Final response (or block reason)
  - Claim verification results with evidence citations
  - Confidence score breakdown
  - Execution trace (same view as in the playground)
  - Guardrail decision and reason
- A "Replay Request" action re-submits the original prompt through the current pipeline configuration.

**Feature Rules and Constraints:**

- Prompts containing detected PII are masked in the audit record display (original is not stored).
- Audit records are retained for the duration of the current session in MVP. Persistence across sessions depends on storage configuration.
- Replay uses the stored prompt but applies current policy configuration, not the original configuration at time of request.

**Edge Cases:**

- Request ID not found: user sees a "Request not found" empty state.
- Prompt was PII-masked: replay is not available for masked records (action is disabled with explanation).

---

### Feature 13 — Knowledge Base Management

**Description:** A UI screen for uploading, managing, and previewing the documents used as the grounding knowledge base for evidence retrieval.

**User Value:** Allows users to control what the system knows and to understand how their documents are processed.

**Functional Behavior:**

- Users can upload documents to be indexed.
- After upload, the system shows a chunking preview: how the document was split into segments.
- Indexing status is shown per document (Pending / Indexing / Ready / Failed).
- Users can delete documents from the knowledge base.
- A vector search preview allows users to enter a test query and see which chunks would be retrieved.
- Pre-loaded knowledge base options are available for selection without uploading.

**Feature Rules and Constraints:**

- Accepted file types and maximum file size must be defined (see Open Questions).
- Chunking parameters (chunk size, overlap) are shown to the user but are not configurable in the playground UI in MVP.
- Indexing must complete before the knowledge base is available for retrieval.
- The user must see a clear Ready status before relying on the knowledge base for requests.

**Edge Cases:**

- Upload fails (unsupported type, size exceeded): user receives a specific error message.
- Indexing fails for a document: document is marked Failed; user can retry or remove it.
- User submits a request while a document is still indexing: retrieval proceeds with only the already-indexed documents; UI notes that indexing is in progress.

---

### Feature 14 — Developer SDK & API

**Description:** A programmatic interface that allows developers to integrate SentinelAI Guardrail middleware into their own applications.

**User Value:** Enables production integration beyond the playground, making the guardrail system a usable infrastructure component.

**Functional Behavior:**

- The REST API accepts requests containing: prompt, model selection, knowledge base reference (optional), and policy overrides (optional).
- The API returns: final response, confidence score, guardrail decision, claim verification results, execution trace, and token usage.
- The SDK wraps the REST API with convenience methods, async support, and structured error handling.
- API documentation is accessible from the playground UI.

**Feature Rules and Constraints:**

- API must return structured, consistent JSON responses for all outcomes including errors.
- All guardrail pipeline outputs (score, decision, trace) are always included in the API response, not just the final text.
- Error responses must include a machine-readable error code and a human-readable message.

**Edge Cases:**

- API caller omits a required field: API returns a 400-level error with the missing field identified.
- API caller provides an invalid policy configuration: API returns a validation error before processing begins.
- Request times out server-side: API returns a timeout error with a request ID for audit lookup.

---

## 7. UX Architecture

### Screen Inventory

| Screen | Description |
|---|---|
| **Playground** | Primary interactive interface for submitting prompts and viewing guardrail results |
| **Guardrail Analysis Panel** | Sub-panel within Playground showing claim extraction, evidence, and verification results |
| **Execution Trace Viewer** | Step-by-step pipeline visualization, accessible from Playground and Request Explorer |
| **Analytics Dashboard** | Aggregate metrics across all processed requests |
| **Request Explorer** | Searchable log of historical requests with full audit detail |
| **Knowledge Base Management** | Document upload, indexing status, chunking preview, and search preview |
| **Policy Configuration** | Guardrail rule settings, thresholds, and module toggles |
| **API Documentation** | Developer-facing API reference, accessible from the Playground |

### Navigation Structure

```
[ Playground ]
    ├── Guardrail Analysis Panel (inline sub-panel)
    ├── Execution Trace Viewer (expandable inline or modal)
    └── [ Model & Knowledge Base Selector ] (inline controls)

[ Analytics Dashboard ]

[ Request Explorer ]
    └── Request Detail View
            └── Execution Trace Viewer (read-only)

[ Knowledge Base Management ]

[ Policy Configuration ]

[ API Documentation ]
```

### Navigation Behavior

- Primary navigation is a persistent top-level navigation bar (or sidebar) accessible from all screens.
- The Guardrail Analysis Panel and Execution Trace Viewer are embedded within the Playground screen and do not navigate away.
- Request Detail View opens inline or in a full-page view from the Request Explorer list.
- API Documentation opens in a new tab or dedicated full-page view.
- No login or authentication gate in MVP; all screens are accessible without an account.

---

## 8. Detailed User Flows

### Flow 1 — Demo User: First Playground Request

1. User navigates to the public SentinelAI Guardrail URL.
2. Landing screen is the Playground with no prior results shown.
3. User reads a short description of the system (inline copy, not a modal).
4. User types a prompt in the prompt input area.
5. User selects a model from the dropdown (defaults to Local Model).
6. User optionally selects a knowledge base or skips (defaults to no knowledge base).
7. User optionally adjusts guardrail toggles (all enabled by default).
8. User clicks Submit.
9. A loading state is shown with a progress indicator cycling through pipeline stage names.
10. Results appear:
    - Response text is displayed in the output panel.
    - Confidence score badge appears above the response.
    - Guardrail decision label is shown (e.g., "Accepted" or "Accepted with Warning").
    - Guardrail Analysis Panel populates with claims, evidence, and verification results.
    - Execution Trace Viewer is available (collapsed by default, expandable).
11. User expands the Execution Trace Viewer and inspects each pipeline stage.
12. User submits another prompt or navigates to the Analytics Dashboard.

---

### Flow 2 — OpenAI API Key Usage

1. User selects "OpenAI" from the model dropdown in the Playground.
2. An API key input field appears inline below the model selector.
3. User enters their OpenAI API key.
4. User submits the request.
5. System uses the key for this request only.
6. If the key is invalid, an error message appears below the input field: "Invalid API key. Please check your OpenAI credentials."
7. Key field is cleared after the request completes (not retained in UI or storage).

---

### Flow 3 — Developer Exploration (Comparing Models)

1. Developer opens the Playground.
2. Submits a factually complex prompt with Local Model selected.
3. Reviews the hallucination detection results and confidence score.
4. Switches model to OpenAI, re-enters API key, resubmits same prompt.
5. Compares confidence scores and claim verification results between the two runs.
6. Navigates to Analytics Dashboard to view model reliability comparison across all submitted requests.

---

### Flow 4 — Audit Investigation

1. User navigates to the Request Explorer.
2. Searches for a specific request by ID (copied from a prior playground session or API response).
3. Selects the request from the results list.
4. Reviews the full audit record: prompt, response, claim verification, confidence breakdown, and guardrail decision.
5. Expands the Execution Trace to identify at which stage a flag was triggered.
6. Clicks "Replay Request" to re-run the prompt through the current pipeline configuration.

---

### Flow 5 — Knowledge Base Upload

1. User navigates to Knowledge Base Management.
2. Clicks "Upload Document."
3. Selects a file from their device.
4. System shows a loading state while processing.
5. Chunking preview is displayed: document segments listed in order.
6. Indexing status shows "Indexing…" then transitions to "Ready."
7. User enters a test query in the vector search preview field.
8. Top-k retrieved chunks are shown with relevance indicators.
9. User returns to the Playground and selects the new knowledge base.

---

### Flow 6 — Policy Configuration

1. User navigates to Policy Configuration.
2. Adjusts confidence threshold sliders for Accept / Warn / Block.
3. Adds restricted content categories from a predefined list.
4. Reorders fallback strategy priority using drag-and-drop controls.
5. Saves configuration.
6. Returns to Playground; next request uses updated policy.

---

### Empty States

| Screen | Empty State |
|---|---|
| Playground (no submission yet) | Prompt input visible with placeholder text; output area shows instructional copy: "Submit a prompt to see the guardrail pipeline in action." |
| Analytics Dashboard (no requests) | Charts shown with empty/placeholder visuals; copy reads: "No requests processed yet. Submit a prompt in the Playground to generate analytics." |
| Request Explorer (no requests) | List shows: "No requests have been recorded yet." |
| Knowledge Base Management (no documents) | Shows: "No documents indexed. Upload a document to enable knowledge-grounded verification." |

---

### Error States

| Scenario | User-Facing Behavior |
|---|---|
| Local model unavailable | Inline error in Playground: "Local model is not available. Please check the service or switch to OpenAI." |
| OpenAI key invalid | Inline field error: "Invalid API key. Please verify your OpenAI credentials." |
| Request timeout | Output area shows: "Request timed out. The pipeline did not complete within the allowed time." with request ID. |
| Upload fails | Inline error in Knowledge Base Management with reason (unsupported type / size exceeded). |
| No evidence retrieved | Claim marked "Unsupported" in panel; note: "No grounding evidence found for this claim." |
| Pipeline blocked | Output area shows block reason and which rule/filter triggered it; no response text shown. |

---

## 9. UI / UX Specifications

---

### Screen: Playground

**Layout Structure:**

- Two-column layout on desktop:
  - Left column (60%): Prompt input, model selector, knowledge base selector, guardrail toggles, submit button, response output panel, confidence badge, guardrail decision label.
  - Right column (40%): Guardrail Analysis Panel (claims, evidence, verification).
- Below both columns: Execution Trace Viewer (full-width, collapsible).
- Single-column stacked layout on mobile/narrow viewports.

**Key UI Components:**

- Prompt input: Multi-line text area with character count indicator.
- Model selector: Dropdown with options [Local Model, OpenAI]. OpenAI selection reveals API key field.
- API key field: Password-type input with "Use this request only" label.
- Knowledge base selector: Dropdown listing indexed knowledge bases plus "None" option.
- Guardrail toggle controls: Toggle switches per module (Prompt Validation, Hallucination Detection, Safety Filters). Safety filters toggle disabled in public playground.
- Submit button: Primary action button, disabled while a request is in progress.
- Response output panel: Scrollable text area displaying the final response or block reason.
- Confidence score badge: Numeric score (0–100) with color coding (green ≥ 70, yellow 40–69, red < 40) and text label (High / Medium / Low).
- Guardrail decision label: Pill or badge showing decision type (Accepted / Warning / Blocked / Retried).
- Guardrail warnings indicator: Icon + count of flags raised during pipeline.

**Interaction Patterns:**

- Submitting a prompt disables the input and submit button, shows a pipeline progress indicator.
- Results animate in progressively as pipeline stages complete (or appear all at once if streaming is not implemented).
- Execution Trace Viewer expands/collapses per stage with a chevron toggle.
- Clicking a claim in the Guardrail Analysis Panel highlights its evidence entry.

**States:**

- **Loading:** Submit button replaced by a spinner; pipeline stage label cycles (e.g., "Validating prompt… Generating response… Verifying claims…").
- **Success (Accepted):** Response text populates; green confidence badge; "Accepted" decision label.
- **Success (Warning):** Response text populates with a yellow warning banner; warning decision label.
- **Blocked:** Response area shows block reason in a red alert box; no response text.
- **Error:** Inline error message below submit button; input re-enabled.
- **Empty:** Instructional placeholder copy in output area.

---

### Screen: Guardrail Analysis Panel

**Layout Structure:**

- Three vertical sections: Extracted Claims → Evidence Retrieved → Verification Results.
- Each section is independently scrollable if content overflows.

**Key UI Components:**

- Claims list: Numbered list of extracted factual claims from the response.
- Evidence list: Per-claim evidence chunks with source document reference and relevance indicator.
- Verification results: Per-claim status badge (Supported / Unsupported / Contradicted) with brief justification.
- Confidence signal breakdown: Small bar chart or labeled list showing individual signal contributions to the total score.

**Interaction Patterns:**

- Clicking a claim filters the evidence panel to show only that claim's evidence.
- Evidence chunks are expandable to show full text.

---

### Screen: Execution Trace Viewer

**Layout Structure:**

- Vertical timeline of pipeline stages.
- Each stage row: Stage name | Status badge | Key metadata | Expand toggle.

**Key UI Components:**

- Stage status badges: Passed (green), Flagged (yellow), Failed (red), Skipped (grey), Not Reached (grey, dashed).
- Expandable detail per stage: Shows specific sub-results (e.g., which PII type was detected, which safety filter triggered, token count, latency per stage).
- Retry indicator: If a retry occurred, a second trace block appears below the first, clearly labeled "Retry Attempt 1."

**States:**

- Collapsed (default): Only stage names and status badges visible.
- Expanded: Full detail per stage.

---

### Screen: Analytics Dashboard

**Layout Structure:**

- Summary metrics row at top (total requests, avg confidence score, hallucination rate, avg latency).
- Chart grid below:
  - Hallucination rate per model (bar chart)
  - Guardrail decision distribution (pie or donut chart)
  - Confidence score distribution (histogram)
  - Latency over time (line chart)
  - Token usage / cost per request (bar chart)

**Key UI Components:**

- Time range selector (dropdown or tab: All Time / Last 100 Requests / Last 24 Hours).
- Chart tooltips on hover showing exact values.
- Model comparison toggle (shows/hides per-model breakdown).

**States:**

- **Empty:** Placeholder charts with instructional copy.
- **Single model:** Model comparison chart shows single dataset without comparison.
- **Loaded:** All charts populated.

---

### Screen: Request Explorer

**Layout Structure:**

- Left panel: Searchable, filterable list of requests.
- Right panel: Selected request detail (or empty state if none selected).

**Key UI Components:**

- Search input: Searches by request ID.
- Filter controls: Decision type, model, confidence range.
- Request list item: Request ID (truncated), timestamp, model, confidence badge, decision label.
- Detail panel: Full audit record view — prompt, response, claims, evidence, score breakdown, execution trace, replay button.

**States:**

- **No selection:** Right panel shows: "Select a request to view its audit record."
- **No results:** List shows empty state copy.
- **PII-masked record:** Prompt field shows masked indicator; Replay button is disabled with tooltip explaining why.

---

### Screen: Knowledge Base Management

**Layout Structure:**

- Top action bar: Upload button.
- Document list: Each document shows name, status badge, chunk count, actions (Delete).
- Document detail side panel (or modal): Chunking preview, vector search preview.

**States:**

- **No documents:** Empty state with upload prompt.
- **Indexing in progress:** Status badge shows "Indexing…" with a spinner.
- **Ready:** Status badge shows "Ready" in green.
- **Failed:** Status badge shows "Failed" in red with retry option.

---

### Screen: Policy Configuration

**Layout Structure:**

- Sections:
  - Confidence Thresholds (sliders for Accept / Warn / Block boundaries)
  - Content Categories (toggle list for restricted categories)
  - Allowed Topics (text input for comma-separated topics)
  - Fallback Strategy Priority (ordered drag-and-drop list)
  - Guardrail Module Toggles (enabled/disabled per module)
- Save button at bottom; changes are not auto-saved.

**States:**

- **Unsaved changes:** Save button is active; a "Unsaved changes" indicator is shown.
- **Saved:** Brief success confirmation inline.

---

## 10. Functional Requirements

### Input Handling

- The prompt input field accepts plain text only; no file attachment from the prompt field.
- Maximum prompt length must be enforced; exceeding the limit displays an inline character count warning and disables submission.
- Empty prompt submission is blocked; the submit button remains disabled until at least one non-whitespace character is entered.

### Validation Rules

- OpenAI API key format validation occurs client-side before the request is sent (basic format check, not an authenticated test call).
- Confidence threshold values in Policy Configuration must be set such that: Block threshold < Warn threshold < Accept threshold; violations are caught on save with an inline validation error.
- Restricted content category selections must persist for the session duration.

### System Responses

- Every submitted request must return a response (text, block reason, or error) within a defined maximum wait time; if the pipeline exceeds this time, the system returns a timeout response with a request ID.
- The request ID is always displayed in the playground output area after a completed request for reference.
- All guardrail decisions are surfaced in the UI; no decision is silently dropped.

### Guardrail Logic

- If prompt is Blocked at validation: no LLM call occurs; no hallucination detection runs; decision is Block; cost is zero.
- If LLM generation fails: fallback strategy is invoked; if all fallbacks fail, decision is Block.
- If hallucination detection is toggled off by the user: claim extraction and verification are skipped; confidence score is computed from available signals (safety filters, model uncertainty); UI notes that hallucination detection is inactive.
- Guardrail decisions are deterministic for the same input and policy configuration; the same prompt with the same settings must produce the same decision.

### Session Behavior

- No user authentication is required in the MVP.
- Session state (policy configuration, knowledge base selection, model selection) is maintained within the browser session.
- Refreshing the page resets the playground to default state.
- Request history is maintained for the session in the Request Explorer.

---

## 11. Non-Functional Product Requirements

### Performance Expectations

- The guardrail pipeline for a typical request (local model, no knowledge base) should complete within a target of under 30 seconds, including all validation, generation, detection, and scoring stages.
- The UI must show meaningful progress feedback during pipeline execution; users must not see a blank screen for more than 2 seconds after submission.
- The Analytics Dashboard must load and render with existing session data within 3 seconds.

### Accessibility Expectations

- All interactive elements must be keyboard-navigable.
- Color-coded confidence badges and status indicators must have text labels in addition to color (for color-blind users).
- Error messages must be descriptive and not rely solely on color.
- Chart tooltips must be accessible via keyboard focus.
- Text contrast ratios must meet WCAG 2.1 AA minimum standards.

### Privacy Expectations

- Prompts containing detected PII are masked before storage in the audit record.
- OpenAI API keys are used for the current request only and are not logged, stored, or transmitted beyond the LLM provider call.
- No user tracking, cookies, or analytics beyond aggregate pipeline metrics in the MVP.
- Prompt content is not used for training or shared with third parties.

### Reliability Expectations

- The system must handle concurrent requests without one user's session affecting another's results.
- Pipeline failures (LLM timeout, retrieval failure) must not crash the UI; error states must be gracefully surfaced.
- The system must function in a free hosting environment with cold start behavior; users in a cold start state see a loading/warming-up indicator.

### Usability Expectations

- A first-time user with no prior knowledge of the system must be able to submit a prompt and understand the results within 5 minutes.
- All technical terms in the UI (e.g., "confidence score," "claim verification," "RAG augmentation") must have inline tooltips explaining them in plain language.
- The Execution Trace Viewer must be comprehensible to a developer who did not build the system.

### Browser Compatibility

- The playground UI must function correctly in the current stable versions of Chrome, Firefox, Safari, and Edge.
- The UI must be responsive and usable on tablet-width viewports (≥ 768px).
- Mobile (< 768px) is a secondary target: core Playground functionality must work; Analytics Dashboard may have reduced chart fidelity on small screens.

---

## 12. External Integrations (Product Perspective)

### LLM Providers

| Integration | Purpose | User Interaction | Expected Behavior |
|---|---|---|---|
| Local Model (via Ollama) | Default free LLM execution | User selects "Local Model" from dropdown | Request is processed using the local model; no API key required; response returned through the full pipeline |
| OpenAI API | Optional hosted LLM for comparison | User selects "OpenAI" and enters their API key in the playground | Key is used for this request only; response processed through the full pipeline; key is discarded after the request |

### Embedding Models

| Integration | Purpose | User Interaction | Expected Behavior |
|---|---|---|---|
| Local embedding model (SentenceTransformers / BGE / Nomic) | Convert claims and document chunks to embeddings for similarity search | Transparent to user; runs during knowledge base indexing and claim verification | Embeddings are generated automatically; user sees indexing status and retrieval results |

### Vector Database

| Integration | Purpose | User Interaction | Expected Behavior |
|---|---|---|---|
| Local vector store (FAISS / Chroma) | Store and retrieve document embeddings for evidence retrieval | Transparent to user; underpins Knowledge Base Management and retrieval | User uploads documents and sees indexing status; retrieval results appear in the Guardrail Analysis Panel |

---

## 13. Edge Cases & Error Scenarios

| Scenario | Expected Product Behavior |
|---|---|
| Empty prompt submitted | Submit button is disabled; no request is sent. |
| Prompt exceeds maximum length | Character counter turns red; submit button disabled; inline message shown. |
| Prompt blocked at validation | No LLM call made; output panel shows block reason and which validation check triggered it; execution trace shows subsequent stages as Not Reached. |
| Local model service is unavailable | Inline error in Playground; user offered option to switch to OpenAI. |
| OpenAI API key invalid or expired | Inline field error; request is not sent; user prompted to re-enter key. |
| LLM returns empty response | Pipeline treats this as a generation failure; fallback strategy is invoked; if all fallbacks fail, Block is issued. |
| All claims unsupported | Confidence score is very low; guardrail decision likely Block or Accept with Warning depending on threshold; all claims marked Unsupported in panel. |
| Safety filter triggered on otherwise high-confidence response | Safety filter result overrides confidence score for block decisions; user sees safety filter flag as the block reason. |
| Knowledge base indexing in progress when request is submitted | Retrieval runs on already-indexed documents only; UI shows note that indexing is still in progress for the pending document. |
| Document upload exceeds size limit | Upload rejected immediately; inline error with size limit stated. |
| Retry limit reached | Block issued with reason: "Maximum retries exceeded after [n] attempts." |
| Request ID not found in Explorer | Empty state shown: "Request not found. Please check the ID and try again." |
| Cold start delay on free hosting | UI shows a "Warming up…" indicator; request proceeds when service is ready. |
| Concurrent requests from multiple users | Each request is isolated; one user's pipeline failure does not affect another's results. |
| Confidence threshold misconfiguration (Block < Warn) | Validation error on save in Policy Configuration; save is blocked until resolved. |
| Very long response with many claims | All claims are processed; high claim density is flagged as a risk signal; performance may degrade on very high claim counts (out of scope for MVP optimization). |

---

## 14. Privacy & User Data Considerations

### Data Collected

| Data | Why Collected | Retention |
|---|---|---|
| Prompt text | Required to run the guardrail pipeline and generate a response | Session only; masked in audit record if PII is detected; not persisted beyond session in MVP |
| LLM response text | Required to display results and perform hallucination detection | Session only; stored in request audit record |
| Confidence score and guardrail decision | Required for audit trail and analytics | Session only; aggregate metrics retained for dashboard |
| Token usage | Required for cost tracking and analytics | Session only; stored in audit record |
| Execution trace | Required for observability and audit investigation | Session only; stored per request |
| OpenAI API key | Required to call OpenAI API on behalf of the user | Not stored; used for current request only; discarded immediately after |

### Data Not Collected

- No user account information (no registration in MVP).
- No browser fingerprinting or user tracking.
- No prompt content shared with third parties beyond the selected LLM provider for the purpose of generating a response.

### User Controls

- Users can choose not to submit prompts containing PII; the system flags PII but does not prevent submission.
- Users control whether to use OpenAI (and supply their key) or rely on the local model.
- Users can delete knowledge base documents they uploaded.
- No mechanism to request deletion of session audit records in MVP (records are session-scoped and discarded on session end).

### Consent and Permissions

- No explicit consent flow in MVP (no account, no persistent data storage).
- A brief privacy notice should be displayed in the Playground UI footer explaining that prompts are processed locally by default, that OpenAI API keys are not stored, and that no user data is retained after the session.

---

## 15. Development Phases (Product Roadmap)

### Phase 1 — MVP

**Goal:** Deliver a working public playground demonstrating the core guardrail pipeline end to end.

**Features Included:**

- Playground UI with prompt input, model selector (Local + OpenAI), and response output
- Prompt validation engine (injection detection, PII detection, policy filtering, risk scoring)
- LLM execution layer with local model support and optional OpenAI via user-supplied key
- Basic hallucination detection (claim extraction, evidence retrieval, LLM-based verification)
- Output safety filters (toxicity, hate speech, harmful instruction detection)
- Confidence scoring engine (multi-signal score, displayed as badge)
- Guardrail decision engine (Accept / Accept with Warning / Block)
- Execution Trace Viewer (step-by-step pipeline visualization)
- Basic audit trail (per-session request log)
- Knowledge Base Management (document upload, chunking preview, indexing status)
- Developer REST API (basic endpoint for external integration)
- Privacy notice in UI footer

---

### Phase 2 — Expansion

**Goal:** Add observability, deeper analysis tools, and developer integration surface.

**Features Added:**

- Analytics Dashboard (hallucination rate, guardrail trigger charts, confidence distribution, latency, cost)
- Request Explorer with search, filter, and full audit record view
- Replay Request capability in Request Explorer
- Fallback Strategy Engine (full retry / augmentation strategy execution)
- Policy Configuration panel (threshold sliders, category toggles, fallback priority)
- Developer SDK (client libraries, async support, error handling utilities)
- Claim-to-evidence linking in the Guardrail Analysis Panel
- Model comparison in the Analytics Dashboard
- Vector search preview in Knowledge Base Management

---

### Phase 3 — Advanced Capabilities

**Goal:** Add configurable policies, richer observability, and developer-facing tooling for production use cases.

**Features Added:**

- API-level policy configuration per request (full policy override via API)
- Human review escalation flag with dedicated review queue view in UI
- Request batching support in the API
- Multi-knowledge-base support (select and combine multiple indexed knowledge bases per request)
- Configurable chunking parameters in Knowledge Base Management
- Export audit records (CSV or JSON) from Request Explorer
- Prometheus metrics endpoint for external monitoring integration
- Pre-loaded demonstration knowledge bases covering common fact-checking domains

---

## 16. Future Enhancements

- **User accounts and persistent history** — Allow users to create accounts to persist request history, policy configurations, and knowledge bases across sessions.
- **Streaming response support** — Stream the LLM response to the UI as it generates rather than waiting for full completion, with guardrail results appended after generation.
- **Multi-model parallel execution** — Submit the same prompt to multiple models simultaneously and display side-by-side results for direct comparison.
- **Custom embedding model selection** — Allow users to choose their embedding model from a list within the playground.
- **Fine-grained policy templates** — Predefined policy configurations for common use cases (e.g., medical Q&A, legal document review, customer support) selectable in Policy Configuration.
- **Webhook support in API** — Push guardrail results and audit events to a user-configured webhook endpoint instead of requiring polling.
- **Human review workflow** — A proper review queue with assignment, resolution, and feedback loop for escalated requests.
- **Hallucination trend analysis** — Per-topic or per-prompt-category hallucination pattern detection over time.
- **SDK language expansion** — Extend SDK beyond the initial language to cover additional common backend languages.
- **Interactive knowledge base graph** — Visualize relationships between indexed document chunks and retrieved evidence.

---

## 17. Open Questions / Assumptions

### Assumptions Made

| # | Assumption |
|---|---|
| A1 | The public playground requires no user authentication in the MVP. |
| A2 | Session-scoped audit records (not cross-session persistent) are acceptable for the MVP. |
| A3 | The local model (Ollama) is assumed to be pre-configured and running as part of the deployment; the playground does not guide users through local model setup. |
| A4 | The playground is a single-tenant public demo, not a multi-tenant platform. Concurrent users are supported but there is no user isolation at the data layer beyond session scoping. |
| A5 | "Human review escalation" in the MVP means flagging in the audit trail only; no external notification or queue system is built. |
| A6 | Confidence threshold defaults: Accept ≥ 70, Warn 40–69, Block < 40 (subject to stakeholder review). |
| A7 | Prompt maximum length defaults to 4,000 characters (subject to model context window constraints). |
| A8 | The analytics dashboard reflects only the current session's requests in the MVP unless a persistent database is configured at deployment time. |

### Open Questions Requiring Stakeholder Clarification

| # | Question | Impact |
|---|---|---|
| Q1 | What file types and maximum file size are supported for knowledge base document uploads? | Affects Knowledge Base Management feature spec and error messages. |
| Q2 | Should policy configuration changes persist across sessions without authentication? If yes, how (browser local storage, server-side with a session token)? | Affects Policy Configuration behavior and session handling. |
| Q3 | Should the public playground have any rate limiting per IP or session to prevent abuse? If yes, what are the limits and what is the user-facing behavior when the limit is reached? | Affects Playground functional requirements and error states. |
| Q4 | What specific pre-loaded knowledge bases should ship with the demo? | Affects Phase 1 MVP scope for Knowledge Base Management. |
| Q5 | Is there a defined list of restricted content categories for the safety filter toggles in Policy Configuration, or is this free-form? | Affects Policy Configuration UI specification. |
| Q6 | Should the audit trail records be exportable in the MVP or only in Phase 3? | Affects Phase 1 vs Phase 3 scope boundary. |
| Q7 | What is the acceptable maximum latency for the full pipeline in production? The 30-second target in this document is an assumption; local models may exceed this for complex prompts. | Affects performance requirements and user expectation setting. |
| Q8 | Is streaming (progressive token delivery from the LLM) a requirement for the MVP playground, or is it a Phase 3 enhancement? | Affects MVP scope and UI loading state design. |
| Q9 | What is the intended hosting platform for the free deployment? (e.g., Hugging Face Spaces, Render, Railway, Fly.io) — this may affect cold start behavior and UI handling. | Affects reliability requirements and the cold start UX pattern. |
| Q10 | Should the developer SDK be released as a published package (e.g., PyPI) in the MVP, or is it only available as source code from the repository? | Affects Phase 1 vs Phase 2 scope boundary for the SDK feature. |

---

*Document prepared by: Product Specification Generator*  
*Based on inputs provided for: SentinelAI Guardrail*  
*Version: 1.0 — Ready for stakeholder review*
