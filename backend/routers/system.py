"""System-level API endpoints (drives, health, path validation, etc.)."""

from __future__ import annotations

import logging
import os
import platform
import shutil
import stat as stat_mod
import string
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ..schemas import (
    AutoStartRequest,
    AutoStartStatusResponse,
    BrowseResponse,
    DirectoryEntry,
    DriveInfo,
    PathValidationRequest,
    PathValidationResponse,
    SystemDrivesResponse,
)
from ..services.autostart import is_autostart_enabled, set_autostart
from ..services.path_validator import verify_directory_access

logger = logging.getLogger("pybackup.api.system")

router = APIRouter(prefix="/api/system", tags=["system"])


def _probe_drive(drive_path: str) -> bool:
    """Return True if a drive responds to *any* OS-level probe."""
    try:
        os.stat(drive_path)
        return True
    except OSError:
        pass
    try:
        with os.scandir(drive_path):
            return True
    except OSError:
        pass
    return False


@router.get(
    "/drives",
    response_model=SystemDrivesResponse,
    summary="List available drives / volumes",
)
async def list_drives() -> SystemDrivesResponse:
    """
    Detect available drives on Windows or mount-points on Unix-like systems.
    Uses multi-strategy probing to discover virtual/cloud drives that fail
    standard ``Path.exists()`` checks (e.g. Filen.io / Dokan / WinFsp).
    """
    drives: list[DriveInfo] = []

    if platform.system() == "Windows":
        for letter in string.ascii_uppercase:
            drive_path = f"{letter}:\\"
            if not (Path(drive_path).exists() or _probe_drive(drive_path)):
                continue
            try:
                usage = shutil.disk_usage(drive_path)
                drives.append(
                    DriveInfo(
                        path=drive_path,
                        label=f"Drive {letter}:",
                        total_gb=round(usage.total / (1024**3), 2),
                        free_gb=round(usage.free / (1024**3), 2),
                        fs_type="NTFS",
                    )
                )
            except OSError:
                # Drive responds to a probe but disk_usage fails — still list it
                drives.append(
                    DriveInfo(
                        path=drive_path,
                        label=f"Drive {letter}: (virtual)",
                        total_gb=0,
                        free_gb=0,
                        fs_type="virtual",
                    )
                )
    else:
        if platform.system() == "Darwin":
            mounts = ["/"]
            # macOS mounts external drives under /Volumes
            volumes = Path("/Volumes")
            if volumes.is_dir():
                try:
                    for entry in volumes.iterdir():
                        if entry.is_dir() and not entry.is_symlink():
                            mounts.append(str(entry))
                except OSError:
                    pass
        else:
            mounts = ["/", "/home", "/mnt", "/media"]

        for mount in mounts:
            mp = Path(mount)
            if mp.exists() and mp.is_dir():
                try:
                    usage = shutil.disk_usage(mount)
                    drives.append(
                        DriveInfo(
                            path=mount,
                            label=mp.name or "/",
                            total_gb=round(usage.total / (1024**3), 2),
                            free_gb=round(usage.free / (1024**3), 2),
                            fs_type="apfs" if platform.system() == "Darwin" else "ext4",
                        )
                    )
                except OSError:
                    pass

    return SystemDrivesResponse(drives=drives)


@router.get(
    "/browse",
    response_model=BrowseResponse,
    summary="Browse directories at a given path",
)
async def browse_directory(path: str = "") -> BrowseResponse:
    """
    List subdirectories of the given path.
    If path is empty, return available drive roots (Windows) or mount-points (Unix).
    Only returns directories, never files — designed for folder selection.
    Uses multi-strategy probing so virtual/cloud drives appear in the root list.
    """
    if not path:
        drives: list[DirectoryEntry] = []
        if platform.system() == "Windows":
            for letter in string.ascii_uppercase:
                drive_path = f"{letter}:\\"
                if Path(drive_path).exists() or _probe_drive(drive_path):
                    drives.append(
                        DirectoryEntry(
                            name=f"{letter}:\\",
                            path=drive_path,
                            is_drive=True,
                        )
                    )
        else:
            if platform.system() == "Darwin":
                browse_roots = ["/", "/Users", "/Volumes"]
            else:
                browse_roots = ["/", "/home", "/mnt", "/media"]
            for mount in browse_roots:
                mp = Path(mount)
                if mp.exists() and mp.is_dir():
                    drives.append(
                        DirectoryEntry(
                            name=mp.name or "/",
                            path=mount,
                            is_drive=True,
                        )
                    )
        return BrowseResponse(
            current_path="",
            parent_path=None,
            directories=drives,
        )

    target = Path(path)

    # Use multi-strategy check: standard first, then scandir/stat fallback
    target_accessible = target.is_dir()
    if not target_accessible:
        try:
            st = os.stat(str(target))
            target_accessible = stat_mod.S_ISDIR(st.st_mode)
        except OSError:
            pass
    if not target_accessible:
        try:
            with os.scandir(str(target)):
                target_accessible = True
        except OSError:
            pass

    if not target_accessible:
        resolved = str(target.resolve()) if target.exists() else str(target)
        parent = str(target.parent) if target.parent != target else None
        return BrowseResponse(
            current_path=resolved,
            parent_path=parent,
            directories=[],
        )

    entries: list[DirectoryEntry] = []
    try:
        with os.scandir(str(target)) as it:
            for entry in sorted(it, key=lambda e: e.name.lower()):
                try:
                    if not entry.is_dir(follow_symlinks=False):
                        continue
                except OSError:
                    continue
                name = entry.name
                if name.startswith(".") or name.startswith("$"):
                    continue
                entries.append(
                    DirectoryEntry(name=name, path=entry.path)
                )
    except (PermissionError, OSError) as exc:
        logger.warning("Cannot read directory %s: %s", target, exc)

    parent = str(target.parent) if target.parent != target else None

    return BrowseResponse(
        current_path=str(target),
        parent_path=parent,
        directories=entries,
    )


@router.post(
    "/validate-path",
    response_model=PathValidationResponse,
    summary="Validate that a directory path is accessible (supports cloud/virtual drives)",
)
async def validate_path(body: PathValidationRequest) -> PathValidationResponse:
    """
    Run a multi-strategy "canary test" on the given path.  Returns detailed
    feedback about accessibility and write permission so the frontend can
    display specific guidance (e.g. "drive found but access denied").
    """
    result = verify_directory_access(body.path)
    return PathValidationResponse(
        path=body.path,
        accessible=result.accessible,
        writable=result.writable if body.check_writable else result.writable,
        method=result.method,
        error=result.error,
    )


@router.get(
    "/autostart",
    response_model=AutoStartStatusResponse,
    summary="Check if Dillo Backup is set to auto-start on boot",
)
async def get_autostart_status() -> AutoStartStatusResponse:
    return AutoStartStatusResponse(
        enabled=is_autostart_enabled(),
        platform=platform.system().lower(),
    )


@router.put(
    "/autostart",
    response_model=AutoStartStatusResponse,
    summary="Enable or disable auto-start on boot",
)
async def update_autostart(body: AutoStartRequest) -> AutoStartStatusResponse:
    success = set_autostart(body.enabled)
    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to update auto-start setting. Check logs for details.",
        )
    return AutoStartStatusResponse(
        enabled=is_autostart_enabled(),
        platform=platform.system().lower(),
    )


@router.get("/health", summary="Health check")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}
