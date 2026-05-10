"""Dillo Backup — macOS build script.

Orchestrates the full build pipeline:
  1. Build the Python backend into a standalone binary (PyInstaller)
  2. Build the Next.js frontend in standalone mode
  3. Download a portable Node.js runtime (macOS arm64/x64)
  4. Bundle the launcher into a standalone binary (DilloBackup)
  5. Assemble everything into "Dillo Backup.app"
  6. Create a distributable .dmg (volume name: "Dillo Backup")

Prerequisites:
  - Python 3.12+ on PATH (with pip)
  - Node.js 18+ on PATH (with npm)
  - macOS with hdiutil (ships with the OS)

Usage:
  python installer/build_macos.py [--node-version 22.14.0] [--skip-dmg]

Output:
  dist/Dillo Backup.app
  dist/installer/Dillo-Backup-1.0.0.dmg
"""

from __future__ import annotations

import argparse
import io
import logging
import os
import platform
import plistlib
import shutil
import subprocess
import sys
import tarfile
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
ASSETS_DIR = INSTALLER_DIR / "assets"
DIST_DIR = PROJECT_ROOT / "dist" / "dillo-mac"
APP_BUNDLE = PROJECT_ROOT / "dist" / "Dillo Backup.app"
APP_VERSION = "1.0.3"
DMG_OUTPUT = (
    PROJECT_ROOT / "dist" / "installer" / f"Dillo-Backup-Setup-{APP_VERSION}.dmg"
)

NODE_VERSION_DEFAULT = "22.14.0"
MACHINE = platform.machine()
NODE_ARCH = "arm64" if MACHINE == "arm64" else "x64"

APP_DISPLAY_NAME = "Dillo Backup"
APP_BUNDLE_NAME = "Dillo Backup"
APP_EXECUTABLE_NAME = "DilloBackup"
APP_IDENTIFIER = "com.dillo.backup"
DMG_VOLUME_NAME = "Dillo Backup"


def run(cmd: list[str], cwd: Path | None = None, env: dict | None = None) -> None:
    log.info("$ %s", " ".join(cmd))
    result = subprocess.run(cmd, cwd=cwd, env=env)
    if result.returncode != 0:
        log.error("Command failed with exit code %d", result.returncode)
        sys.exit(result.returncode)


def ensure_command(name: str) -> str:
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

    venv_python = BACKEND_DIR / "venv" / "bin" / "python"
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

    pyinstaller = BACKEND_DIR / "venv" / "bin" / "pyinstaller"

    hidden_imports = [
        "uvicorn.logging",
        "uvicorn.loops", "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http", "uvicorn.protocols.http.auto",
        "uvicorn.protocols.http.h11_impl",
        "uvicorn.protocols.http.httptools_impl",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.protocols.websockets.wsproto_impl",
        "uvicorn.lifespan", "uvicorn.lifespan.on", "uvicorn.lifespan.off",
        "aiosqlite",
        "sqlalchemy.dialects.sqlite", "sqlalchemy.dialects.sqlite.aiosqlite",
        "pydantic", "pydantic_settings", "croniter",
        "backend", "backend.config", "backend.database",
        "backend.models", "backend.schemas", "backend.main",
        "backend.routers", "backend.routers.jobs",
        "backend.routers.system", "backend.routers.activity",
        "backend.services", "backend.services.backup_engine",
        "backend.services.activity_logger", "backend.services.scheduler",
        "backend.services.autostart", "backend.services.path_validator",
    ]

    cmd = [
        str(pyinstaller),
        str(PROJECT_ROOT / "run_production.py"),
        "--name", "dillo-backend",
        "--distpath", str(DIST_DIR / "backend"),
        "--workpath", str(PROJECT_ROOT / "build" / "backend"),
        "--specpath", str(PROJECT_ROOT / "build"),
        "--noconfirm", "--clean", "--console",
    ]
    for mod in hidden_imports:
        cmd.extend(["--hidden-import", mod])
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

    log.info("Copying standalone output ...")
    shutil.copytree(standalone_dir, target, dirs_exist_ok=True)

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
    if (node_dir / "bin" / "node").exists():
        log.info("Node.js already present, skipping download.")
        return

    filename = f"node-v{version}-darwin-{NODE_ARCH}"
    url = f"https://nodejs.org/dist/v{version}/{filename}.tar.gz"

    log.info("Downloading %s ...", url)
    with urlopen(url) as resp:
        data = resp.read()

    log.info("Extracting ...")
    clean_dir(node_dir)

    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tf:
        for member in tf.getmembers():
            # Strip the top-level directory name
            parts = member.name.split("/", 1)
            if len(parts) < 2:
                continue
            member.name = parts[1]
            tf.extract(member, path=node_dir)

    log.info("Node.js download complete.")


# ── Step 4: Build Launcher ───────────────────────────────────────────


def build_launcher() -> None:
    log.info("=" * 60)
    log.info("STEP 4: Building launcher")
    log.info("=" * 60)

    pyinstaller = BACKEND_DIR / "venv" / "bin" / "pyinstaller"

    icon_flag: list[str] = []
    icns_path = ASSETS_DIR / "dillo.icns"
    if icns_path.exists():
        icon_flag = ["--icon", str(icns_path)]

    cmd = [
        str(pyinstaller),
        str(INSTALLER_DIR / "launcher.py"),
        "--name", APP_EXECUTABLE_NAME,
        "--onefile", "--windowed",
        "--distpath", str(DIST_DIR),
        "--workpath", str(PROJECT_ROOT / "build" / "launcher"),
        "--specpath", str(PROJECT_ROOT / "build"),
        "--noconfirm", "--clean",
        *icon_flag,
    ]
    for mod in ["pystray", "pystray._darwin", "PIL", "PIL.Image"]:
        cmd.extend(["--hidden-import", mod])

    run(cmd, cwd=PROJECT_ROOT)
    log.info("Launcher build complete.")


