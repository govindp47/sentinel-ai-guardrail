from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
import uuid

from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel.infrastructure.db.models import AnalyticsCounterORM

# All incrementable counter columns (subset of delta keys allowed)
COUNTER_COLUMNS = frozenset(
    {
        "total_requests",
        "total_accepted",
        "total_warned",
        "total_retried",
        "total_blocked",
        "total_hallucinations_detected",
        "total_safety_triggered",
        "sum_confidence_score",
        "sum_latency_ms",
        "sum_tokens_in",
        "sum_tokens_out",
    }
)


class AnalyticsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert_counters(
        self,
        session_id: str,
        date_bucket: str,
        model_provider: str,
        model_name: str,
        delta: dict[str, int],
    ) -> None:
        """
        Atomic INSERT ... ON CONFLICT DO UPDATE increment.
        `delta` keys must be valid counter column names.
        Unknown keys are silently ignored for safety.
        Never performs a read-modify-write round-trip.
        """
        safe_delta = {k: v for k, v in delta.items() if k in COUNTER_COLUMNS}

        # Build the INSERT row (new row values = delta values themselves)
        insert_values: dict[str, Any] = {
            "id": str(uuid.uuid4()),
            "session_id": session_id,
            "date_bucket": date_bucket,
            "model_provider": model_provider,
            "model_name": model_name,
            "updated_at": datetime.now(UTC),
            **{col: safe_delta.get(col, 0) for col in COUNTER_COLUMNS},
        }

        # Build the ON CONFLICT SET clause: col = col + excluded.col
        update_clause: dict[str, Any] = {
            col: getattr(AnalyticsCounterORM, col)
            + getattr(sqlite_insert(AnalyticsCounterORM).excluded, col)
            for col in safe_delta
        }
        update_clause["updated_at"] = datetime.now(UTC)

        stmt = (
            sqlite_insert(AnalyticsCounterORM)
            .values(**insert_values)
            .on_conflict_do_update(
                index_elements=["session_id", "date_bucket", "model_provider", "model_name"],
                set_=update_clause,
            )
        )
        await self._session.execute(stmt)
        await self._session.commit()
