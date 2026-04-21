#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────
#  Dillo Backup — macOS build script
#
#  Orchestrates the full build pipeline:
#    1. Build the Python backend into a standalone binary (PyInstaller)
#    2. Build the Next.js frontend in standalone mode
#    3. Download a portable Node.js runtime (macOS arm64/x64)
#    4. Bundle the launcher into a standalone binary (DilloBackup)
#    5. Assemble everything into "dist/Dillo Backup.app"
#
#  Prerequisites:
#    - Python 3.12+ on PATH (with pip)
#    - Node.js 18+ on PATH (with npm)
#
#  Usage:
#    chmod +x installer/build_macos.sh
#    ./installer/build_macos.sh [--node-version 22.14.0]
# ─────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
BACKEND_DIR="$PROJECT_ROOT/backend"
FRONTEND_DIR="$PROJECT_ROOT/frontend"
INSTALLER_DIR="$PROJECT_ROOT/installer"
DIST_DIR="$PROJECT_ROOT/dist/dillo-mac"

APP_BUNDLE_NAME="Dillo Backup"
APP_EXECUTABLE_NAME="DilloBackup"
APP_IDENTIFIER="com.dillo.backup"
DMG_VOLUME_NAME="Dillo Backup"
APP_BUNDLE="$PROJECT_ROOT/dist/${APP_BUNDLE_NAME}.app"

NODE_VERSION="${1:-22.14.0}"

# Detect architecture
ARCH="$(uname -m)"
if [ "$ARCH" = "arm64" ]; then
    NODE_ARCH="arm64"
else
    NODE_ARCH="x64"
fi

log() { echo "$(date '+%H:%M:%S')  $*"; }

clean_dir() {
    if [ -d "$1" ]; then
        log "Cleaning $1"
        rm -rf "$1"
    fi
    mkdir -p "$1"
}

# ── Step 1: Build Backend ────────────────────────────────────────────

build_backend() {
    log "============================================================"
    log "STEP 1: Building backend with PyInstaller"
    log "============================================================"

    VENV_PYTHON="$BACKEND_DIR/venv/bin/python"
    if [ ! -f "$VENV_PYTHON" ]; then
        log "Creating backend virtual environment ..."
        python3 -m venv "$BACKEND_DIR/venv"
        "$VENV_PYTHON" -m pip install --upgrade pip
    fi

    log "Installing backend dependencies ..."
    "$VENV_PYTHON" -m pip install -r "$BACKEND_DIR/requirements.txt"

    log "Installing PyInstaller ..."
    "$VENV_PYTHON" -m pip install "pyinstaller>=6.0"

    PYINSTALLER="$BACKEND_DIR/venv/bin/pyinstaller"

    "$PYINSTALLER" \
        "$PROJECT_ROOT/run_production.py" \
        --name dillo-backend \
        --distpath "$DIST_DIR/backend" \
        --workpath "$PROJECT_ROOT/build/backend" \
        --specpath "$PROJECT_ROOT/build" \
        --noconfirm --clean --console \
        --hidden-import uvicorn.logging \
        --hidden-import uvicorn.loops \
        --hidden-import uvicorn.loops.auto \
        --hidden-import uvicorn.protocols \
        --hidden-import uvicorn.protocols.http \
        --hidden-import uvicorn.protocols.http.auto \
        --hidden-import uvicorn.protocols.http.h11_impl \
        --hidden-import uvicorn.protocols.http.httptools_impl \
        --hidden-import uvicorn.protocols.websockets \
        --hidden-import uvicorn.protocols.websockets.auto \
        --hidden-import uvicorn.protocols.websockets.wsproto_impl \
        --hidden-import uvicorn.lifespan \
        --hidden-import uvicorn.lifespan.on \
        --hidden-import uvicorn.lifespan.off \
        --hidden-import aiosqlite \
        --hidden-import sqlalchemy.dialects.sqlite \
        --hidden-import sqlalchemy.dialects.sqlite.aiosqlite \
        --hidden-import pydantic \
        --hidden-import pydantic_settings \
        --hidden-import croniter \
        --hidden-import backend \
        --hidden-import backend.config \
        --hidden-import backend.database \
        --hidden-import backend.models \
        --hidden-import backend.schemas \
        --hidden-import backend.main \
        --hidden-import backend.routers \
        --hidden-import backend.routers.jobs \
        --hidden-import backend.routers.system \
        --hidden-import backend.routers.activity \
        --hidden-import backend.services \
        --hidden-import backend.services.backup_engine \
        --hidden-import backend.services.activity_logger \
        --hidden-import backend.services.scheduler \
        --hidden-import backend.services.autostart \
        --hidden-import backend.services.path_validator \
        --collect-submodules backend \
        --collect-submodules uvicorn \
        --collect-submodules fastapi \
        --collect-submodules starlette

    log "Backend build complete."
}

