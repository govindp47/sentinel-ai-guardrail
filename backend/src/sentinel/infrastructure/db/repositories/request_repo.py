from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
import uuid

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from sentinel.infrastructure.db.models import (
    PipelineTraceORM,
    RequestClaimORM,
    RequestORM,
    SafetyFilterResultORM,
)

# ── Lightweight read models returned by list / get_by_id ─────────────────────


@dataclass
class RequestSummary:
    id: str
    created_at: datetime
    model_provider: str
    model_name: str
    confidence_score: int | None
    confidence_label: str | None
    guardrail_decision: str | None
    status: str
    pii_detected: bool


@dataclass
class RequestDetail:
    """Full request record including all child records."""

    id: str
    session_id: str
    policy_snapshot_id: str
    prompt_hash: str
    prompt_masked_text: str
    model_provider: str
    model_name: str
    status: str
    retry_count: int
    total_latency_ms: int | None
    tokens_in: int | None
    tokens_out: int | None
    risk_score: int | None
    confidence_score: int | None
    confidence_label: str | None
    confidence_signal_breakdown: str | None
    guardrail_decision: str | None
    decision_reason: str | None
    decision_triggered_rule: str | None
    final_response_text: str | None
    block_reason: str | None
    fallback_strategy_used: str | None
    pii_detected: bool
    pii_types_detected: str
    created_at: datetime
    completed_at: datetime | None
    # Child records — populated via selectinload
    pipeline_traces: list[PipelineTraceORM]
    request_claims: list[RequestClaimORM]
    safety_filter_results: list[SafetyFilterResultORM]


# ── Repository ────────────────────────────────────────────────────────────────


class RequestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        session_id: str,
        policy_snapshot_id: str,
        prompt_hash: str,
        prompt_masked_text: str,
        model_provider: str,
        model_name: str,
        kb_document_set_id: str | None = None,
    ) -> str:
        """Insert a new request with status='pending'. Returns the new UUID."""
        request_id = str(uuid.uuid4())
        row = RequestORM(
            id=request_id,
            session_id=session_id,
            policy_snapshot_id=policy_snapshot_id,
            prompt_hash=prompt_hash,
            prompt_masked_text=prompt_masked_text,
            model_provider=model_provider,
            model_name=model_name,
            kb_document_set_id=kb_document_set_id,
            status="pending",
            retry_count=0,
            pii_detected=0,
            pii_types_detected="[]",
            created_at=datetime.now(UTC),
        )
        self._session.add(row)
        await self._session.commit()
        return request_id

    async def update_status(self, request_id: str, status: str) -> None:
        """Single-statement status update."""
        stmt = update(RequestORM).where(RequestORM.id == request_id).values(status=status)
        await self._session.execute(stmt)
        await self._session.commit()

    async def update_completed(self, request_id: str, result_dict: dict[str, Any]) -> None:
        """
        Atomically update all result fields when the pipeline completes.
        `result_dict` keys must match RequestORM column names exactly.
        Always sets completed_at to now.
        """
        safe_fields = {
            "status",
            "retry_count",
            "total_latency_ms",
            "tokens_in",
            "tokens_out",
            "risk_score",
            "confidence_score",
            "confidence_label",
            "confidence_signal_breakdown",
            "guardrail_decision",
            "decision_reason",
            "decision_triggered_rule",
            "final_response_text",
            "block_reason",
            "fallback_strategy_used",
            "pii_detected",
            "pii_types_detected",
        }
        values = {k: v for k, v in result_dict.items() if k in safe_fields}
        values["completed_at"] = datetime.now(UTC)

        stmt = update(RequestORM).where(RequestORM.id == request_id).values(**values)
        await self._session.execute(stmt)
        await self._session.commit()

    async def list_by_session(
        self,
        session_id: str,
        filters: dict[str, Any] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[RequestSummary]:
        """
        Paginated list for the Request Explorer.
        Supported filter keys:
          filter_by_decision: str  — exact match on guardrail_decision
          filter_by_status: str    — exact match on status
          search_by_id: str        — prefix/contains match on request id
        """
        filters = filters or {}
        stmt = (
            select(
                RequestORM.id,
                RequestORM.created_at,
                RequestORM.model_provider,
                RequestORM.model_name,
                RequestORM.confidence_score,
                RequestORM.confidence_label,
                RequestORM.guardrail_decision,
                RequestORM.status,
                RequestORM.pii_detected,
            )
            .where(RequestORM.session_id == session_id)
            .order_by(RequestORM.created_at.desc())
            .limit(limit)
            .offset(offset)
        )

        if "filter_by_decision" in filters and filters["filter_by_decision"] is not None:
            stmt = stmt.where(RequestORM.guardrail_decision == filters["filter_by_decision"])

        if "filter_by_status" in filters and filters["filter_by_status"] is not None:
            stmt = stmt.where(RequestORM.status == filters["filter_by_status"])

        if "search_by_id" in filters and filters["search_by_id"] is not None:
            stmt = stmt.where(RequestORM.id.contains(filters["search_by_id"]))

        result = await self._session.execute(stmt)
        rows = result.all()

        return [
            RequestSummary(
                id=row.id,
                created_at=row.created_at,
                model_provider=row.model_provider,
                model_name=row.model_name,
                confidence_score=row.confidence_score,
                confidence_label=row.confidence_label,
                guardrail_decision=row.guardrail_decision,
                status=row.status,
                pii_detected=bool(row.pii_detected),
            )
            for row in rows
        ]

    async def get_by_id(self, request_id: str, session_id: str) -> RequestDetail | None:
        """
        Full row fetch with eager loading of all child records.
        Single query — no N+1.
        Enforces session ownership: returns None if session_id doesn't match.
        """
        stmt = (
            select(RequestORM)
            .where(RequestORM.id == request_id)
            .where(RequestORM.session_id == session_id)
            .options(
                selectinload(RequestORM.pipeline_traces),
                selectinload(RequestORM.claims),
                selectinload(RequestORM.safety_filter_results),
            )
        )
        result = await self._session.execute(stmt)
        row: RequestORM | None = result.scalar_one_or_none()
        if row is None:
            return None

        return RequestDetail(
            id=row.id,
            session_id=row.session_id,
            policy_snapshot_id=row.policy_snapshot_id,
            prompt_hash=row.prompt_hash,
            prompt_masked_text=row.prompt_masked_text,
            model_provider=row.model_provider,
            model_name=row.model_name,
            status=row.status,
            retry_count=row.retry_count,
            total_latency_ms=row.total_latency_ms,
            tokens_in=row.tokens_in,
            tokens_out=row.tokens_out,
            risk_score=row.risk_score,
            confidence_score=row.confidence_score,
            confidence_label=row.confidence_label,
            confidence_signal_breakdown=(
                row.confidence_signal_breakdown
                if isinstance(row.confidence_signal_breakdown, str)
                else None
            ),
            guardrail_decision=row.guardrail_decision,
            decision_reason=row.decision_reason,
            decision_triggered_rule=row.decision_triggered_rule,
            final_response_text=row.final_response_text,
            block_reason=row.block_reason,
            fallback_strategy_used=row.fallback_strategy_used,
            pii_detected=bool(row.pii_detected),
            pii_types_detected=(
                row.pii_types_detected if isinstance(row.pii_types_detected, str) else "[]"
            ),
            created_at=row.created_at,
            completed_at=row.completed_at,
            pipeline_traces=list(row.pipeline_traces),
            request_claims=list(row.claims),
            safety_filter_results=list(row.safety_filter_results),
        )
