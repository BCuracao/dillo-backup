"""Application configuration via pydantic-settings."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

IS_FROZEN = getattr(sys, "frozen", False)

# Backend package directory (code location)
BASE_DIR = (
    Path(sys.executable).resolve().parent
    if IS_FROZEN
    else Path(__file__).resolve().parent
)


def _resolve_data_dir() -> Path:
    """Per-platform user data directory in production, backend/ in dev."""
    if IS_FROZEN:
        if sys.platform == "darwin":
            data_dir = Path.home() / "Library" / "Application Support" / "Dillo Backup"
        elif sys.platform == "win32":
            root = Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
            data_dir = root / "Dillo Backup"
        else:
            # Linux / other: XDG_DATA_HOME or ~/.local/share
            xdg = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))
            data_dir = Path(xdg) / "dillo-backup"
    else:
        data_dir = Path(__file__).resolve().parent
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


DATA_DIR = _resolve_data_dir()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="PYBACKUP_",
        case_sensitive=False,
    )

    app_name: str = "Dillo Backup"
    database_url: str = f"sqlite+aiosqlite:///{DATA_DIR / 'backups.db'}"
    cors_origins: list[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]
    log_level: str = "INFO"

    protected_drives: list[str] = (
        ["C:\\"] if sys.platform == "win32"
        else ["/System", "/usr", "/bin", "/sbin"] if sys.platform == "darwin"
        else ["/usr", "/bin", "/sbin"]
    )
    max_concurrent_copies: int = 4


settings = Settings()
DB_PATH = DATA_DIR / "backups.db"
