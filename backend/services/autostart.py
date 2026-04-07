"""Cross-platform auto-start management for Dillo.

Windows : HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run registry key
macOS   : ~/Library/LaunchAgents/com.dillo.backup.plist  (LaunchAgent)
Linux   : ~/.config/autostart/dillo.desktop              (XDG autostart)
"""

from __future__ import annotations

import logging
import os
import plistlib
import sys
from pathlib import Path

logger = logging.getLogger("dillo.autostart")

_APP_ID = "Dillo"
_MACOS_LABEL = "com.dillo.backup"
_LINUX_DESKTOP_ID = "dillo"


def _get_exe_path() -> Path | None:
    """Return the path to the launcher executable (frozen builds only)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve()
    return None


# ── Windows ───────────────────────────────────────────────────────────


def _win_get_enabled() -> bool:
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_READ,
        )
        try:
            winreg.QueryValueEx(key, _APP_ID)
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except Exception:
        return False


def _win_set_enabled(enabled: bool) -> bool:
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Run",
            0,
            winreg.KEY_SET_VALUE,
        )
        try:
            if enabled:
                exe = _get_exe_path()
                if exe is None:
                    logger.warning("Cannot enable autostart: not running from a frozen executable.")
                    return False
                winreg.SetValueEx(key, _APP_ID, 0, winreg.REG_SZ, f'"{exe}"')
                logger.info("Windows autostart enabled: %s", exe)
            else:
                try:
                    winreg.DeleteValue(key, _APP_ID)
                except FileNotFoundError:
                    pass
                logger.info("Windows autostart disabled.")
            return True
        finally:
            winreg.CloseKey(key)
    except Exception:
        logger.exception("Failed to update Windows autostart")
        return False


# ── macOS ─────────────────────────────────────────────────────────────


def _macos_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{_MACOS_LABEL}.plist"


def _macos_get_enabled() -> bool:
    return _macos_plist_path().exists()


def _macos_set_enabled(enabled: bool) -> bool:
    plist_path = _macos_plist_path()
    try:
        if enabled:
            exe = _get_exe_path()
            if exe is None:
                logger.warning("Cannot enable autostart: not running from a frozen executable.")
                return False
            plist_data = {
                "Label": _MACOS_LABEL,
                "ProgramArguments": [str(exe)],
                "RunAtLoad": True,
                "KeepAlive": False,
                "StandardOutPath": str(Path.home() / "Library" / "Logs" / "Dillo" / "launcher.log"),
                "StandardErrorPath": str(Path.home() / "Library" / "Logs" / "Dillo" / "launcher.err"),
            }
            plist_path.parent.mkdir(parents=True, exist_ok=True)
            (Path.home() / "Library" / "Logs" / "Dillo").mkdir(parents=True, exist_ok=True)
            with open(plist_path, "wb") as f:
                plistlib.dump(plist_data, f)
            logger.info("macOS LaunchAgent created: %s", plist_path)
        else:
            plist_path.unlink(missing_ok=True)
            logger.info("macOS LaunchAgent removed.")
        return True
    except Exception:
        logger.exception("Failed to update macOS autostart")
        return False


# ── Linux ─────────────────────────────────────────────────────────────


def _linux_desktop_path() -> Path:
    config_home = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    return Path(config_home) / "autostart" / f"{_LINUX_DESKTOP_ID}.desktop"


def _linux_get_enabled() -> bool:
    return _linux_desktop_path().exists()


def _linux_set_enabled(enabled: bool) -> bool:
    desktop_path = _linux_desktop_path()
    try:
        if enabled:
            exe = _get_exe_path()
            if exe is None:
                logger.warning("Cannot enable autostart: not running from a frozen executable.")
                return False
            desktop_path.parent.mkdir(parents=True, exist_ok=True)
            desktop_path.write_text(
                f"[Desktop Entry]\n"
                f"Type=Application\n"
                f"Name=Dillo Backup Manager\n"
                f"Exec={exe}\n"
                f"Hidden=false\n"
                f"NoDisplay=false\n"
                f"X-GNOME-Autostart-enabled=true\n",
                encoding="utf-8",
            )
            logger.info("Linux autostart desktop entry created: %s", desktop_path)
        else:
            desktop_path.unlink(missing_ok=True)
            logger.info("Linux autostart desktop entry removed.")
        return True
    except Exception:
        logger.exception("Failed to update Linux autostart")
        return False


# ── Public API ────────────────────────────────────────────────────────


def is_autostart_enabled() -> bool:
    """Check whether Dillo is configured to start on boot."""
    if sys.platform == "win32":
        return _win_get_enabled()
    elif sys.platform == "darwin":
        return _macos_get_enabled()
    else:
        return _linux_get_enabled()


def set_autostart(enabled: bool) -> bool:
    """Enable or disable auto-start.  Returns True on success."""
    if sys.platform == "win32":
        return _win_set_enabled(enabled)
    elif sys.platform == "darwin":
        return _macos_set_enabled(enabled)
    else:
        return _linux_set_enabled(enabled)
