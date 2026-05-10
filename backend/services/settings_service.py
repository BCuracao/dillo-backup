"""Singleton accessor for application-wide global settings.

Reads/writes the row in ``global_settings`` (id == 1) that holds defaults
for the Auto-Wake and Time Capsule features.  Per-job settings override
these globals when set; a NULL on the job means "inherit".
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from ..database import async_session_factory
from ..models import GlobalSettings

logger = logging.getLogger("pybackup.settings")

# Hard limits the UI exposes via the slider (kept in sync with schemas).
MIN_VERSIONING_LIMIT = 0
MAX_VERSIONING_LIMIT = 50


@dataclass(frozen=True)
class GlobalSettingsSnapshot:
    """Plain DTO so consumers don't carry a live ORM session."""

    global_auto_wake: bool
    global_versioning_limit: int


async def _load_or_create(session: AsyncSession) -> GlobalSettings:
    """Fetch the singleton row, inserting one with defaults if absent."""
    record = await session.get(GlobalSettings, 1)
    if record is None:
        record = GlobalSettings(
            id=1,
            global_auto_wake=False,
            global_versioning_limit=0,
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
    return record


async def get_global_settings() -> GlobalSettingsSnapshot:
    """Return the current global defaults."""
    async with async_session_factory() as session:
        record = await _load_or_create(session)
        return GlobalSettingsSnapshot(
            global_auto_wake=bool(record.global_auto_wake),
            global_versioning_limit=int(record.global_versioning_limit or 0),
        )


async def update_global_settings(
    *,
    global_auto_wake: Optional[bool] = None,
    global_versioning_limit: Optional[int] = None,
) -> GlobalSettingsSnapshot:
    """Patch the singleton row.  Unspecified fields are left untouched."""
    async with async_session_factory() as session:
        record = await _load_or_create(session)

        if global_auto_wake is not None:
            record.global_auto_wake = bool(global_auto_wake)

        if global_versioning_limit is not None:
            limit = int(global_versioning_limit)
            if limit < MIN_VERSIONING_LIMIT or limit > MAX_VERSIONING_LIMIT:
                raise ValueError(
                    f"global_versioning_limit must be between {MIN_VERSIONING_LIMIT} "
                    f"and {MAX_VERSIONING_LIMIT} (got {limit})."
                )
            record.global_versioning_limit = limit

        await session.commit()
        await session.refresh(record)
        return GlobalSettingsSnapshot(
            global_auto_wake=bool(record.global_auto_wake),
            global_versioning_limit=int(record.global_versioning_limit or 0),
        )


def resolve_auto_wake(job_value: Optional[bool], snapshot: GlobalSettingsSnapshot) -> bool:
    """Combine a per-job override with the global default."""
    return bool(snapshot.global_auto_wake if job_value is None else job_value)


def resolve_versioning_limit(
    job_value: Optional[int], snapshot: GlobalSettingsSnapshot
) -> int:
    """Combine a per-job override with the global default.  Always returns >= 0."""
    if job_value is None:
        return max(0, int(snapshot.global_versioning_limit or 0))
    return max(0, int(job_value))
