"""SQLAlchemy ORM models for backup jobs and execution logs."""

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from .database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TZDateTime(TypeDecorator):
    """A DateTime type that ensures timezone-aware UTC datetimes on read.

    SQLite does not store timezone info natively.  When SQLAlchemy reads a
    naive datetime from the database, this decorator attaches ``timezone.utc``
    so that Pydantic serialises ISO strings with the ``+00:00`` suffix and
    JavaScript's ``Date`` constructor interprets them correctly.
    """

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):  # type: ignore[override]
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value

    def process_result_value(self, value, dialect):  # type: ignore[override]
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


class BackupJob(Base):
    __tablename__ = "backup_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_path: Mapped[str] = mapped_column(Text, nullable=False)
    dest_path: Mapped[str] = mapped_column(Text, nullable=False)
    schedule_cron: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, default=None
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        TZDateTime(), default=_utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        TZDateTime(), default=_utcnow, onupdate=_utcnow
    )

    # Relationships
    logs: Mapped[list["JobLog"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<BackupJob {self.name!r} [{self.id}]>"


class ActivityLog(Base):
    """Tracks high-level events: job creation, deletion, execution, etc."""

    __tablename__ = "activity_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_type: Mapped[str] = mapped_column(
        String(30), nullable=False
    )  # JOB_CREATED | JOB_DELETED | JOB_RUN | JOB_DRY_RUN | JOB_COMPLETED | JOB_FAILED
    job_name: Mapped[str] = mapped_column(String(255), nullable=False)
    job_id: Mapped[Optional[uuid.UUID]] = mapped_column(Uuid, nullable=True)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    timestamp: Mapped[datetime] = mapped_column(
        TZDateTime(), default=_utcnow, index=True
    )

    def __repr__(self) -> str:
        return f"<ActivityLog {self.event_type} job={self.job_name!r}>"


class JobLog(Base):
    __tablename__ = "job_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("backup_jobs.id", ondelete="CASCADE"), nullable=False
    )
    start_time: Mapped[datetime] = mapped_column(
        TZDateTime(), default=_utcnow
    )
    end_time: Mapped[Optional[datetime]] = mapped_column(
        TZDateTime(), nullable=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default="RUNNING"
    )  # RUNNING | SUCCESS | ERROR
    files_processed: Mapped[int] = mapped_column(Integer, default=0)
    files_skipped: Mapped[int] = mapped_column(Integer, default=0)
    total_size_mb: Mapped[float] = mapped_column(Float, default=0.0)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_dry_run: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    job: Mapped["BackupJob"] = relationship(back_populates="logs")

    def __repr__(self) -> str:
        return f"<JobLog job={self.job_id} status={self.status}>"
