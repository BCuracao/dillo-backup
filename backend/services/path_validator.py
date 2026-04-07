"""Multi-strategy path validation for cloud/virtual drives (Dokan, WinFsp, etc.)."""

from __future__ import annotations

import logging
import os
import stat as stat_mod
import uuid
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger("pybackup.path_validator")


@dataclass
class PathValidationResult:
    """Outcome of a multi-strategy directory access check."""

    accessible: bool
    writable: bool
    method: str  # which strategy confirmed access
    error: str | None = None


def _test_writable(target: Path) -> bool:
    """Attempt to create and immediately delete a hidden canary file."""
    canary = target / f".dillo_canary_{uuid.uuid4().hex[:8]}"
    try:
        canary.touch()
        canary.unlink(missing_ok=True)
        return True
    except (PermissionError, OSError):
        return False


def verify_directory_access(path: str) -> PathValidationResult:
    """
    Validate that *path* points to a real, accessible directory.

    Virtual filesystems (Filen.io / Dokan / WinFsp) often fail standard
    ``os.path.isdir()`` or ``Path.exists()`` calls because their driver
    does not broadcast metadata the way NTFS does.  This function walks
    through progressively more aggressive strategies:

    1. Standard ``Path.is_dir()``
    2. ``os.scandir()`` probe (many FUSE drivers respond to readdir)
    3. ``os.stat()`` + ``S_ISDIR`` flag check
    4. Canary file: create + delete a hidden temp file
    5. Drive-root fallback (Windows only) — detects the drive but marks
       the specific sub-path as inaccessible
    """
    p = Path(path)

    # Strategy 1 — standard metadata check
    if p.is_dir():
        writable = _test_writable(p)
        return PathValidationResult(
            accessible=True, writable=writable, method="standard",
        )

    # Strategy 2 — readdir via os.scandir
    try:
        with os.scandir(path) as it:
            next(it, None)  # one entry is enough to prove the dir exists
        writable = _test_writable(p)
        return PathValidationResult(
            accessible=True, writable=writable, method="scandir",
        )
    except PermissionError:
        return PathValidationResult(
            accessible=True, writable=False, method="scandir",
            error="path_found_access_denied",
        )
    except OSError:
        pass

    # Strategy 3 — raw stat() call
    try:
        st = os.stat(path)
        if stat_mod.S_ISDIR(st.st_mode):
            writable = _test_writable(p)
            return PathValidationResult(
                accessible=True, writable=writable, method="stat",
            )
    except PermissionError:
        return PathValidationResult(
            accessible=True, writable=False, method="stat",
            error="path_found_access_denied",
        )
    except OSError:
        pass

    # Strategy 4 — canary file (proves the path is real AND writable)
    canary = p / f".dillo_canary_{uuid.uuid4().hex[:8]}"
    try:
        p.mkdir(parents=True, exist_ok=True)
        canary.touch()
        canary.unlink(missing_ok=True)
        return PathValidationResult(
            accessible=True, writable=True, method="canary_file",
        )
    except PermissionError:
        return PathValidationResult(
            accessible=True, writable=False, method="canary_file",
            error="path_found_write_denied",
        )
    except OSError:
        pass

    # Strategy 5 — Windows drive-root check
    drive, _ = os.path.splitdrive(path)
    if drive:
        drive_root = drive + os.sep
        try:
            os.stat(drive_root)
            return PathValidationResult(
                accessible=False, writable=False, method="none",
                error="drive_exists_path_inaccessible",
            )
        except OSError:
            pass

    # UNC path root probe (e.g. \\server\share)
    if path.startswith("\\\\"):
        parts = path.replace("/", "\\").split("\\")
        # \\server\share -> minimum 4 parts ["", "", "server", "share"]
        if len(parts) >= 4:
            unc_root = f"\\\\{parts[2]}\\{parts[3]}"
            try:
                os.stat(unc_root)
                return PathValidationResult(
                    accessible=False, writable=False, method="none",
                    error="unc_share_exists_path_inaccessible",
                )
            except OSError:
                pass

    return PathValidationResult(
        accessible=False, writable=False, method="none",
        error="path_not_found",
    )


def is_path_accessible(path: str) -> bool:
    """Quick boolean check — True if the path can be reached by any strategy."""
    return verify_directory_access(path).accessible
