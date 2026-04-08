"""Incremental backup engine with dry-run support and integrity verification."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import shutil
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..database import async_session_factory
from ..models import BackupJob, JobLog
from ..services.activity_logger import EventType, log_activity
from ..services.path_validator import verify_directory_access

logger = logging.getLogger("pybackup.engine")

# Thread pool shared across all backup runs
_executor = ThreadPoolExecutor(
    max_workers=settings.max_concurrent_copies,
    thread_name_prefix="backup-io",
)


@dataclass
class CopyResult:
    """Result of a single file copy operation."""

    source: Path
    dest: Path
    size_bytes: int = 0
    copied: bool = False
    skipped: bool = False
    error: Optional[str] = None


@dataclass
class BackupReport:
    """Aggregated result of an entire backup run."""

    job_id: uuid.UUID
    files_processed: int = 0
    files_skipped: int = 0
    total_bytes: int = 0
    errors: list[str] = field(default_factory=list)
    dry_run: bool = False
    start_time: float = field(default_factory=time.monotonic)
    end_time: float = 0.0

    @property
    def total_size_mb(self) -> float:
        return round(self.total_bytes / (1024 * 1024), 2) if self.total_bytes else 0.0

    @property
    def elapsed_seconds(self) -> float:
        return round(self.end_time - self.start_time, 2) if self.end_time else 0.0

    @property
    def status(self) -> str:
        if self.errors:
            return "ERROR"
        return "SUCCESS"


class BackupManager:
    """Handles incremental backup logic with concurrency and safety checks."""

    # ── Public API ────────────────────────────────────────────────────

    @classmethod
    async def run_backup(
        cls,
        job_id: uuid.UUID,
        dry_run: bool = False,
        force_system_drive: bool = False,
        verify_after_copy: bool = False,
    ) -> BackupReport:
        """
        Entry-point: load the job from DB, execute the backup, and persist a log.
        Designed to be called from a FastAPI BackgroundTask.
        """
        async with async_session_factory() as session:
            job = await session.get(BackupJob, job_id)
            if job is None:
                raise ValueError(f"BackupJob {job_id} not found.")

            source = Path(job.source_path)
            dest = Path(job.dest_path)
            job_name = job.name
            job_source = job.source_path
            job_dest = job.dest_path

            # Pre-flight checks (path access + safety lock).
            # Failures here used to silently vanish in the background task,
            # so we catch them and persist a proper ERROR log + activity entry.
            try:
                src_check = verify_directory_access(job_source)
                if not src_check.accessible:
                    raise FileNotFoundError(
                        f"Source path is not accessible: {job_source} "
                        f"({src_check.error or 'unknown'})"
                    )
                dst_check = verify_directory_access(job_dest)
                if not dst_check.accessible:
                    raise FileNotFoundError(
                        f"Destination path is not accessible: {job_dest} "
                        f"({dst_check.error or 'unknown'})"
                    )
                cls._check_safety_lock(dest, force_system_drive)
            except Exception as preflight_exc:
                logger.error("Pre-flight check failed for job %s: %s", job_id, preflight_exc)
                error_log = JobLog(
                    job_id=job_id,
                    start_time=datetime.now(timezone.utc),
                    end_time=datetime.now(timezone.utc),
                    status="ERROR",
                    is_dry_run=dry_run,
                    error_message=str(preflight_exc),
                )
                session.add(error_log)
                await session.commit()
                await log_activity(
                    event_type=EventType.JOB_FAILED,
                    job_name=job_name,
                    message=f"Backup failed (pre-flight): {job_source} → {job_dest}",
                    job_id=job_id,
                    details=str(preflight_exc),
                )
                report = BackupReport(job_id=job_id, dry_run=dry_run)
                report.errors.append(str(preflight_exc))
                report.end_time = time.monotonic()
                return report

            # Create a RUNNING log entry
            log_entry = JobLog(
                job_id=job_id,
                start_time=datetime.now(timezone.utc),
                status="RUNNING",
                is_dry_run=dry_run,
            )
            session.add(log_entry)
            await session.commit()
            await session.refresh(log_entry)

            report = BackupReport(job_id=job_id, dry_run=dry_run)

            try:
                await cls._incremental_backup(
                    source, dest, report,
                    log_entry_id=log_entry.id,
                    verify=verify_after_copy,
                )
            except Exception as exc:
                report.errors.append(f"Fatal: {exc}")
                logger.exception("Backup failed for job %s", job_id)
            finally:
                report.end_time = time.monotonic()

            # Update the log entry with final results
            log_entry.end_time = datetime.now(timezone.utc)
            log_entry.status = report.status
            log_entry.files_processed = report.files_processed
            log_entry.files_skipped = report.files_skipped
            log_entry.total_size_mb = report.total_size_mb
            if report.errors:
                log_entry.error_message = "\n".join(report.errors[:50])
            await session.commit()

            logger.info(
                "Backup %s completed: %s | %d files | %.2f MB | %.1fs",
                job_id,
                report.status,
                report.files_processed,
                report.total_size_mb,
                report.elapsed_seconds,
            )

            # Activity log: backup completed or failed
            event = EventType.JOB_COMPLETED if report.status == "SUCCESS" else EventType.JOB_FAILED
            mode_label = "Dry-run" if dry_run else "Backup"
            details = (
                f"Files: {report.files_processed} copied, {report.files_skipped} skipped | "
                f"Size: {report.total_size_mb} MB | Time: {report.elapsed_seconds}s"
            )
            if report.errors:
                details += f" | Errors: {len(report.errors)}"
            await log_activity(
                event_type=event,
                job_name=job_name,
                message=f"{mode_label} {report.status.lower()}: {job_source} → {job_dest}",
                job_id=job_id,
                details=details,
            )

        return report

    # ── Estimation ─────────────────────────────────────────────────────

    @classmethod
    async def estimate_backup(cls, job_id: uuid.UUID) -> dict:
        """
        Scan the source tree and compare against the destination to estimate
        the number of files and total bytes that would be copied.
        Does NOT copy anything — read-only operation.
        """
        async with async_session_factory() as session:
            job = await session.get(BackupJob, job_id)
            if job is None:
                raise ValueError(f"BackupJob {job_id} not found.")

            source = Path(job.source_path)
            dest = Path(job.dest_path)

            loop = asyncio.get_running_loop()
            scan_start = time.monotonic()

            file_pairs = await loop.run_in_executor(
                _executor, cls._scan_source_tree, source, dest
            )

            # Compare each pair to see what would actually be copied
            total_files = 0
            skipped_files = 0
            total_bytes = 0

            for src, dst in file_pairs:
                try:
                    src_stat = src.stat()
                    size = src_stat.st_size
                    if dst.exists():
                        dst_stat = dst.stat()
                        same_size = src_stat.st_size == dst_stat.st_size
                        src_newer = src_stat.st_mtime > dst_stat.st_mtime
                        if same_size and not src_newer:
                            skipped_files += 1
                            continue
                    total_files += 1
                    total_bytes += size
                except (PermissionError, OSError):
                    pass

            scan_duration = round(time.monotonic() - scan_start, 2)
            size_mb = round(total_bytes / (1024 * 1024), 2) if total_bytes else 0.0
            # Rough estimate: ~50 MB/s on typical local disk
            estimated_time = round(size_mb / 50, 1) if size_mb > 0 else 0.0

            return {
                "total_files": total_files,
                "skipped_files": skipped_files,
                "estimated_size_mb": size_mb,
                "estimated_time_seconds": estimated_time,
                "scan_duration_seconds": scan_duration,
            }

    # ── Progress Flushing ─────────────────────────────────────────────

    _FLUSH_EVERY_N = 25  # flush progress to DB every N completed files
    _FLUSH_EVERY_S = 3.0  # or every N seconds, whichever comes first

    @classmethod
    async def _flush_progress(cls, log_entry_id: int, report: BackupReport) -> None:
        """Write intermediate progress to the JobLog row so the frontend can poll it."""
        try:
            async with async_session_factory() as session:
                log_entry = await session.get(JobLog, log_entry_id)
                if log_entry and log_entry.status == "RUNNING":
                    log_entry.files_processed = report.files_processed
                    log_entry.files_skipped = report.files_skipped
                    log_entry.total_size_mb = report.total_size_mb
                    await session.commit()
        except Exception:
            logger.debug("Progress flush failed (non-critical)", exc_info=True)

    # ── Core Incremental Logic ────────────────────────────────────────

    @classmethod
    async def _incremental_backup(
        cls,
        source: Path,
        dest: Path,
        report: BackupReport,
        log_entry_id: int | None = None,
        verify: bool = False,
    ) -> None:
        """
        Walk the source tree and copy only files that are newer or
        different in size compared to the destination.
        Streams progress to the DB every _FLUSH_EVERY_N files or _FLUSH_EVERY_S seconds.
        """
        loop = asyncio.get_running_loop()

        # Collect work items from the source tree (blocking I/O in thread)
        file_pairs = await loop.run_in_executor(
            _executor, cls._scan_source_tree, source, dest
        )

        # Process copies with bounded concurrency
        semaphore = asyncio.Semaphore(settings.max_concurrent_copies)

        async def _guarded_copy(src: Path, dst: Path) -> CopyResult:
            async with semaphore:
                return await loop.run_in_executor(
                    _executor, cls._copy_if_needed, src, dst, report.dry_run, verify
                )

        tasks = [asyncio.ensure_future(_guarded_copy(src, dst)) for src, dst in file_pairs]

        flush_counter = 0
        last_flush = time.monotonic()

        for future in asyncio.as_completed(tasks):
            try:
                result = await future
            except Exception as exc:
                report.errors.append(str(exc))
                flush_counter += 1
                continue

            if result.error:
                report.errors.append(result.error)
            if result.copied:
                report.files_processed += 1
                report.total_bytes += result.size_bytes
            elif result.skipped:
                report.files_skipped += 1

            flush_counter += 1
            now = time.monotonic()
            if log_entry_id and (
                flush_counter >= cls._FLUSH_EVERY_N
                or (now - last_flush) >= cls._FLUSH_EVERY_S
            ):
                await cls._flush_progress(log_entry_id, report)
                flush_counter = 0
                last_flush = now

    # ── File Scanning ─────────────────────────────────────────────────

    @staticmethod
    def _scan_source_tree(source: Path, dest: Path) -> list[tuple[Path, Path]]:
        """
        Use os.scandir for fast recursive enumeration.
        Returns a list of (source_file, dest_file) pairs.
        """
        pairs: list[tuple[Path, Path]] = []

        def _recurse(current: Path) -> None:
            try:
                with os.scandir(current) as it:
                    for entry in it:
                        if entry.is_dir(follow_symlinks=False):
                            _recurse(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            src_path = Path(entry.path)
                            relative = src_path.relative_to(source)
                            dst_path = dest / relative
                            pairs.append((src_path, dst_path))
            except PermissionError as exc:
                logger.warning("Permission denied scanning %s: %s", current, exc)

        _recurse(source)
        return pairs

    # ── Incremental Copy ──────────────────────────────────────────────

    @classmethod
    def _copy_if_needed(cls, src: Path, dst: Path, dry_run: bool, verify: bool = False) -> CopyResult:
        """
        Compare mtime + size.  Copy only when the source is newer or a
        different size.  In dry-run mode, log but don't write.
        When *verify* is True, run SHA-256 comparison after each real copy.
        """
        result = CopyResult(source=src, dest=dst)

        try:
            src_stat = src.stat()
            result.size_bytes = src_stat.st_size

            # Check if dest exists and is already up-to-date
            if dst.exists():
                dst_stat = dst.stat()
                same_size = src_stat.st_size == dst_stat.st_size
                src_newer = src_stat.st_mtime > dst_stat.st_mtime
                if same_size and not src_newer:
                    result.skipped = True
                    return result

            # Need to copy
            if dry_run:
                logger.info("[DRY RUN] Would copy %s -> %s", src, dst)
                result.copied = True
                return result

            # Ensure parent directory exists
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(src), str(dst))
            result.copied = True

            # Post-copy SHA-256 verification
            if verify and result.copied:
                if not cls.verify_copy(src, dst):
                    result.error = f"Verification failed (SHA-256 mismatch): {dst}"
                    logger.warning("SHA-256 mismatch after copy: %s -> %s", src, dst)

        except PermissionError:
            result.error = f"Permission denied: {src}"
        except OSError as exc:
            result.error = f"OS error copying {src}: {exc}"

        return result

    # ── Safety Lock ───────────────────────────────────────────────────

    @staticmethod
    def _check_safety_lock(dest: Path, force: bool) -> None:
        """
        Prevent writing to protected drives/paths (e.g. C:\\ on Windows,
        /System or / on macOS) unless explicitly forced by the user.
        """
        if force:
            logger.warning("Safety Lock overridden for destination: %s", dest)
            return

        resolved = str(dest.resolve())
        if os.name == "nt":
            dest_drive = os.path.splitdrive(resolved)[0] + os.sep
            for protected in settings.protected_drives:
                if dest_drive.upper() == protected.upper():
                    raise PermissionError(
                        f"Safety Lock: destination drive '{dest_drive}' is protected. "
                        f"Set force_system_drive=true to override."
                    )
        else:
            for protected in settings.protected_drives:
                norm = protected.rstrip("/")
                if not norm:
                    # Bare "/" — only block the root directory itself
                    if resolved == "/":
                        raise PermissionError(
                            f"Safety Lock: destination is the filesystem root. "
                            f"Set force_system_drive=true to override."
                        )
                elif resolved == protected or resolved.startswith(norm + "/"):
                    raise PermissionError(
                        f"Safety Lock: destination path '{resolved}' is inside "
                        f"protected area '{protected}'. "
                        f"Set force_system_drive=true to override."
                    )

    # ── Integrity Verification (SHA-256) ──────────────────────────────

    @staticmethod
    def file_checksum(path: Path, algorithm: str = "sha256") -> str:
        """Compute a hex digest for a file."""
        h = hashlib.new(algorithm)
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    @classmethod
    def verify_copy(cls, src: Path, dst: Path) -> bool:
        """Return True if source and dest share the same SHA-256 digest."""
        return cls.file_checksum(src) == cls.file_checksum(dst)
