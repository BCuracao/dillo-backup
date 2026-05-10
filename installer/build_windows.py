"""Dillo Backup — Windows build script.

Orchestrates the full build pipeline:
  1. Build the Python backend into a standalone exe (PyInstaller)
  2. Build the Next.js frontend in standalone mode
  3. Download a portable Node.js runtime
  4. Bundle the launcher into a standalone exe (DilloBackup.exe)
  5. Assemble everything into dist/dillo/
  6. (Optional) Compile the Inno Setup installer

Prerequisites:
  - Python 3.12+ on PATH (with pip)
  - Node.js 18+ on PATH (with npm)
  - (Optional) Inno Setup 6 installed for .exe installer generation

Usage:
  python installer/build_windows.py [--skip-inno] [--node-version 22.14.0]

Output:
  dist/installer/Dillo-Backup-Setup-1.0.3.exe
"""

from __future__ import annotations

import argparse
import io
import logging
import os
import platform
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.request import urlopen

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("build")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
INSTALLER_DIR = PROJECT_ROOT / "installer"
DIST_DIR = PROJECT_ROOT / "dist" / "dillo"

NODE_VERSION_DEFAULT = "22.14.0"
NODE_ARCH = "x64" if platform.machine().endswith("64") else "x86"


# ── Helpers ──────────────────────────────────────────────────────────


def run(cmd: list[str], cwd: Path | None = None, env: dict | None = None) -> None:
    """Run a subprocess, stream output, and abort on failure."""
    log.info("$ %s", " ".join(cmd))
    result = subprocess.run(cmd, cwd=cwd, env=env)
    if result.returncode != 0:
        log.error("Command failed with exit code %d", result.returncode)
        sys.exit(result.returncode)


def ensure_command(name: str) -> str:
    """Return the full path to an executable or abort."""
    path = shutil.which(name)
    if not path:
        log.error("'%s' not found on PATH. Please install it first.", name)
        sys.exit(1)
    return path


def clean_dir(path: Path) -> None:
    if path.exists():
        log.info("Cleaning %s", path)
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


# ── Step 1: Build Backend ────────────────────────────────────────────


def build_backend() -> None:
    log.info("=" * 60)
    log.info("STEP 1: Building backend with PyInstaller")
    log.info("=" * 60)

    venv_python = BACKEND_DIR / "venv" / "Scripts" / "python.exe"
    if not venv_python.exists():
        log.info("Creating backend virtual environment ...")
        run([sys.executable, "-m", "venv", str(BACKEND_DIR / "venv")])
        run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip"])

    log.info("Installing backend dependencies ...")
    run([
        str(venv_python), "-m", "pip", "install", "-r",
        str(BACKEND_DIR / "requirements.txt"),
    ])

    log.info("Installing PyInstaller ...")
    run([str(venv_python), "-m", "pip", "install", "pyinstaller>=6.0"])

    pyinstaller = BACKEND_DIR / "venv" / "Scripts" / "pyinstaller.exe"

    hidden_imports = [
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.http.httptools_impl",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.protocols.websockets.wsproto_impl",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "uvicorn.lifespan.off",
        "aiosqlite",
        "sqlalchemy.dialects.sqlite",
        "sqlalchemy.dialects.sqlite.aiosqlite",
        "pydantic",
        "pydantic_settings",
        "croniter",
        "backend",
        "backend.config",
        "backend.database",
        "backend.models",
        "backend.schemas",
        "backend.main",
        "backend.routers",
        "backend.routers.jobs",
        "backend.routers.system",
        "backend.routers.activity",
        "backend.services",
        "backend.services.backup_engine",
        "backend.services.activity_logger",
        "backend.services.scheduler",
        "backend.services.autostart",
        "backend.services.path_validator",
    ]

    cmd = [
        str(pyinstaller),
        str(PROJECT_ROOT / "run_production.py"),
        "--name", "dillo-backend",
        "--distpath", str(DIST_DIR / "backend"),
        "--workpath", str(PROJECT_ROOT / "build" / "backend"),
        "--specpath", str(PROJECT_ROOT / "build"),
        "--noconfirm",
        "--clean",
        "--console",
    ]
    for mod in hidden_imports:
        cmd.extend(["--hidden-import", mod])

    # Collect the backend package as data so relative imports work
    cmd.extend([
        "--collect-submodules", "backend",
        "--collect-submodules", "uvicorn",
        "--collect-submodules", "fastapi",
        "--collect-submodules", "starlette",
    ])

    run(cmd, cwd=PROJECT_ROOT)
    log.info("Backend build complete.")


# ── Step 2: Build Frontend ───────────────────────────────────────────


