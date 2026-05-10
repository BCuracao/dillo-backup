"""Async SQLAlchemy 2.0 engine & session factory for SQLite."""

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from .config import settings

logger = logging.getLogger("pybackup.database")

engine = create_async_engine(
    settings.database_url,
    echo=False,
    # SQLite requires this for async usage
    connect_args={"check_same_thread": False},
)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""
    pass


async def get_db() -> AsyncSession:  # type: ignore[misc]
    """FastAPI dependency that yields an async DB session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


# ── Lightweight Migrations ────────────────────────────────────────────

# Columns that may be missing on databases created before these features
# shipped.  Each tuple is (table, column, sqlite_column_definition).
# Sqlalchemy's ``metadata.create_all`` only creates missing tables; it does
# not add new columns to existing tables, so we patch the schema in-place.
_PENDING_COLUMN_MIGRATIONS: list[tuple[str, str, str]] = [
    ("backup_jobs", "job_auto_wake", "BOOLEAN"),
    ("backup_jobs", "job_versioning_limit", "INTEGER"),
]


async def _apply_column_migrations(conn) -> None:
    """Add any columns introduced after the initial schema, idempotently."""
    for table, column, ddl in _PENDING_COLUMN_MIGRATIONS:
        result = await conn.exec_driver_sql(f"PRAGMA table_info({table})")
        existing = {row[1] for row in result.fetchall()}
        if column not in existing:
            logger.info("Migration: adding %s.%s (%s)", table, column, ddl)
            await conn.exec_driver_sql(
                f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"
            )


async def _seed_global_settings(conn) -> None:
    """Insert the singleton settings row with defaults if it doesn't exist yet."""
    result = await conn.exec_driver_sql(
        "SELECT COUNT(*) FROM global_settings WHERE id = 1"
    )
    (count,) = result.fetchone()
    if count == 0:
        await conn.execute(
            text(
                "INSERT INTO global_settings (id, global_auto_wake, "
                "global_versioning_limit, updated_at) "
                "VALUES (1, 0, 0, CURRENT_TIMESTAMP)"
            )
        )
        logger.info("Seeded default global_settings row.")


async def init_db() -> None:
    """Create all tables, then apply lightweight column migrations + seed singletons."""
    async with engine.begin() as conn:
        from . import models as _models  # noqa: F401 – ensure models are imported
        await conn.run_sync(Base.metadata.create_all)
        await _apply_column_migrations(conn)
        await _seed_global_settings(conn)