# ── Step 2: Build Frontend ───────────────────────────────────────────

build_frontend() {
    log "============================================================"
    log "STEP 2: Building Next.js frontend (standalone)"
    log "============================================================"

    log "Installing frontend dependencies ..."
    npm ci --prefix "$FRONTEND_DIR"

    log "Building Next.js in standalone mode ..."
    npm run build --prefix "$FRONTEND_DIR"

    STANDALONE_DIR="$FRONTEND_DIR/.next/standalone"
    if [ ! -d "$STANDALONE_DIR" ]; then
        log "ERROR: Standalone output not found at $STANDALONE_DIR"
        exit 1
    fi

    TARGET="$DIST_DIR/frontend"
    clean_dir "$TARGET"

    log "Copying standalone output ..."
    cp -R "$STANDALONE_DIR/"* "$TARGET/"

    STATIC_SRC="$FRONTEND_DIR/.next/static"
    STATIC_DST="$TARGET/.next/static"
    if [ -d "$STATIC_SRC" ]; then
        log "Copying static assets ..."
        mkdir -p "$STATIC_DST"
        cp -R "$STATIC_SRC/"* "$STATIC_DST/"
    fi

    PUBLIC_SRC="$FRONTEND_DIR/public"
    PUBLIC_DST="$TARGET/public"
    if [ -d "$PUBLIC_SRC" ]; then
        log "Copying public assets ..."
        mkdir -p "$PUBLIC_DST"
        cp -R "$PUBLIC_SRC/"* "$PUBLIC_DST/"
    fi

    log "Frontend build complete."
}

# ── Step 3: Download Node.js ─────────────────────────────────────────

download_node() {
    log "============================================================"
    log "STEP 3: Downloading portable Node.js $NODE_VERSION ($NODE_ARCH)"
    log "============================================================"

    NODE_DIR="$DIST_DIR/node"
    if [ -f "$NODE_DIR/bin/node" ]; then
        log "Node.js already present, skipping download."
        return
    fi

    FILENAME="node-v${NODE_VERSION}-darwin-${NODE_ARCH}"
    URL="https://nodejs.org/dist/v${NODE_VERSION}/${FILENAME}.tar.gz"

    log "Downloading $URL ..."
    clean_dir "$NODE_DIR"

    curl -fsSL "$URL" | tar xz -C "$NODE_DIR" --strip-components=1
    log "Node.js download complete."
}

# ── Step 4: Build Launcher ───────────────────────────────────────────

build_launcher() {
    log "============================================================"
    log "STEP 4: Building launcher"
    log "============================================================"

    PYINSTALLER="$BACKEND_DIR/venv/bin/pyinstaller"

    ICON_FLAG=""
    if [ -f "$INSTALLER_DIR/dillo.icns" ]; then
        ICON_FLAG="--icon $INSTALLER_DIR/dillo.icns"
    fi

    # shellcheck disable=SC2086
    "$PYINSTALLER" \
        "$INSTALLER_DIR/launcher.py" \
        --name "$APP_EXECUTABLE_NAME" \
        --onefile --console \
        --distpath "$DIST_DIR" \
        --workpath "$PROJECT_ROOT/build/launcher" \
        --specpath "$PROJECT_ROOT/build" \
        --noconfirm --clean \
        $ICON_FLAG

    log "Launcher build complete."
}

# ── Step 5: Assemble .app Bundle ─────────────────────────────────────

