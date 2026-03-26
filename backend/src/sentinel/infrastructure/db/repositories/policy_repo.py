from __future__ import annotations

from datetime import UTC, datetime
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from sentinel.domain.models.policy import PolicySnapshot
from sentinel.infrastructure.db.models import PolicySnapshotORM


class PolicyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_snapshot(
        self,
        session_id: str,
        policy: PolicySnapshot,
    ) -> str:
        """
        Persist a PolicySnapshot. JSON-serializes list/dict fields.
        Returns the new snapshot UUID.
        """
        snapshot_id = str(uuid.uuid4())
        stmt = sqlite_insert(PolicySnapshotORM).values(
            id=snapshot_id,
            session_id=session_id,
            accept_threshold=policy.accept_threshold,
            warn_threshold=policy.warn_threshold,
            block_threshold=policy.block_threshold,
            max_retries=policy.max_retries,
            restricted_categories=policy.restricted_categories,
            allowed_topics=policy.allowed_topics,
            fallback_priority=policy.fallback_priority,
            module_flags=policy.module_flags,
            created_at=datetime.now(UTC),
        )
        await self._session.execute(stmt)
        await self._session.commit()
        return snapshot_id

    async def get_latest_for_session(self, session_id: str) -> PolicySnapshot | None:
        """
        Returns the most recently created PolicySnapshot for this session,
        or None if no snapshots exist. Deserializes JSON fields.
        """
        result = await self._session.execute(
            select(PolicySnapshotORM)
            .where(PolicySnapshotORM.session_id == session_id)
            .order_by(PolicySnapshotORM.created_at.desc())
            .limit(1)
        )
        row: PolicySnapshotORM | None = result.scalar_one_or_none()
        if row is None:
            return None

        return PolicySnapshot(
            accept_threshold=row.accept_threshold,
            warn_threshold=row.warn_threshold,
            block_threshold=row.block_threshold,
            max_retries=row.max_retries,
            restricted_categories=row.restricted_categories,  # type: ignore[arg-type]
            allowed_topics=row.allowed_topics,  # type: ignore[arg-type]
            fallback_priority=row.fallback_priority,  # type: ignore[arg-type]
            module_flags=row.module_flags,  # type: ignore[arg-type]
        )
