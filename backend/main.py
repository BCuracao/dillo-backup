"""PyBackup Sentinel — FastAPI application entry-point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import init_db
from .routers import activity, jobs, system
from .services.activity_logger import cleanup_old_activity_logs
from .services.scheduler import start_scheduler, stop_scheduler

# ── Logging ───────────────────────────────────────────────────────────

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s  %(name)-28s  %(levelname)-7s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)


# ── Lifespan (startup / shutdown) ────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Create DB tables on startup and clean up stale activity logs."""
    await init_db()
    logging.getLogger("pybackup").info("Database initialized.")
    # Auto-cleanup activity logs older than 14 days
    deleted = await cleanup_old_activity_logs()
    if deleted:
        logging.getLogger("pybackup").info("Cleaned up %d old activity log entries.", deleted)
    # Start the cron-based backup scheduler
    start_scheduler()
    logging.getLogger("pybackup").info("Cron scheduler started.")
    yield
    stop_scheduler()


# ── Application ──────────────────────────────────────────────────────

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="A robust local backup management system.",
    lifespan=lifespan,
)

# CORS — allow the Next.js dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount routers
app.include_router(jobs.router)
app.include_router(system.router)
app.include_router(activity.router)