assemble_app_bundle() {
    log "============================================================"
    log "STEP 5: Assembling macOS .app bundle"
    log "============================================================"

    rm -rf "$APP_BUNDLE"
    CONTENTS="$APP_BUNDLE/Contents"
    MACOS_DIR="$CONTENTS/MacOS"
    RESOURCES="$CONTENTS/Resources"

    mkdir -p "$MACOS_DIR" "$RESOURCES"

    # Info.plist (heredoc uses variable expansion)
    cat > "$CONTENTS/Info.plist" << PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleName</key>
    <string>${APP_BUNDLE_NAME}</string>
    <key>CFBundleDisplayName</key>
    <string>${APP_BUNDLE_NAME}</string>
    <key>CFBundleIdentifier</key>
    <string>${APP_IDENTIFIER}</string>
    <key>CFBundleVersion</key>
    <string>1.0.0</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundleExecutable</key>
    <string>${APP_EXECUTABLE_NAME}</string>
    <key>CFBundleIconFile</key>
    <string>dillo</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>LSMinimumSystemVersion</key>
    <string>12.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
</dict>
</plist>
PLIST

    # Copy built artefacts into the app bundle
    cp "$DIST_DIR/$APP_EXECUTABLE_NAME" "$MACOS_DIR/$APP_EXECUTABLE_NAME"
    chmod +x "$MACOS_DIR/$APP_EXECUTABLE_NAME"

    # Backend / frontend / node live in Resources (see launcher.py + Gatekeeper).
    cp -R "$DIST_DIR/backend" "$RESOURCES/backend"
    cp -R "$DIST_DIR/frontend" "$RESOURCES/frontend"
    cp -R "$DIST_DIR/node" "$RESOURCES/node"

    # Icon (optional)
    if [ -f "$INSTALLER_DIR/dillo.icns" ]; then
        cp "$INSTALLER_DIR/dillo.icns" "$RESOURCES/dillo.icns"
    fi

    log ".app bundle created at: $APP_BUNDLE"
}

sign_app_bundle() {
    log "============================================================"
    log "STEP 5b: Ad-hoc code signing (Gatekeeper)"
    log "============================================================"
    codesign --force --deep --sign - "$APP_BUNDLE"
}

# ── Step 6: Create DMG ────────────────────────────────────────────────

create_dmg() {
    log "============================================================"
    log "STEP 6: Creating DMG"
    log "============================================================"

    DMG_OUTPUT="$PROJECT_ROOT/dist/installer/Dillo-Backup-1.0.0.dmg"
    STAGING="$PROJECT_ROOT/build/dmg-staging"

    mkdir -p "$(dirname "$DMG_OUTPUT")"
    rm -f "$DMG_OUTPUT"
    rm -rf "$STAGING"
    mkdir -p "$STAGING"

    cp -R "$APP_BUNDLE" "$STAGING/${APP_BUNDLE_NAME}.app"
    ln -s /Applications "$STAGING/Applications"

    hdiutil create \
        -volname "$DMG_VOLUME_NAME" \
        -srcfolder "$STAGING" \
        -ov \
        -format UDZO \
        "$DMG_OUTPUT"

    rm -rf "$STAGING"
    log "DMG created: $DMG_OUTPUT"
}

# ── Main ─────────────────────────────────────────────────────────────

SKIP_DMG=false
for arg in "$@"; do
    case "$arg" in
        --skip-dmg) SKIP_DMG=true ;;
        --node-version) shift; NODE_VERSION="$1" ;;
    esac
done

main() {
    log "Dillo Backup — macOS Build"
    log "Project root: $PROJECT_ROOT"
    log "Distribution: $DIST_DIR"

    clean_dir "$DIST_DIR"

    build_backend
    build_frontend
    download_node
    build_launcher
    assemble_app_bundle
    sign_app_bundle

    if [ "$SKIP_DMG" = false ]; then
        create_dmg
    fi

    log "============================================================"
    log "BUILD COMPLETE"
    log "App bundle: $APP_BUNDLE"
    if [ "$SKIP_DMG" = false ]; then
        log "DMG: $PROJECT_ROOT/dist/installer/Dillo-Backup-1.0.0.dmg"
    fi
    log "============================================================"
}

main
