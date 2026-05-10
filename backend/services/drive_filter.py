"""Shared filter that hides virtual / installer volumes from the drive list.

Used by both the public ``/api/system/drives`` endpoint and the Auto-Wake
drive watcher so the same heuristics decide what counts as a real backup
target.

A volume is *ignored* when **any** of these are true:
  * Its display name is exactly ``Dillo`` or ``Dillo Backup`` (case-insensitive,
    optionally suffixed by `` 1`` / `` 2`` / ... when macOS de-duplicates names).
  * On macOS, its mount path lives under ``/Volumes/Dillo`` (covers the
    installer DMG and any spillover names like ``Dillo Backup 1``).
  * The mount is read-only (mounted DMGs almost always are; nothing useful as
    a backup destination is read-only).
  * Its total capacity is below ``MIN_VOLUME_SIZE_BYTES`` (default 500 MB) —
    knocks out tiny installer DMGs, recovery partitions and similar noise.

Windows drives don't have a mount-path heuristic, so only the name / size /
read-only checks apply there.
"""

from __future__ import annotations

import logging
import os
import shutil
import stat
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger("pybackup.drive_filter")

# 500 MB — anything smaller is almost certainly an installer / recovery image
# rather than a backup target.
MIN_VOLUME_SIZE_BYTES: int = 500 * 1024 * 1024

# Exact names (case-insensitive) the app must never list as backup targets.
_BLOCKED_EXACT_NAMES: frozenset[str] = frozenset({"dillo", "dillo backup"})

# Names beginning with these prefixes (case-insensitive) are ignored —
# catches macOS' auto-renamed duplicates like "Dillo Backup 1".
_BLOCKED_NAME_PREFIXES: tuple[str, ...] = ("dillo backup", "dillo ")


def _is_blocked_name(name: str) -> bool:
    """Return True when *name* matches a Dillo installer volume label."""
    if not name:
        return False
    lowered = name.strip().lower()
    if lowered in _BLOCKED_EXACT_NAMES:
        return True
    return any(lowered.startswith(prefix) for prefix in _BLOCKED_NAME_PREFIXES)


def _is_blocked_macos_path(path: str) -> bool:
    """Return True when *path* is a macOS mount under ``/Volumes/Dillo*``."""
    if sys.platform != "darwin":
        return False
    try:
        normalized = os.path.normpath(path)
    except Exception:
        return False
    parts = normalized.split(os.sep)
    if len(parts) < 3 or parts[1] != "Volumes":
        return False
    leaf = parts[2]
    return leaf.lower().startswith("dillo")


def _is_read_only_mount(path: str) -> bool:
    """Return True when *path* is mounted read-only (DMG-style)."""
    try:
        info = os.statvfs(path)
    except (AttributeError, OSError):
        return False
    # ST_RDONLY is bit 0 of f_flag on POSIX; Python re-exports it via
    # ``os.ST_RDONLY`` (= 1) on supported platforms.
    rdonly_flag = getattr(os, "ST_RDONLY", 1)
    return bool(info.f_flag & rdonly_flag)


def _is_read_only_attrib_windows(path: str) -> bool:
    """Best-effort read-only probe for Windows volumes via attribute byte."""
    try:
        st = os.stat(path)
    except OSError:
        return False
    file_attribute_readonly = getattr(stat, "FILE_ATTRIBUTE_READONLY", 0x1)
    file_attrs = getattr(st, "st_file_attributes", 0)
    return bool(file_attrs & file_attribute_readonly)


def should_ignore_volume(
    path: str,
    *,
    name: Optional[str] = None,
    total_bytes: Optional[int] = None,
) -> bool:
    """Return True when *path* should be hidden from the backup-target list.

    ``name`` and ``total_bytes`` are derived automatically when not supplied;
    callers that have already paid for these stats can pass them through to
    avoid duplicate syscalls.
    """
    if not path:
        return True

    resolved_name = name if name is not None else (Path(path).name or path)

    if _is_blocked_name(resolved_name):
        logger.debug("Filtering volume %s — blocked name %r.", path, resolved_name)
        return True

    if _is_blocked_macos_path(path):
        logger.debug("Filtering volume %s — Dillo* mount path.", path)
        return True

    if total_bytes is None:
        try:
            total_bytes = shutil.disk_usage(path).total
        except OSError:
            total_bytes = None

    if total_bytes is not None and 0 < total_bytes < MIN_VOLUME_SIZE_BYTES:
        logger.debug(
            "Filtering volume %s — below %d MB threshold (%d bytes).",
            path, MIN_VOLUME_SIZE_BYTES // (1024 * 1024), total_bytes,
        )
        return True

    if sys.platform == "win32":
        if _is_read_only_attrib_windows(path):
            logger.debug("Filtering volume %s — read-only attribute set.", path)
            return True
    else:
        if _is_read_only_mount(path):
            logger.debug("Filtering volume %s — mounted read-only.", path)
            return True

    return False


__all__ = ["MIN_VOLUME_SIZE_BYTES", "should_ignore_volume"]