# ── Step 5: Assemble .app Bundle ─────────────────────────────────────


def assemble_app_bundle() -> None:
    log.info("=" * 60)
    log.info("STEP 5: Assembling macOS .app bundle")
    log.info("=" * 60)

    if APP_BUNDLE.exists():
        shutil.rmtree(APP_BUNDLE)

    contents = APP_BUNDLE / "Contents"
    macos_dir = contents / "MacOS"
    resources = contents / "Resources"
    macos_dir.mkdir(parents=True)
    resources.mkdir(parents=True)

    # Info.plist
    plist = {
        "CFBundleName": APP_BUNDLE_NAME,
        "CFBundleDisplayName": APP_DISPLAY_NAME,
        "CFBundleIdentifier": APP_IDENTIFIER,
        "CFBundleVersion": APP_VERSION,
        "CFBundleShortVersionString": APP_VERSION,
        "CFBundleExecutable": APP_EXECUTABLE_NAME,
        "CFBundleIconFile": "dillo",
        "CFBundlePackageType": "APPL",
        "LSMinimumSystemVersion": "12.0",
        "NSHighResolutionCapable": True,
    }
    with open(contents / "Info.plist", "wb") as f:
        plistlib.dump(plist, f)

    # Copy built artefacts
    launcher_bin = DIST_DIR / APP_EXECUTABLE_NAME
    if not launcher_bin.exists():
        log.error("Launcher binary not found at %s", launcher_bin)
        sys.exit(1)

    shutil.copy2(launcher_bin, macos_dir / APP_EXECUTABLE_NAME)
    os.chmod(macos_dir / APP_EXECUTABLE_NAME, 0o755)

    # Ship backend / frontend / node under Resources (not MacOS) so codesign
    # does not treat node_modules and other data as signed code.
    shutil.copytree(DIST_DIR / "backend", resources / "backend")
    shutil.copytree(DIST_DIR / "frontend", resources / "frontend")
    shutil.copytree(DIST_DIR / "node", resources / "node")

    icns_path = ASSETS_DIR / "dillo.icns"
    if icns_path.exists():
        shutil.copy2(icns_path, resources / "dillo.icns")

    log.info(".app bundle created at: %s", APP_BUNDLE)


def sign_app_bundle(app_bundle: Path) -> None:
    """Re-seal the bundle with an ad hoc signature.

    Without this step, Gatekeeper often shows a misleading dialog: the app
    appears "damaged" and the only button is to trash it. Re-signing after
    the final folder layout fixes validation for local / unsigned builds.
    """
    log.info("=" * 60)
    log.info("STEP 5b: Ad-hoc code signing (Gatekeeper)")
    log.info("=" * 60)
    run([
        "codesign",
        "--force",
        "--deep",
        "--sign",
        "-",
        str(app_bundle),
    ])


# ── Step 6: Create DMG ───────────────────────────────────────────────


def create_dmg() -> None:
    log.info("=" * 60)
    log.info("STEP 6: Creating DMG")
    log.info("=" * 60)

    if not APP_BUNDLE.exists():
        log.error("App bundle not found at %s. Cannot create DMG.", APP_BUNDLE)
        sys.exit(1)

    DMG_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    if DMG_OUTPUT.exists():
        DMG_OUTPUT.unlink()

    staging = PROJECT_ROOT / "build" / "dmg-staging"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)

    # Copy .app into staging area
    shutil.copytree(APP_BUNDLE, staging / f"{APP_BUNDLE_NAME}.app", symlinks=True)

    # Create a symlink to /Applications for drag-to-install
    os.symlink("/Applications", staging / "Applications")

    # Use hdiutil to create the DMG
    run([
        "hdiutil", "create",
        "-volname", DMG_VOLUME_NAME,
        "-srcfolder", str(staging),
        "-ov",
        "-format", "UDZO",
        str(DMG_OUTPUT),
    ])

    # Clean up staging
    shutil.rmtree(staging)

    log.info("DMG created: %s", DMG_OUTPUT)


# ── Main ─────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Dillo Backup for macOS")
    parser.add_argument("--node-version", default=NODE_VERSION_DEFAULT, help="Node.js version to bundle")
    parser.add_argument("--skip-dmg", action="store_true", help="Skip DMG creation")
    args = parser.parse_args()

    log.info("Dillo Backup — macOS Build")
    log.info("Project root: %s", PROJECT_ROOT)
    log.info("Distribution: %s", DIST_DIR)

    clean_dir(DIST_DIR)

    build_backend()
    build_frontend()
    download_node(args.node_version)
    build_launcher()
    assemble_app_bundle()
    sign_app_bundle(APP_BUNDLE)

    if not args.skip_dmg:
        create_dmg()

    log.info("=" * 60)
    log.info("BUILD COMPLETE")
    log.info("App bundle: %s", APP_BUNDLE)
    if not args.skip_dmg:
        log.info("DMG: %s", DMG_OUTPUT)
    log.info("=" * 60)


if __name__ == "__main__":
    main()