def build_frontend() -> None:
    log.info("=" * 60)
    log.info("STEP 2: Building Next.js frontend (standalone)")
    log.info("=" * 60)

    npm = ensure_command("npm")

    log.info("Installing frontend dependencies ...")
    run([npm, "ci"], cwd=FRONTEND_DIR)

    log.info("Building Next.js in standalone mode ...")
    run([npm, "run", "build"], cwd=FRONTEND_DIR)

    standalone_dir = FRONTEND_DIR / ".next" / "standalone"
    if not standalone_dir.exists():
        log.error("Standalone output not found at %s", standalone_dir)
        sys.exit(1)

    target = DIST_DIR / "frontend"
    clean_dir(target)

    # Copy standalone server (server.js + node_modules + .next/server)
    log.info("Copying standalone output ...")
    shutil.copytree(standalone_dir, target, dirs_exist_ok=True)

    # Copy static assets that standalone doesn't include automatically
    static_src = FRONTEND_DIR / ".next" / "static"
    static_dst = target / ".next" / "static"
    if static_src.exists():
        log.info("Copying static assets ...")
        shutil.copytree(static_src, static_dst, dirs_exist_ok=True)

    public_src = FRONTEND_DIR / "public"
    public_dst = target / "public"
    if public_src.exists():
        log.info("Copying public assets ...")
        shutil.copytree(public_src, public_dst, dirs_exist_ok=True)

    log.info("Frontend build complete.")


# ── Step 3: Download Node.js ─────────────────────────────────────────


def download_node(version: str) -> None:
    log.info("=" * 60)
    log.info("STEP 3: Downloading portable Node.js %s (%s)", version, NODE_ARCH)
    log.info("=" * 60)

    node_dir = DIST_DIR / "node"

    # Check if already downloaded
    if (node_dir / "node.exe").exists():
        log.info("Node.js already present, skipping download.")
        return

    filename = f"node-v{version}-win-{NODE_ARCH}"
    url = f"https://nodejs.org/dist/v{version}/{filename}.zip"

    log.info("Downloading %s ...", url)
    with urlopen(url) as resp:
        data = resp.read()

    log.info("Extracting node.exe ...")
    clean_dir(node_dir)

    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        # Only extract node.exe (we don't need npm/npx in production)
        node_entry = f"{filename}/node.exe"
        for member in zf.namelist():
            if member == node_entry:
                with zf.open(member) as src, open(node_dir / "node.exe", "wb") as dst:
                    shutil.copyfileobj(src, dst)
                break
        else:
            log.error("node.exe not found in archive.")
            sys.exit(1)

    log.info("Node.js download complete.")


# ── Step 4: Build Launcher ───────────────────────────────────────────


def build_launcher() -> None:
    log.info("=" * 60)
    log.info("STEP 4: Building launcher")
    log.info("=" * 60)

    venv_python = BACKEND_DIR / "venv" / "Scripts" / "python.exe"
    pyinstaller = BACKEND_DIR / "venv" / "Scripts" / "pyinstaller.exe"

    icon_flag = []
    icon_path = INSTALLER_DIR / "dillo.ico"
    if icon_path.exists():
        icon_flag = ["--icon", str(icon_path)]

    cmd = [
        str(pyinstaller),
        str(INSTALLER_DIR / "launcher.py"),
        "--name", "DilloBackup",
        "--onefile",
        "--windowed",
        "--distpath", str(DIST_DIR),
        "--workpath", str(PROJECT_ROOT / "build" / "launcher"),
        "--specpath", str(PROJECT_ROOT / "build"),
        "--noconfirm",
        "--clean",
        *icon_flag,
    ]
    for mod in ["pystray", "pystray._win32", "PIL", "PIL.Image"]:
        cmd.extend(["--hidden-import", mod])

    run(cmd, cwd=PROJECT_ROOT)
    log.info("Launcher build complete.")


# ── Step 5: Compile Inno Setup ───────────────────────────────────────


def compile_inno() -> None:
    log.info("=" * 60)
    log.info("STEP 5: Compiling Inno Setup installer")
    log.info("=" * 60)

    iss_file = INSTALLER_DIR / "dillo-backup.iss"
    if not iss_file.exists():
        log.error("Inno Setup script not found at %s", iss_file)
        sys.exit(1)

    iscc_paths = [
        Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
        Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
        Path(r"D:\Inno Setup 6\ISCC.exe"),
    ]
    iscc = None
    for p in iscc_paths:
        if p.exists():
            iscc = p
            break

    if iscc is None:
        iscc_which = shutil.which("ISCC")
        if iscc_which:
            iscc = Path(iscc_which)

    if iscc is None:
        log.warning("Inno Setup (ISCC.exe) not found. Skipping installer compilation.")
        log.warning("Install Inno Setup 6 from https://jrsoftware.org/isdownload.php")
        return

    run([str(iscc), str(iss_file)])
    log.info("Installer compiled successfully.")


# ── Main ─────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Dillo Backup for Windows")
    parser.add_argument("--skip-inno", action="store_true", help="Skip Inno Setup compilation")
    parser.add_argument("--node-version", default=NODE_VERSION_DEFAULT, help="Node.js version to bundle")
    args = parser.parse_args()

    log.info("Dillo Backup — Windows Build")
    log.info("Project root: %s", PROJECT_ROOT)
    log.info("Distribution: %s", DIST_DIR)

    # Clean dist
    clean_dir(DIST_DIR)

    build_backend()
    build_frontend()
    download_node(args.node_version)
    build_launcher()

    # Copy the .ico into the dist folder for the installed shortcut
    ico_src = INSTALLER_DIR / "dillo.ico"
    if ico_src.exists():
        shutil.copy2(ico_src, DIST_DIR / "dillo.ico")
        log.info("Copied dillo.ico to dist folder.")

    if not args.skip_inno:
        compile_inno()

    log.info("=" * 60)
    log.info("BUILD COMPLETE")
    log.info("Output: %s", DIST_DIR)
    log.info("=" * 60)


if __name__ == "__main__":
    main()
