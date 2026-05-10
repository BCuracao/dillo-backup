# Project Journal: PyBackup Sentinel

---

## 1. Project Overview

- **Goal:** A robust local backup management web application that lets users schedule, customize, and monitor local data backups via a modern dark-mode browser interface.
- **Stack:** Python 3.12+ (FastAPI, SQLAlchemy 2.0, aiosqlite), Next.js 16 (App Router, TypeScript, Tailwind CSS, next-intl), SQLite.
- **Status:** MVP complete — full-stack scaffold through verified end-to-end integration. All core CRUD, incremental backup engine, and dashboard UI are functional.
- **Repository:** [github.com/BCuracao/dillo](https://github.com/BCuracao/dillo)

### Architecture

```
┌──────────────────────┐        REST / JSON         ┌──────────────────────┐
│   Next.js 15 (3000)  │  ◄────────────────────►    │   FastAPI (8000)     │
│   App Router + TW    │      axios / polling        │   async + BGTasks    │
└──────────────────────┘                             └──────────┬───────────┘
                                                                │
                                                     ┌──────────▼───────────┐
                                                     │  SQLite (aiosqlite)  │
                                                     │  backups.db          │
                                                     └──────────────────────┘
```

### Key Design Decisions

| Decision                                          | Rationale                                                                                                                                                                       |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **SQLite over Postgres**                          | Local-only desktop tool. Zero-config, file-based, adequate for tens of jobs. `aiosqlite` provides async compatibility without an external server.                               |
| **UUID primary keys on BackupJob**                | Avoids sequential ID enumeration. Generated client-side (`uuid.uuid4`) so no DB round-trip is needed before the object is usable.                                               |
| **`lazy="selectin"` on logs relationship**        | Jobs almost always need their latest log for display. `selectin` batches one extra SELECT, avoiding N+1 without joined-load complexity.                                         |
| **BackgroundTasks over Celery**                   | No external broker needed for a local tool. FastAPI's `BackgroundTasks` runs in-process after the response. Combined with `ThreadPoolExecutor`, handles concurrent backups.     |
| **`shutil.copy2` over raw I/O**                   | Preserves metadata (mtime, permissions) — critical for backup fidelity and for incremental comparison on subsequent runs.                                                       |
| **Pydantic `model_validator` for source != dest** | Defense-in-depth against recursive copy loops. Enforced on both backend schema and mirrored as client-side validation.                                                          |
| **Polling (5s) over WebSockets**                  | Simpler to implement and debug. Latency tolerance is high for a local tool. WebSockets can be added later if real-time progress becomes a requirement.                          |
| **next-intl (non-routing) over URL-based i18n**   | Cookie-based locale avoids route prefixes (`/en/`, `/de/`). Simpler for a local desktop tool where SEO is irrelevant. Locale persists across sessions via `NEXT_LOCALE` cookie. |
| **Engine owns its own DB session**                | `BackgroundTask` runs after the request lifecycle, so the request-scoped `get_db` session is already closed. The engine creates its own `async_session_factory()` context.      |
| **`croniter` over APScheduler**                   | Lightweight cron parsing library (~50 KB). A simple asyncio loop + `croniter.get_next()` avoids the complexity and overhead of a full scheduler framework for a local tool.     |
| **`as_completed` over `gather` for progress**     | `asyncio.as_completed` streams results as each file copy finishes, enabling periodic DB flushes. `gather` waits for all, blocking progress updates until the entire run ends.   |

### Backup Engine Design (`BackupManager`)

1. **Incremental strategy** — Compares `mtime` + `st_size`. Copies only when source is newer or different size. Avoids full-content hashing per run.
2. **`os.scandir` for scanning** — Returns `DirEntry` objects with cached stat results from the OS directory read. On NTFS, avoids redundant system calls vs. `os.walk` or `pathlib.rglob`.
3. **Concurrency** — Blocking file I/O offloaded to a shared `ThreadPoolExecutor` (4 workers default). `asyncio.Semaphore` gates concurrency. Scan phase also runs in executor. FastAPI event loop stays free.
4. **Fault isolation** — Each file copy wrapped in its own `try/except` for `PermissionError`/`OSError`. One inaccessible file does not abort the job. Errors collected into `BackupReport`, persisted to `JobLog.error_message` (capped at 50).
5. **Dry-run mode** — Full scan + comparison logic runs, but `shutil.copy2`/`mkdir` are skipped. Logs what _would_ be copied at INFO level. Metrics reflect the would-be work.
6. **Safety Lock** — Resolves destination drive letter via `os.path.splitdrive`, compares against `settings.protected_drives` (default `["C:\\"]`). Blocks writes unless `force_system_drive=true`.
7. **SHA-256 verification** — `file_checksum()` and `verify_copy()` implemented, reading in 8 KB chunks. Wired into the copy flow via `verify_after_copy` flag on `RunJobRequest`; each file verified immediately after copy.
8. **Size estimation** — `estimate_backup()` classmethod runs scan + stat comparison read-only, returning file count, byte total, and a rough time estimate (~50 MB/s). Exposed via `GET /api/jobs/{id}/estimate`.
9. **Real-time progress** — `_flush_progress()` writes intermediate `files_processed`, `files_skipped`, `total_size_mb` to the `JobLog` row every 25 files or 3 seconds. Uses `asyncio.as_completed` instead of `gather` to stream results.
10. **Cron scheduler** — `services/scheduler.py` runs an asyncio loop every 60 seconds, matching `schedule_cron` expressions via `croniter`. Prevents overlapping runs by checking for existing RUNNING log entries.

### File Manifest

```
pybackup-sentinel/
├── backend/
│   ├── __init__.py
│   ├── config.py                # pydantic-settings, Safety Lock config
│   ├── database.py              # Async SQLAlchemy engine + session
│   ├── main.py                  # FastAPI app, CORS, lifespan
│   ├── models.py                # BackupJob + JobLog ORM models
│   ├── schemas.py               # Pydantic v2 request/response schemas
│   ├── requirements.txt         # Python dependencies
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── activity.py          # Activity log retrieval + cleanup
│   │   ├── jobs.py              # Job CRUD + run trigger + logs
│   │   └── system.py            # Drive listing + health check
│   ├── services/
│   │   ├── __init__.py
│   │   ├── activity_logger.py   # Activity logging (DB + file + rotation)
│   │   ├── autostart.py         # Cross-platform auto-start (winreg / plist / XDG)
│   │   ├── backup_engine.py     # Incremental backup logic
│   │   ├── path_validator.py    # Multi-strategy dir access (cloud/virtual drives)
│   │   └── scheduler.py         # Cron-based backup scheduler (asyncio + croniter)
│   └── logs/                    # Auto-created, rotating .log files (max 3)
├── frontend/
│   ├── app/
│   │   ├── globals.css          # Dark-mode design tokens
│   │   ├── layout.tsx           # Root layout
│   │   ├── logs/
│   │   │   └── page.tsx         # Activity logs page (100 entries)
│   │   ├── settings/
│   │   │   └── page.tsx         # Settings page (auto-start, language, about)
│   │   └── page.tsx             # Dashboard page
│   ├── components/
│   │   ├── ActivityFeed.tsx     # Activity log feed (polling, paginated)
│   │   ├── CreateJobModal.tsx   # Job creation form
│   │   ├── EditJobModal.tsx    # Job editing form (pre-filled)
│   │   ├── DashboardLayout.tsx  # Sidebar + content wrapper
│   │   ├── DriveCard.tsx        # Drive usage display
│   │   ├── FolderPicker.tsx     # Visual folder browser/selector
│   │   ├── JobCard.tsx          # Backup job card with actions
│   │   ├── LanguageSwitcher.tsx # Locale toggle (en/de)
│   │   ├── SchedulePicker.tsx   # Friendly schedule builder
│   │   ├── Sidebar.tsx          # Navigation sidebar
│   │   ├── StatusBadge.tsx      # Status pill component
│   │   └── ToastProvider.tsx    # Toast notification context + renderer
│   ├── hooks/
│   │   └── useBackupJobs.ts     # Polling hook (5s interval)
│   ├── i18n/
│   │   └── request.ts           # next-intl request config
│   ├── messages/
│   │   ├── en.json              # English translations
│   │   └── de.json              # German translations
│   └── lib/
│       ├── api.ts               # Axios API client
│       └── types.ts             # TypeScript interfaces
├── installer/
│   ├── build_windows.py         # Windows build orchestration script
│   ├── build_macos.sh           # macOS build + .app bundle script
│   ├── launcher.py              # App launcher source (→ Dillo.exe / Dillo)
│   └── dillo.iss                # Inno Setup installer script
├── run_production.py            # Backend PyInstaller entry point
├── start-dev.bat                # Windows dev launcher
├── start-dev.sh                 # Unix dev launcher
├── README.md                    # User-facing documentation
└── PROJECT_JOURNAL.md           # This file (long-term memory)
```

---

## 2. Active Context

- **Current Focus:** Released v1.0.3 Windows installer (`dist/installer/Dillo-Backup-Setup-1.0.3.exe`, ~55 MB). Version bumped from `1.0.0` to `1.0.3` across installer script, FastAPI app, settings page, locale messages, and README.
- **Last Session:** 2026-05-10 — v1.0.3 Windows installer release build.
- **Running State:** Both servers can be launched via `start-dev.bat` (Windows dev), `start-dev.sh` (Unix dev), or `Dillo.exe` / `Dillo.app` (production). Backend on `:8000`, frontend on `:3000`.

---

## 3. Recent Changes

### Session: 2026-05-10 — v1.0.3 Windows Installer Release

**Goal:** Cut a new Windows installer for the **v1.0.3** release with the version embedded in the installer filename.

**Version bumps (1.0.0 → 1.0.3):**
- `installer/dillo-backup.iss` — `MyAppVersion` define (drives `OutputBaseFilename=Dillo-Backup-Setup-{#MyAppVersion}` so the version automatically appears in the filename)
- `installer/build_windows.py` — docstring example output path
- `backend/main.py` — FastAPI `app(version="1.0.3", ...)`
- `frontend/app/settings/page.tsx` — About section version label
- `frontend/messages/en.json` + `de.json` — sidebar `dashboard.version` strings
- `README.md` — install instructions reference

**Build pipeline run:** `python installer/build_windows.py` end-to-end — PyInstaller backend + Next.js standalone frontend + portable Node.js 22.14.0 + windowed `DilloBackup.exe` launcher + Inno Setup 6 compile.

**Output:** `dist/installer/Dillo-Backup-Setup-1.0.3.exe` (~55 MB; full pipeline ~2.5 min wall time on this machine; Inno reported ~43.8 s compile step).

**Notes:**
- New backend service modules added since the last release (`backup_queue`, `drive_watcher`, `settings_service`, `system_events`, `ui_presence`) are picked up automatically by PyInstaller's `--collect-submodules backend` flag — no hidden-import edits needed.
- PowerShell flagged Python's stderr logger output as a `NativeCommandError` early in the run; this is cosmetic and the actual subprocess exit code was `0`.

---

### Session: 2026-04-08 — Windows Installer Rebuild

- Ran `python installer/convert_icons.py` (missing `installer/dillo.ico` in tree; generates from `frontend/public/dillo-logo-color.png`).
- Ran `python installer/build_windows.py` end-to-end: PyInstaller backend + Next.js standalone + portable Node 22.14.0 + windowed `Dillo.exe` + Inno Setup 6.
- **Output:** `dist/installer/DilloSetup-1.0.0.exe` (full pipeline ~2.3 min wall time on this machine; Inno reported ~43 s compile step).

---

### Session: 2026-04-08 — Windows Autostart Registered Backend Only (Fix)

**Symptom:** After enabling auto-start in Settings, reboot showed only Uvicorn on `:8000`; `localhost:3000` unreachable. Registry `Run` value pointed at `...\backend\dillo-backend\dillo-backend.exe`.

**Root cause:** `_get_exe_path()` used `sys.executable`, which in production is always the **backend** binary (the process serving the API). The **launcher** (`Dillo.exe` / `Dillo`) must be registered so both backend and Next.js start.

**Fix:** `backend/services/autostart.py` — resolve install root from `.../backend/dillo-backend/<exe>`, then register `Dillo.exe` (Windows) or `Dillo` (macOS/Linux bundle layout). **Requires rebuild/reinstall** for existing users; manual registry fix: set quoted path to `D:\Dillo\Dillo.exe` (or toggle autostart off/on after update).

---

### Session: 2026-04-08 — macOS Safety Lock Fix & Silent Failure Prevention

**Goal:** Diagnose and fix backup jobs silently failing on macOS — no error shown, no log entry created, job appears to do nothing when run.

**Root Cause:** Two compounding bugs:

1. **Safety Lock blocked every path on macOS/Linux.** `config.py` included `"/"` in `protected_drives` for macOS. The comparison `resolved.startswith(protected.rstrip("/") + "/")` reduced to `resolved.startswith("/")` which is always true for any Unix path. Every backup destination was rejected with a `PermissionError`.
2. **Pre-flight errors were silently swallowed.** Path validation and Safety Lock checks in `run_backup()` ran *before* the `JobLog` row was created and *outside* the `try/except` block. Exceptions propagated into FastAPI's `BackgroundTasks` runner, which discarded them — no `JobLog`, no activity entry, no UI feedback.

**Fix 1: Safety Lock protected paths (`backend/config.py`)**

- macOS `protected_drives` changed from `["/System", "/"]` to `["/System", "/usr", "/bin", "/sbin"]` — protects actual system directories without blocking user paths like `/Users/...` or `/Volumes/...`
- Linux `protected_drives` changed from `["/"]` to `["/usr", "/bin", "/sbin"]` — same rationale

**Fix 2: Safety Lock comparison hardening (`backend/services/backup_engine.py`)**

- Added special-case handling for bare `"/"` in the Unix branch: if `protected.rstrip("/")` yields an empty string, only an exact match against `"/"` triggers the lock — prevents `startswith("")` from matching everything

**Fix 3: Pre-flight error visibility (`backend/services/backup_engine.py`)**

- Wrapped path validation + Safety Lock checks in `try/except` inside `run_backup()`
- On failure: creates an `ERROR` `JobLog` row (with `error_message`), writes a `JOB_FAILED` activity log entry, and returns a `BackupReport` with the error — ensures the UI always shows feedback

**Fix 4: macOS drives & browse endpoints (`backend/routers/system.py`)**

- `GET /api/system/drives` — macOS: dynamically discovers volumes under `/Volumes` (was only listing Linux-style `/home`, `/mnt`, `/media` which don't exist on Mac); reports `apfs` as filesystem type; label uses directory name instead of full path
- `GET /api/system/browse` (root listing) — macOS: shows `/`, `/Users`, `/Volumes` instead of Linux mount points

**Fix 5: Dev launcher rebrand (`start-dev.bat`, `start-dev.sh`)**

- Updated all "PyBackup Sentinel" references to "Dillo" in both development launcher scripts (header comments, banner text, window titles)

---

### Session: 2026-04-08 — Settings Page, Console Window Fix, Color App Icon

**Goal:** Create a Settings page with auto-start toggle, fix the console window appearing on production launch, and wire the new color logo for desktop icon generation.

**Task 1: Settings Page (`frontend/app/settings/page.tsx`)**

- New: `app/settings/page.tsx` — Full settings page accessible via the `/settings` sidebar link:
  - **General section:** Language selector (same locale-switching logic as `LanguageSwitcher`, now in a proper settings layout with description text)
  - **Startup section:** Auto-start toggle switch — fetches status from `GET /api/system/autostart`, toggles via `PUT /api/system/autostart`; smooth animated toggle; shows fallback text when not running from installed build; error handling with inline message
  - **About section:** Version number (1.0.0) and detected platform (from autostart status response)
- `messages/en.json` + `de.json` — Added `settingsPage` namespace (12 keys each: title, subtitle, general, language, languageDescription, startup, autoStartToggling, autoStartError, autoStartNotAvailable, about, version, platform)

**Task 2: Console Window Fix**

- `installer/build_windows.py` — Launcher PyInstaller flag changed from `--console` to `--windowed`; `Dillo.exe` will no longer spawn a visible command prompt on launch
- `installer/build_macos.py` — Same fix applied for the macOS launcher build
- Note: Child processes (backend + frontend) already used `CREATE_NO_WINDOW` / no-console flags; only the launcher itself was showing the window

**Task 3: Color Logo for Desktop Icons**

- `installer/convert_icons.py` — Source path changed from `dillo-logo.png` to `dillo-logo-color.png`; next `python installer/convert_icons.py` run will generate `.ico` / `.icns` from the color armadillo logo
- `dillo-logo-color.png` added to `frontend/public/` (color armadillo illustration)
- Sidebar logo intentionally unchanged — keeps `dillo-logo.png` with `invert brightness-200` filter for the dark UI

---

### Session: 2026-04-08 — Git Repository Initialization & GitHub Setup

**Goal:** Initialize version control, create a comprehensive `.gitignore`, update README with Dillo branding, and push the full project to a public GitHub repository.

**Step 1: `.gitignore` Creation**

- Created root `.gitignore` covering all required exclusions:
  - SQLite databases (`*.db`, `*.db-journal`, `*.db-wal`, `*.db-shm`)
  - Python artifacts (`__pycache__/`, `*.py[cod]`, `venv/`, `.pytest_cache/`)
  - Backend logs (`backend/logs/`)
  - Environment files (`.env`, `.env.*`)
  - Frontend build artifacts (`frontend/.next/`, `frontend/node_modules/`)
  - Build/distribution outputs (`build/`, `dist/`, `*.spec`)
  - Installer generated assets (`installer/assets/*.ico`, `installer/assets/*.icns`, `installer/dillo.ico`)
  - OS-specific files (`.DS_Store`, `Thumbs.db`)
  - IDE files (`.vscode/`, `.idea/`) — `.cursor/rules/` explicitly preserved via negation pattern

**Step 2: README Update**

- Rewrote `README.md` with full Dillo branding:
  - Badge row (Python, Next.js, SQLite, MIT license)
  - Complete feature list (12 features: incremental, dry run, SHA-256, cron, safety lock, dashboard, logging, toasts, pause/resume, estimation, auto-start, i18n)
  - Production build instructions (Windows Inno Setup + macOS DMG)
  - Full API endpoint table (16 endpoints)
  - Updated project structure reflecting current file manifest

**Step 3: Git Initialization**

- Removed nested `frontend/.git` directory (leftover from `create-next-app`)
- Initialized repository, staged 69 files (16,060 lines), created initial commit
- Renamed default branch from `master` to `main`

**Step 4: GitHub Remote**

- Installed GitHub CLI (`gh`) via winget
- Created public repository: [github.com/BCuracao/dillo](https://github.com/BCuracao/dillo)
- Pushed `main` branch to origin

---

### Session: 2026-04-07 — Asset Conversion & Full Production Build Pipeline

**Goal:** Generate platform-specific icons from `dillo-logo.png`, refine the Windows installer, create a complete macOS build script with DMG packaging, and verify cross-platform persistence paths and autostart logic.

**Step 1: Asset Generation (`installer/convert_icons.py`)**

- Created `installer/convert_icons.py` — Pillow-based script that converts `frontend/public/dillo-logo.png` into:
  - `installer/assets/dillo.ico` — multi-size Windows icon (16, 32, 48, 64, 128, 256 px)
  - `installer/assets/dillo.icns` — macOS icon (16, 32, 64, 128, 256, 512 px) using PNG-in-ICNS format
  - Copies `.ico` to `installer/dillo.ico` for Inno Setup / PyInstaller references
- Script tested and verified: ICO 72 KB, ICNS 264 KB

**Step 2: Windows Build Refinements**

- `installer/dillo.iss` — Desktop and Start Menu shortcuts now use `{app}\dillo.ico` (dedicated icon file shipped with installer); `dillo.ico` added as an installable file; `DisableDirPage=no` confirmed
- `installer/build_windows.py` — Copies `dillo.ico` into `dist/dillo/` before Inno Setup compilation so the installed icon file is always present
- All "Stashit" references confirmed removed

**Step 3: macOS Build with DMG (`installer/build_macos.py`)**

- Created `installer/build_macos.py` — full Python build script mirroring `build_windows.py`:
  1. PyInstaller backend build
  2. Next.js standalone frontend build
  3. Portable Node.js download (arm64/x64 auto-detect)
  4. PyInstaller launcher with `dillo.icns` icon
  5. `.app` bundle assembly (`Contents/Info.plist`, `Resources/dillo.icns`, `MacOS/` with all artefacts)
  6. DMG creation via `hdiutil create` with `/Applications` symlink for drag-to-install
- Updated `installer/build_macos.sh` — added `create_dmg()` step and `--skip-dmg` flag

**Step 4: Cross-Platform Persistence & Auto-Start (verified, no changes needed)**

- `backend/config.py` — macOS data dir already targets `~/Library/Application Support/Dillo`
- `backend/services/autostart.py` — Windows Registry, macOS LaunchAgent, Linux XDG desktop entry all implemented and wired to `GET/PUT /api/autostart` in the system router

---

### Session: 2026-04-07 — Cross-Platform, Auto-Start, Installer & Path Validation

**Goal:** Implement four high-priority tasks: macOS support, auto-start on boot, Inno Setup 6 refinements, and robust path validation (canary test in backup engine + FolderPicker resilience).

**Task 1: macOS Support (`config.py`)**

- `config.py` — `_resolve_data_dir()` now detects `sys.platform`:
  - **macOS:** `~/Library/Application Support/Dillo`
  - **Windows:** `%LOCALAPPDATA%\Dillo`
  - **Linux:** `$XDG_DATA_HOME/dillo` or `~/.local/share/dillo`
- `protected_drives` default is platform-aware: `["C:\\"]` on Windows, `["/System", "/"]` on macOS, `["/"]` on Linux

**Task 2: Auto-Start on Boot**

- New: `services/autostart.py` — Cross-platform auto-start management:
  - **Windows:** Adds/removes `HKCU\Software\Microsoft\Windows\CurrentVersion\Run` registry key via `winreg`
  - **macOS:** Creates/removes `~/Library/LaunchAgents/com.dillo.backup.plist` (LaunchAgent with `RunAtLoad`)
  - **Linux:** Creates/removes `~/.config/autostart/dillo.desktop` (XDG autostart)
  - Public API: `is_autostart_enabled()` and `set_autostart(enabled)` — both detect the platform automatically
- `schemas.py` — Added `AutoStartStatusResponse` (enabled, platform) and `AutoStartRequest` (enabled)
- `routers/system.py` — New endpoints:
  - `GET /api/system/autostart` — returns current auto-start state
  - `PUT /api/system/autostart` — enable/disable with error handling
- Frontend:
  - `lib/types.ts` — Added `AutoStartStatus` interface
  - `lib/api.ts` — Added `fetchAutoStartStatus()` and `setAutoStart(enabled)` API functions
  - `messages/en.json` + `de.json` — Added `autoStart` namespace (label, description, enabled, disabled)

**Task 3: Inno Setup 6 Refinement**

- `installer/dillo.iss`:
  - Added `DisableDirPage=no` — users can now choose installation directory
  - Uncommented `SetupIconFile=dillo.ico` and `UninstallDisplayIcon` — installer uses the Dillo icon
  - Desktop shortcut task now checked by default (removed `Flags: unchecked`)
  - Desktop icon entry references `IconFilename` for the Dillo icon

**Task 4: macOS Build Script + Cross-Platform Launcher**

- New: `installer/build_macos.sh` — Full macOS build pipeline:
  1. Build backend (PyInstaller)
  2. Build frontend (Next.js standalone)
  3. Download portable Node.js (arm64/x64 auto-detected)
  4. Build launcher (PyInstaller onefile)
  5. Assemble `Dillo.app` bundle with `Info.plist` (CFBundleIdentifier: `com.dillo.backup`)
- `installer/launcher.py` — Cross-platform path resolution:
  - Backend/Node.js binary paths differ between Windows (.exe) and Unix
  - Data directory resolves per platform (macOS: Library/Application Support, Linux: XDG)
- `installer/build_windows.py` — Added `backend.services.autostart` and `backend.services.path_validator` to hidden imports

**Task 5: Canary Test in Backup Engine**

- `services/backup_engine.py`:
  - `run_backup()` now calls `verify_directory_access()` on both source and destination before starting
  - Raises `FileNotFoundError` with the specific error key if either path fails all probe strategies
  - `_check_safety_lock()` updated for cross-platform support: uses `os.path.splitdrive` on Windows, prefix matching on Unix

**Task 6: FolderPicker Virtual Drive Resilience**

- `components/FolderPicker.tsx`:
  - When a browse returns zero directories for a non-root path, automatically runs a `validatePath()` canary check
  - If canary succeeds, shows "Path is accessible" with green shield icon — user can select the path
  - If canary fails, shows "Verify access" button for manual retry, with error feedback
  - Added `ShieldCheck` and `AlertTriangle` icon imports
- `messages/en.json` + `de.json` — Added to `folderPicker`: `verifyAccess`, `validatedAccessible`, `emptyButAccessible`, `notAccessible`

---

### Session: 2026-02-21 — Robust Path Validation (Network/Cloud Drive Support)

**Goal:** Allow users to use cloud/virtual drives (e.g. Filen.io on X:) that fail standard `os.path.isdir()` checks by implementing a multi-strategy "canary" validator and manual path entry in the UI.

**Backend — New File:**

- `services/path_validator.py` — Multi-strategy directory access verification:
  - `verify_directory_access(path)` tries, in order: (1) `Path.is_dir()`, (2) `os.scandir()` probe, (3) `os.stat()` + `S_ISDIR`, (4) canary file create/delete, (5) Windows drive-root / UNC share probe
  - Returns `PathValidationResult` (accessible, writable, method, error) with machine-readable error keys for user feedback

**Backend — Modified:**

- `schemas.py` — Added `PathValidationRequest` (path, check_writable) and `PathValidationResponse` (path, accessible, writable, method, error)
- `routers/system.py` — `_probe_drive()` for drives that don’t respond to `Path.exists()`; `GET /drives` and `GET /browse` use multi-strategy probing so virtual drives appear; `GET /browse` uses stat/scandir fallbacks and `os.scandir()` for listing; new `POST /api/system/validate-path` endpoint
- `routers/jobs.py` — `create_job` and `update_job` use `verify_directory_access()` for source and destination paths; specific error messages (e.g. "drive found but access denied", "drive exists but path is not accessible") returned in 400 detail

**Frontend — Modified:**

- `lib/types.ts` — Added `PathValidationResponse` interface
- `lib/api.ts` — Added `validatePath(path, checkWritable)` calling `POST /api/system/validate-path`
- `components/CreateJobModal.tsx` — Manual path override: below each FolderPicker, "Or enter path manually" text input (same state as picker) plus hint; backend validation on submit
- `components/EditJobModal.tsx` — Same manual path override for source and destination
- `messages/en.json` and `messages/de.json` — In `folderPicker`: `manualPathLabel`, `manualPathPlaceholder`, `manualPathHint` (EN + DE)

**Verification:** Backend validates paths on create/update; frontend displays API error detail in modal; manual path and browser selection share one value; i18n keys used via `useTranslations("folderPicker")`.

---

### Session: 2026-02-18 — Windows Installer Build Pipeline

**Goal:** Bundle the full application (Python backend + Next.js frontend) into a distributable Windows installer (.exe) using PyInstaller, Next.js standalone mode, portable Node.js, and Inno Setup.

**Backend — Modified:**

- `config.py` — Production data directory support:
  - Added `IS_FROZEN` flag (`sys.frozen` detection for PyInstaller bundles)
  - `_resolve_data_dir()` returns `%LOCALAPPDATA%\Dillo` in production, `backend/` in development
  - `DATA_DIR` module-level constant used for database path and log directory
  - `BASE_DIR` now resolves to `sys.executable` parent when frozen
  - `database_url` default now uses absolute path via `DATA_DIR / 'backups.db'`
  - `cors_origins` expanded to include both `localhost` and `127.0.0.1` on port 3000
  - `app_name` default changed from `"PyBackup Sentinel"` to `"Dillo"`
- `services/activity_logger.py` — Changed `LOG_DIR` from `BASE_DIR / "logs"` to `DATA_DIR / "logs"` so log files persist in user data directory in production

**New Files — Backend:**

- `run_production.py` (project root) — PyInstaller entry point that imports `backend.main.app` and runs it via `uvicorn.run()` on `127.0.0.1:8000`

**Frontend — Modified:**

- `next.config.ts` — Added `output: "standalone"` to enable self-contained production builds (generates `.next/standalone/` with minimal `server.js` + dependencies)
- `lib/api.ts` — API base URL now reads `NEXT_PUBLIC_API_URL` env variable with fallback to `http://localhost:8000`

**New Files — Installer Infrastructure:**

- `installer/launcher.py` — Main application launcher (bundled into `Dillo.exe` via PyInstaller `--onefile`):
  - Resolves install directory from `sys.executable` path
  - Starts backend process (`dillo-backend.exe`) with `CREATE_NO_WINDOW` flag
  - Polls `GET /api/system/health` for backend readiness (30s timeout)
  - Starts frontend process (`node.exe server.js`) with `PORT` and `HOSTNAME` env vars
  - Opens default browser to `http://localhost:3000`
  - Monitors both child processes; exits if either dies
  - `atexit` + signal handlers (`SIGINT`, `SIGTERM`, `SIGBREAK`) ensure clean child process termination
- `installer/build_windows.py` — Full build orchestration script (5 steps):
  1. **Build backend** — Creates/reuses venv, installs deps + PyInstaller, runs PyInstaller with comprehensive `--hidden-import` list (uvicorn internals, aiosqlite, SQLAlchemy SQLite dialect, croniter, all backend modules) and `--collect-submodules` for backend/uvicorn/fastapi/starlette
  2. **Build frontend** — Runs `npm ci` + `npm run build`, copies standalone output + static assets + public directory to dist
  3. **Download Node.js** — Fetches portable `node.exe` from `nodejs.org` (x64 zip), extracts only `node.exe` (no npm/npx needed in production)
  4. **Build launcher** — PyInstaller `--onefile` for `launcher.py` → `Dillo.exe`; optional `--icon` if `dillo.ico` exists
  5. **Compile Inno Setup** — Runs `ISCC.exe` on `dillo.iss` (auto-detects install path, gracefully skips if not installed)
  - CLI args: `--skip-inno`, `--node-version` (default `22.14.0`)
- `installer/dillo.iss` — Inno Setup 6 script:
  - App ID with stable GUID for upgrade detection
  - LZMA2/ultra64 solid compression
  - `{autopf}\Dillo` default install dir, `PrivilegesRequired=lowest`
  - Dual language support (English + German)
  - Optional desktop shortcut task
  - File sections for launcher, backend (recurse), frontend (recurse), Node.js runtime
  - Start menu + desktop icons
  - Post-install launch option
  - Uninstall offers to remove `%LOCALAPPDATA%\Dillo` user data (with confirmation dialog)

**Distribution Structure (after build):**

```
dist/dillo/
├── Dillo.exe                          # Launcher (PyInstaller onefile)
├── backend/
│   └── dillo-backend/
│       ├── dillo-backend.exe          # FastAPI server (PyInstaller onedir)
│       └── _internal/                 # PyInstaller bundled dependencies
├── frontend/
│   ├── server.js                      # Next.js standalone server
│   ├── node_modules/                  # Minimal production deps
│   ├── public/                        # Static assets
│   └── .next/
│       └── static/                    # Built JS/CSS chunks
└── node/
    └── node.exe                       # Portable Node.js runtime
```

**Build command:**

```bash
python installer/build_windows.py          # Full build + installer
python installer/build_windows.py --skip-inno  # Build without Inno Setup
```

---

### Session: 2026-02-16 — Final Immediate Features (Progress, Toasts, Scheduler, Verification)

**Feature 1: Real-time Backup Progress**

**Backend — Modified:**

- `services/backup_engine.py` — Restructured `_incremental_backup` for live progress:
  - Added `_flush_progress()` classmethod that opens a dedicated session and writes intermediate `files_processed`, `files_skipped`, `total_size_mb` to the `JobLog` row
  - Replaced `asyncio.gather` with `asyncio.as_completed` to process file copy results as they finish
  - Progress flushed to DB every 25 files or 3 seconds (whichever comes first)
  - `run_backup` now passes `log_entry.id` to `_incremental_backup` for progress tracking
  - `_FLUSH_EVERY_N = 25` and `_FLUSH_EVERY_S = 3.0` class constants control flush frequency

**Frontend — Modified:**

- `components/JobCard.tsx` — Replaced pulsing placeholder progress bar with live file-count display:
  - When `latest_log.status === "RUNNING"` and counts > 0, shows animated dot + "X files copied · Y skipped · Z MB"
  - Falls back to "Running..." label when no progress data yet
  - Stats row hidden while running (live progress takes over)
  - Uses `jobCard.progress.*` i18n keys with ICU interpolation

**i18n:**

- Added `jobCard.progress` namespace to `en.json` and `de.json`: `filesCopied`, `skipped`, `size` (3 keys each with `{count}` / `{size}` interpolation)

---

**Feature 2: Toast Notifications**

**Frontend — New Component:**

- `components/ToastProvider.tsx` — Context-based toast notification system:
  - `ToastProvider` wraps the app, exposes `addToast(type, message)` via `useToast()` hook
  - Three toast types: `success` (green), `error` (red), `info` (blue) with matching icons and border colors
  - Auto-dismiss after 4 seconds with slide-out exit animation (300ms)
  - Manual dismiss via X button
  - Bottom-right fixed positioning (`z-[100]`), stacks vertically with `flex-col-reverse`
  - Slide-in animation via custom `@keyframes slide-in-right` in `globals.css`

**Frontend — Modified:**

- `app/layout.tsx` — Wrapped `{children}` in `<ToastProvider>` inside `NextIntlClientProvider`
- `app/globals.css` — Added `@keyframes slide-in-right` and `.animate-slide-in-right` class
- `components/JobCard.tsx` — All actions now show toasts:
  - Run Now / Dry Run / Verified Run → success toast with mode label
  - Pause / Resume → success toast
  - Delete → success toast
  - All errors → error toast with generic failure message
- `components/CreateJobModal.tsx` — Shows success toast after job creation
- `components/EditJobModal.tsx` — Shows success toast after job update

**i18n:**

- Added `toast` namespace to `en.json` and `de.json`: `jobCreated`, `jobUpdated`, `jobDeleted`, `jobQueued`, `jobPaused`, `jobResumed`, `actionFailed`, `modeLive`, `modeDryRun`, `modeVerified` (10 keys each with `{name}` / `{mode}` interpolation)

---

**Feature 3: Cron-based Scheduling**

**Backend — New File:**

- `services/scheduler.py` — Asyncio-based cron scheduler:
  - `_scheduler_loop()` runs indefinitely, checking every 60 seconds
  - Queries active jobs with non-null `schedule_cron` from the DB
  - `_should_run_now()` uses `croniter` to determine if the job's cron expression triggered between the last check and now
  - `_is_already_running()` prevents overlapping runs (checks for existing RUNNING log entries)
  - Dispatches `BackupManager.run_backup` via `asyncio.create_task` (non-blocking)
  - Logs each scheduled trigger to the activity log (`EventType.JOB_RUN`)
  - `start_scheduler()` / `stop_scheduler()` are idempotent lifecycle functions
  - `CHECK_INTERVAL_SECONDS = 60` constant controls tick frequency

**Backend — Modified:**

- `main.py` — Imported and wired scheduler into lifespan:
  - `start_scheduler()` called after DB init and activity log cleanup
  - `stop_scheduler()` called on shutdown (after `yield`)
- `requirements.txt` — Added `croniter>=3.0.0` dependency

---

**Feature 4: Post-backup SHA-256 Verification Toggle**

**Backend — Modified:**

- `schemas.py` — Added `verify_after_copy: bool = False` to `RunJobRequest` with description
- `services/backup_engine.py` — Wired `verify_copy()` into the copy flow:
  - `run_backup()` accepts new `verify_after_copy` kwarg, passes it through as `verify`
  - `_incremental_backup()` accepts `verify` param, passes it to `_copy_if_needed()`
  - `_copy_if_needed()` calls `cls.verify_copy(src, dst)` after each successful real copy when `verify=True`; logs SHA-256 mismatch as a warning and adds error to `CopyResult`
  - Method changed from `@staticmethod` to `@classmethod` to call `cls.verify_copy()`
- `routers/jobs.py` — Passes `verify_after_copy=params.verify_after_copy` to `BackupManager.run_backup`

**Frontend — Modified:**

- `lib/types.ts` — Added `verify_after_copy?: boolean` to `RunJobPayload` interface
- `components/JobCard.tsx` — New "Run with Verification" context menu item:
  - `ShieldCheck` icon import from lucide-react
  - Styled in success green (`text-success/80`, `hover:bg-success/10`)
  - Positioned between "Dry Run" and "Estimate Size" in the context menu
  - Calls `handleRun(false, true)` which passes `{ verify_after_copy: true }` to the API
  - Toast shows "verified" mode label

**i18n:**

- Added `jobCard.actions.verifiedRun` in `en.json` and `de.json`: EN "Run with Verification", DE "Mit Verifizierung starten"

---

**Verification:**

- `next build` → Zero TypeScript errors, zero lint warnings
- Routes generated: `/`, `/_not-found`, `/logs`
- No new DB columns added — all features work with existing schema (no migration needed)

---

### Session: 2026-02-15 — Remove Exclusion Patterns Feature

**Reason:** The `exclude_patterns` column was added to the `BackupJob` ORM model but never migrated into the existing SQLite database (project uses `metadata.create_all` which only creates missing tables, not missing columns). This caused `sqlite3.OperationalError: no such column: backup_jobs.exclude_patterns` on every `GET /api/jobs` request. The feature was deemed no longer required and has been fully reverted.

**Backend — Reverted:**

- `models.py` — Removed `exclude_patterns` mapped column from `BackupJob`
- `schemas.py` — Removed `exclude_patterns` from `JobCreate`, `JobUpdate`, `JobResponse`; removed `parse_exclude_patterns` field validator; removed `json` import
- `routers/jobs.py` — Removed `json` import; reverted `create_job` (no longer serialises patterns); reverted `update_job` (no special-case for exclude_patterns)
- `services/backup_engine.py` — Removed `fnmatch` and `json` imports; reverted `run_backup` (no pattern parsing); reverted `estimate_backup` (no pattern parsing); reverted `_incremental_backup` signature (no `exclude_patterns` param); reverted `_scan_source_tree` to original (no `_is_excluded` filtering)

**Frontend — Reverted:**

- `lib/types.ts` — Removed `exclude_patterns` from `BackupJob` and `CreateJobPayload` interfaces
- `components/CreateJobModal.tsx` — Removed `Ban` icon import, `excludeInput` state, pattern parsing, exclusion patterns UI block
- `components/EditJobModal.tsx` — Same removals as CreateJobModal; removed pre-fill from `job.exclude_patterns`

**i18n — Reverted:**

- Removed from `createJob.labels` and `editJob.labels` in both `en.json` and `de.json`: `excludePatterns`, `excludeOptional`, `excludeHint`
- Removed from `createJob.placeholders` and `editJob.placeholders`: `excludePatterns`

**Verification:**

- `next build` → Zero TypeScript errors, zero lint warnings
- Backend model no longer references `exclude_patterns` column → existing SQLite DB works without migration

---

### Session: 2026-02-15 — Medium-Term Features (Timezone, Logs Filters, Estimation)

**Feature 1: Local Time Zone**

- `models.py` — Added `TZDateTime` custom SQLAlchemy `TypeDecorator`:
  - `process_bind_param` ensures timezone-aware UTC on write
  - `process_result_value` attaches `timezone.utc` to naive datetimes on read (fixes SQLite stripping timezone info)
  - Replaced all `DateTime(timezone=True)` usages across `BackupJob`, `ActivityLog`, and `JobLog` with `TZDateTime()`
- `components/JobCard.tsx` — `formatTime()` now detects missing timezone suffix and appends `Z` before parsing; ensures `toLocaleString()` converts UTC→local correctly
- `components/ActivityFeed.tsx` — Added `toSafeDate()` helper that appends `Z` to ISO strings lacking timezone info; used in `useRelativeTime` and inline timestamp display

**Feature 2: Logs Page Enhancements**

**Backend — Modified:**

- `routers/activity.py` — Added filter support:
  - New query params: `job_name` (partial match via `ILIKE`), `event_type` (exact match), `date_from` / `date_to` (ISO date strings, treated as UTC)
  - `_build_activity_filters()` helper applies optional WHERE clauses to both count and data queries
  - New `GET /api/activity-logs/job-names` endpoint returning distinct job names for the filter dropdown

**Frontend — Modified:**

- `lib/api.ts` — `fetchActivityLogs()` now accepts optional `ActivityLogFilters` object; added `fetchActivityJobNames()` function
- `components/ActivityFeed.tsx` — Enhanced:
  - New `filters` prop (type `ActivityLogFilters`) passed through to API calls
  - Expandable error details: click on any log entry with details to expand/collapse; `ChevronDown`/`ChevronUp` icons; expanded view shows full details in a `<pre>` block with `bg-background/60` panel
  - `expandedIds` state (`Set<number>`) tracks which entries are expanded
  - Absolute timestamp shown inline alongside relative time
  - `visibleCount` resets when filters change
- `app/logs/page.tsx` — Full redesign:
  - Filter bar with toggle button showing active filter count badge
  - Four filter controls: Job Name (dropdown from `/job-names`), Event Type (dropdown with translated labels), Date From (date input), Date To (date input)
  - "Clear all" button resets all filters
  - Filters passed to `ActivityFeed` via `filters` prop; updates are live

**i18n:**

- Added 8 keys to `logsPage` namespace in `en.json` and `de.json`: `filters`, `filterTitle`, `clearFilters`, `filterJob`, `filterEvent`, `filterFrom`, `filterTo`, `allJobs`, `allEvents`

~~**Feature 3: Exclusion Patterns** — Removed in a subsequent session (see above). Column was never migrated to the existing SQLite DB.~~

**Feature 3: Backup Size Estimation**

**Backend — New:**

- `schemas.py` — Added `BackupEstimate` Pydantic model: `total_files`, `skipped_files`, `estimated_size_mb`, `estimated_time_seconds` (based on ~50 MB/s), `scan_duration_seconds`
- `services/backup_engine.py` — Added `BackupManager.estimate_backup()` classmethod:
  - Read-only: reuses `_scan_source_tree()` then compares each file pair via stat (mtime + size)
  - Returns dict with file counts, byte totals, and timing
- `routers/jobs.py` — Added `GET /api/jobs/{id}/estimate` endpoint returning `BackupEstimate`

**Frontend — Modified:**

- `lib/types.ts` — Added `BackupEstimate` interface
- `lib/api.ts` — Added `estimateBackup(id)` function
- `components/JobCard.tsx` — Estimate feature:
  - `estimate` / `estimating` state; `handleEstimate()` calls API
  - Context menu: new "Estimate Size" item with `ScanSearch` icon (between Dry Run and Delete)
  - Inline estimate display panel: shows file count, total size (MB/GB), rough time estimate, and up-to-date count; animated scan indicator during estimation

**i18n:**

- Added to `jobCard.actions` in `en.json` and `de.json`: `estimate` (1 key each)
- Added `jobCard.estimate` namespace: `scanning`, `filesToCopy`, `upToDate` (3 keys each)

**Verification:**

- `next build` → Zero TypeScript errors, zero lint warnings
- Routes generated: `/`, `/_not-found`, `/logs`

---

### Session: 2026-02-15 — Pause/Resume Backup Jobs

**Frontend — Modified:**

- `components/StatusBadge.tsx` — Added `PAUSED` status:
  - New `Pause` icon import from lucide-react
  - Type extended from 4 to 5 states: `"RUNNING" | "SUCCESS" | "ERROR" | "IDLE" | "PAUSED"`
  - PAUSED config: `bg-warning/15` background, `text-warning` text, `Pause` icon
- `components/JobCard.tsx` — Pause/Resume toggle:
  - New `Pause`, `CirclePlay` icon imports; `updateJob` API import added
  - `isPaused` derived from `!job.is_active`; status resolves to `"PAUSED"` when inactive, overriding log status
  - `handleTogglePause()` calls `updateJob(job.id, { is_active: !isPaused })` then `onMutate()`
  - Context menu: new Pause/Resume item between Edit and Dry Run; pause shown with warning color, resume with success color
  - Card container gets `opacity-60` when paused (visual dimming)
  - "Run Now" button disabled when paused, label switches to "Paused"
  - Dry Run button also disabled while paused

**i18n:**

- Added to `jobCard.actions` in `en.json` and `de.json`: `paused`, `pauseJob`, `resumeJob` (3 keys each)
- Added `statusBadge.PAUSED` in both locale files: EN "PAUSED", DE "PAUSIERT"

**Verification:**

- `next build` → Zero TypeScript errors, zero lint warnings
- No backend changes required — `JobUpdate.is_active` already supported via `PATCH`

---

### Session: 2026-02-15 — Active Backup Jobs Schedule

**Frontend — Modified:**

- `components/JobCard.tsx` — Schedule display added to each job card:
  - New `describeCron()` helper function that parses a cron expression into a human-readable label (Manual, Hourly at :MM, Daily at HH:MM, Weekly on Day at HH:MM, Monthly on day N at HH:MM)
  - Reuses `schedulePicker.days.*` i18n keys for localized day names
  - Schedule shown inline below the job name with a `Clock` icon, separated from the "Created" timestamp by a dot separator
  - Added `Clock` icon import from lucide-react
- `components/ActivityFeed.tsx` — Reactive refresh on mutations:
  - New `refreshSignal` prop (number, default 0); when incremented by the parent, triggers an immediate `load()` call via a dedicated `useEffect`
  - Background 5-second polling continues alongside for catching async events (e.g. backup completions)
- `app/page.tsx` — Unified mutation handler:
  - New `mutationSignal` state (number counter) and `handleMutation` callback that calls `refresh()` then increments the signal
  - All mutation points now use `handleMutation` instead of raw `refresh`: Refresh button, `JobCard.onMutate`, `CreateJobModal.onCreated`, `EditJobModal.onUpdated`
  - `ActivityFeed` receives `refreshSignal={mutationSignal}` for immediate updates
  - Added `useCallback` import

**i18n:**

- Added `jobCard.schedule` namespace to `en.json` and `de.json` (manual, hourly, daily, weekly, monthly — 5 keys each with ICU interpolation)
- Updated `dashboard.autoRefresh` in both locale files: EN "Live updates", DE "Live-Aktualisierung"

**Verification:**

- `next build` → Zero TypeScript errors, zero lint warnings
- No backend changes required

---

### Session: 2026-02-15 — Activity Log & Logo Improvements

**Frontend — Modified:**

- `components/Sidebar.tsx` — Logo made more prominent:
  - Logo container enlarged from `h-9 w-9` to `h-12 w-12` with `rounded-xl` and a subtle `ring-1 ring-accent/20` border
  - Image increased from 28×28 to 36×36 pixels
  - Brand text bumped from `text-sm` to `text-base`, subtitle from `text-[11px]` to `text-xs`
  - Entire logo block wrapped in a `Link` to `/` (clickable home navigation)
  - Section padding increased (`py-5` → `py-6`, `gap-3` → `gap-4`)
  - **Sidebar navigation now uses real routing:** All nav items converted from `<button>` to `<Link>` with proper `href` paths (`/`, `/drives`, `/logs`, `/settings`)
  - Active state derived from `usePathname()` instead of a hardcoded `active: true` flag; root path uses exact match, others use `startsWith`
- `components/ActivityFeed.tsx` — Made configurable via props:
  - New `ActivityFeedProps` interface: `limit` (default 15), `paginated` (default false), `showTitle` (default true)
  - Dashboard usage: 15 entries, no pagination, with title
  - Logs page usage: 100 entries, paginated, no title (page provides its own header)
  - "Show More" button gated behind `paginated` prop

**Frontend — New Page:**

- `app/logs/page.tsx` — Dedicated activity logs page:
  - Full-page layout with `DashboardLayout` wrapper
  - Page header with `Database` icon, title, and subtitle
  - Renders `ActivityFeed` with `limit={100}`, `paginated`, and `showTitle={false}`
  - Accessible via the "Logs" nav item in the sidebar

**i18n:**

- Added `logsPage` namespace to `en.json` and `de.json` (title + subtitle — 2 keys each)

**Verification:**

- `next build` → Zero TypeScript errors, zero lint warnings
- Routes generated: `/`, `/_not-found`, `/logs`
- No backend changes required

---

### Session: 2026-02-15 — Log Backup Jobs

**Backend — New Files:**

- `services/activity_logger.py` — Activity logging service:
  - `log_activity()` — Records events to both the SQLite `activity_logs` table and physical `.log` files in `backend/logs/`
  - `cleanup_old_activity_logs()` — Deletes DB entries older than 14 days; runs automatically on startup via lifespan hook
  - Physical log files named `YYYY-MM-DD.log`, auto-rotated to keep only the 3 most recent files
  - `EventType` constants: `JOB_CREATED`, `JOB_DELETED`, `JOB_RUN`, `JOB_DRY_RUN`, `JOB_COMPLETED`, `JOB_FAILED`
- `routers/activity.py` — New API endpoints:
  - `GET /api/activity-logs?limit=50&offset=0` — Paginated activity log retrieval (newest first)
  - `DELETE /api/activity-logs/cleanup` — Manual cleanup trigger

**Backend — Modified:**

- `models.py` — Added `ActivityLog` ORM model (id, event_type, job_name, job_id nullable, message, details, timestamp with index)
- `schemas.py` — Added `ActivityLogResponse` and `ActivityLogListResponse` Pydantic v2 schemas
- `routers/jobs.py` — Wired `log_activity()` into `create_job` (JOB_CREATED), `delete_job` (JOB_DELETED), and `run_job` (JOB_RUN / JOB_DRY_RUN)
- `services/backup_engine.py` — Logs `JOB_COMPLETED` or `JOB_FAILED` after backup finishes, including details (file counts, size, duration, error count)
- `main.py` — Registered `activity` router; added startup auto-cleanup of stale activity logs in lifespan hook

**Frontend — New Component:**

- `components/ActivityFeed.tsx` — Activity log feed displayed on the dashboard:
  - Event-type icons with color coding (created=blue, deleted=red, running=white, dry-run=yellow, completed=green, failed=red)
  - Relative timestamps ("just now", "5 min ago", "2h ago", "3d ago")
  - Details row for execution stats (file counts, size, duration)
  - "Show more" pagination (loads 15 entries at a time)
  - Polls every 5 seconds for live updates

**Frontend — Modified:**

- `lib/types.ts` — Added `ActivityLog` and `ActivityLogListResponse` interfaces
- `lib/api.ts` — Added `fetchActivityLogs()` function
- `app/page.tsx` — Imported and rendered `ActivityFeed` below the jobs grid

**i18n:**

- Added `activityFeed` namespace to `en.json` and `de.json` (title, empty state, error, show more, 6 event labels, 4 time-ago formats — 13 keys each)

**Verification:**

- `next build` → Zero TypeScript errors, zero lint warnings
- No breaking changes to existing endpoints or components

---

### Session: 2026-02-15 — Editable Backup Jobs

**Frontend — New Component:**

- `components/EditJobModal.tsx` — Edit modal for existing backup jobs:
  - Accepts a `BackupJob | null` prop; renders when non-null
  - Pre-fills all form fields (name, source path, dest path, schedule) via `useEffect` when the job reference changes
  - Reuses `FolderPicker` and `SchedulePicker` components from the create flow
  - Client-side validation identical to create (name required, paths required, source != dest)
  - Calls `updateJob()` (`PATCH /api/jobs/{id}`) with only the changed fields
  - `Save` icon with "Save Changes" / "Saving..." button text
  - Full error handling (backend validation errors, connectivity errors)

**Frontend — Modified:**

- `components/JobCard.tsx` — Added `Pencil` icon import, new `onEdit` callback prop, and "Edit Job" menu item in the context menu (positioned above "Dry Run")
- `app/page.tsx` — Imported `EditJobModal`, added `editingJob` state (`BackupJob | null`), passes `onEdit={setEditingJob}` to each `JobCard`, renders `EditJobModal` alongside `CreateJobModal`

**i18n:**

- Added `editJob` namespace to `en.json` and `de.json` (title, validation, errors, labels, placeholders, submit — 12 keys each)
- Added `jobCard.actions.editJob` key in both locale files

**Verification:**

- `next build` → Zero TypeScript errors, zero lint warnings
- No backend changes required — existing `PATCH` endpoint and `updateJob` API client were already in place

---

### Session: 2026-02-14 — Rebrand to "Dillo"

**Changes:**

- Copied armadillo logo to `frontend/public/dillo-logo.png`
- Updated `app/layout.tsx` — metadata title changed from "PyBackup Sentinel" to "Dillo"
- Updated `components/Sidebar.tsx` — replaced `Shield` lucide icon with `next/image` rendering of `dillo-logo.png`; applied `invert brightness-200` CSS filter for dark-mode visibility; logo sits in an `bg-accent/10` rounded container
- Updated `messages/en.json` — brand → "Dillo", brandSub → "Backup Manager"
- Updated `messages/de.json` — brand → "Dillo", brandSub → "Backup-Manager"
- Removed unused `Shield` import from Sidebar

**Verification:**

- `next build` → Zero TypeScript errors, zero lint warnings
- Grep for "PyBackup" / "Sentinel" across frontend → zero matches

---

### Session: 2026-02-14 — Create Backup Job UX Redesign

**Backend:**

- Added `DirectoryEntry` and `BrowseResponse` Pydantic schemas to `schemas.py`
- Added `GET /api/system/browse?path=` endpoint to `routers/system.py` — lists subdirectories of a given path; returns drive roots when path is empty; skips hidden/system dirs and unreadable directories

**Frontend — New Components:**

- `components/FolderPicker.tsx` — Inline folder browser with:
  - Text display showing the currently selected path + "Browse" button
  - Expandable browser panel with breadcrumb navigation (clickable segments)
  - Up-arrow to navigate to parent, drive icon to return to roots
  - Drive-level view showing all available drives with HardDrive icons
  - Subdirectory listing with folder icons, click-to-navigate
  - "Select" button at bottom to confirm the current directory
  - Loading spinner, empty-state, and error handling
- `components/SchedulePicker.tsx` — Friendly schedule builder replacing raw cron input:
  - Frequency dropdown: Manual (no schedule), Hourly, Daily, Weekly, Monthly
  - Hourly → minute-of-hour selector (:00, :05, ..., :55)
  - Daily → hour + minute selectors (HH:MM)
  - Weekly → day-of-week dropdown + time selectors
  - Monthly → day-of-month (1–28) + time selectors
  - Bidirectional cron parsing: parses existing cron expressions back into structured UI, builds cron string from selections
  - "Manual" maps to empty string (no schedule_cron)

**Frontend — Refactored:**

- `CreateJobModal.tsx` — Replaced raw Source Path and Destination Path text inputs with `FolderPicker` components; replaced raw cron input with `SchedulePicker`; added `max-h-[90vh] overflow-y-auto` to modal for scroll safety
- `lib/types.ts` — Added `DirectoryEntry` and `BrowseResponse` interfaces
- `lib/api.ts` — Added `browsePath()` function

**i18n:**

- Added `folderPicker` namespace (6 keys: browse, goUp, drives, empty, loadError, selectFolder)
- Added `schedulePicker` namespace (frequency options, time labels, 7 day names)
- Updated `createJob` namespace (added sourcePath/destPath labels, updated placeholders/validation text)
- All keys present in both `en.json` and `de.json`

**Verification:**

- `next build` → Zero TypeScript errors, zero lint warnings

---

### Session: 2026-02-14 — Internationalization (i18n)

**Setup:**

- Installed `next-intl` for App Router (non-routing/cookie-based locale strategy)
- Created `i18n/request.ts` — request config that reads `NEXT_LOCALE` cookie, defaults to `en`
- Updated `next.config.ts` — integrated `createNextIntlPlugin` for automatic message loading
- Updated `app/layout.tsx` — wrapped app in `NextIntlClientProvider` with server-side `getLocale`/`getMessages`

**Translation Files:**

- Created `messages/en.json` — all English UI strings organized by component namespace
- Created `messages/de.json` — complete German translations for all UI strings
- Namespaces: `metadata`, `dashboard`, `sidebar`, `createJob`, `jobCard`, `driveCard`, `statusBadge`, `languageSwitcher`

**Component Refactoring (all hardcoded strings replaced with `useTranslations`):**

- `app/page.tsx` — 14 strings extracted (headings, buttons, stats labels, empty states)
- `components/Sidebar.tsx` — 7 strings (brand, nav items, version); nav items now use translation keys
- `components/CreateJobModal.tsx` — 17 strings (title, labels, placeholders, validation messages, error messages, submit button)
- `components/JobCard.tsx` — 10 strings (delete confirm with interpolated job name, created timestamp, stats labels, action buttons)
- `components/DriveCard.tsx` — 2 strings with ICU interpolation (`{used} GB used of {total} GB`)
- `components/StatusBadge.tsx` — 4 status labels (RUNNING/SUCCESS/ERROR/IDLE translated per locale)

**Language Switcher:**

- Created `components/LanguageSwitcher.tsx` — dropdown with globe icon, sets `NEXT_LOCALE` cookie and triggers `router.refresh()`
- Integrated into `Sidebar.tsx` footer, visible on every page

**Verification:**

- `next build` → Zero TypeScript errors, zero lint warnings
- All 6 components with user-facing text fully i18n-ready

---

### Session: 2026-02-23 — Installer & Asset Preparation

**Current Goal:** Generate production-ready installers for Windows and macOS and prepare required branding assets.

- **New Task:** Convert `dillo-logo.png` into `.ico` (Windows) and `.icns` (macOS) formats to ensure professional branding in the taskbar, desktop, and installer wizards.
- **Requirement:** Windows installer must allow custom install paths (`DisableDirPage=no`).
- **Requirement:** macOS installer must be a `.dmg` containing a signed-ready `.app` bundle.

### Session: 2026-02-13 — Initial Build (Full MVP)

**Backend:**

- Created project scaffolding (`backend/`, `frontend/`, `__init__.py` files, `requirements.txt`)
- Installed all Python dependencies into `backend/venv` (FastAPI, SQLAlchemy, aiosqlite, pydantic-settings, alembic, watchdog, aiofiles)
- Implemented `config.py` — centralized `pydantic-settings` config with `PYBACKUP_` env prefix, protected drives list, concurrency knobs
- Implemented `database.py` — async SQLAlchemy 2.0 engine, `async_session_factory`, `get_db` dependency with auto-commit/rollback, `init_db()` for lifespan table creation
- Implemented `models.py` — `BackupJob` (UUID PK, name, source/dest paths, cron, active flag, timestamps) and `JobLog` (FK, start/end times, status, file/size metrics, error text, dry-run flag) with `selectin` eager loading
- Implemented `schemas.py` — Pydantic v2 schemas: `JobCreate` (with source != dest model validator), `JobUpdate`, `JobResponse`, `JobLogResponse`, `RunJobRequest` (dry_run + force_system_drive), `DriveInfo`, `SystemDrivesResponse`
- Implemented `services/backup_engine.py` — `BackupManager` class with incremental backup (mtime+size), `ThreadPoolExecutor` concurrency, `asyncio.Semaphore`, dry-run mode, Safety Lock, SHA-256 verification
- Implemented `routers/jobs.py` — Full CRUD (`POST`, `GET`, `GET/{id}`, `PATCH/{id}`, `DELETE/{id}`), `POST /{id}/run` (BackgroundTask dispatch), `GET /{id}/logs`
- Implemented `routers/system.py` — `GET /api/system/drives` (A–Z letter scan on Windows), `GET /api/system/health`
- Implemented `main.py` — FastAPI app with CORS for `localhost:3000`, lifespan-based DB init, both routers mounted

**Frontend:**

- Scaffolded Next.js 15 via `create-next-app` (App Router, TypeScript, Tailwind CSS)
- Installed `lucide-react` (icons) and `axios` (HTTP client)
- Implemented `lib/types.ts` — TypeScript interfaces mirroring all backend Pydantic schemas
- Implemented `lib/api.ts` — Typed Axios client with functions for every endpoint
- Implemented `hooks/useBackupJobs.ts` — Polling hook (5s `setInterval`, cleared on unmount)
- Implemented `components/Sidebar.tsx` — Branding, nav items, version footer
- Implemented `components/StatusBadge.tsx` — RUNNING/SUCCESS/ERROR/IDLE badges with icons
- Implemented `components/JobCard.tsx` — Path display with arrows, stats row, Run Now button, context menu (Dry Run, Delete), animated progress bar
- Implemented `components/CreateJobModal.tsx` — Form with client-side source != dest validation, inline backend error display
- Implemented `components/DriveCard.tsx` — Usage bar with green/yellow/red thresholds
- Implemented `components/DashboardLayout.tsx` — Sidebar + scrollable content wrapper
- Implemented `app/page.tsx` — Dashboard with stats row, drive grid, job grid, empty states, create modal
- Configured `globals.css` — Dark-mode-first design system (`--background: #0a0a0a`, `--card: #141414`, `--accent: #3b82f6`), custom scrollbar

**Integration:**

- Created `start-dev.bat` (Windows) and `start-dev.sh` (Unix) launchers
- CORS configured to allow `http://localhost:3000`
- Wrote `README.md` with quickstart, API reference, and project structure

**Verification (all passed):**

- `GET /api/system/health` → `{"status": "ok"}`
- `GET /api/system/drives` → Detected 4 drives (C, D, E, G) with accurate capacity
- `GET /api/jobs` → `{"jobs": [], "total": 0}` on fresh DB
- `POST /api/jobs` → Created test job with UUID, validated source path
- `DELETE /api/jobs/{id}` → 204 No Content, job removed
- `next build` → Zero TypeScript errors, zero lint warnings
- Database auto-created on first startup via lifespan hook

---

## 4. Next Steps

### Immediate (high-value, low-effort)

- [x] **Feature: Robust Path Validation (Network/Cloud Drive Support):** _(completed 2026-02-21)_
  - Backend: `services/path_validator.py` with multi-strategy `verify_directory_access()` (standard → scandir → stat → canary file → drive/UNC probe); `POST /api/system/validate-path`; resilient drive listing and browse; job create/update validate both paths and return specific error messages.
  - Frontend: Manual path override text input below each FolderPicker in CreateJobModal and EditJobModal; `validatePath()` API; i18n for manual path label, placeholder, and hint (EN + DE).
- [x] **Feature: Update Create Backup Job window:** _(completed 2026-02-14)_
  - Replaced Source Path / Destination Path raw text inputs with visual `FolderPicker` (inline directory browser backed by `/api/system/browse`)
  - Replaced Cron Expression input with `SchedulePicker` (frequency dropdown + time/day selectors, auto-converts to cron)
- [x] **Improvement: Update the App name and logo:** _(completed 2026-02-14)_
  - Renamed from "PyBackup Sentinel" to "Dillo"; replaced Shield icon with armadillo logo image
- [x] **Feature: Editable Backup jobs:** _(completed 2026-02-15)_
  - Created `EditJobModal` component pre-filled with job data; added "Edit Job" to `JobCard` context menu; full i18n (EN + DE)
- [x] **Feature: Log Backup Jobs:** _(completed 2026-02-15)_
  - Added `ActivityLog` model + `activity_logger` service (DB + rotating file logs); wired into create, delete, run endpoints + backup engine; `ActivityFeed` component on dashboard with polling, icons, relative time, pagination; 14-day auto-cleanup; 3-file log rotation
- [x] **Improvement: Activity Log and Logo improvements:** _(completed 2026-02-15)_
  - Logo enlarged (12×12 container, 36px image, ring accent border, clickable link to home); brand text bumped to `text-base`
  - Dashboard ActivityFeed limited to 15 most recent entries (no pagination)
  - Dedicated `/logs` page shows 100 most recent entries with "Show More" pagination; accessible from sidebar navigation
  - Sidebar nav items converted from buttons to `Link` elements with real routing + `usePathname` active state
- [x] **Feature: Active Backup Jobs Schedule:** _(completed 2026-02-15)_
  - Each JobCard displays its schedule via `describeCron()` (Manual / Hourly / Daily / Weekly / Monthly with times, localized day names)
  - ActivityFeed refreshes immediately on any mutation via `refreshSignal` prop; dashboard wires all mutation points through a unified `handleMutation` callback
  - Auto-refresh text updated to "Live updates" / "Live-Aktualisierung"
  - Pause/Resume toggle in JobCard context menu; paused jobs show PAUSED badge, dimmed card, disabled Run Now/Dry Run; uses existing `is_active` field via `PATCH`
- [x] **Real-time backup progress:** _(completed 2026-02-16)_
  - Engine flushes `files_processed`, `files_skipped`, `total_size_mb` to the `JobLog` row every 25 files or 3 seconds via `_flush_progress()`. Frontend replaces pulsing bar with live file-count display during RUNNING status.
- [x] **Toast notifications:** _(completed 2026-02-16)_
  - `ToastProvider` context with `useToast()` hook; three types (success/error/info); auto-dismiss 4s; slide-in/out animation; wired into all CRUD, run, pause/resume, and modal actions across `JobCard`, `CreateJobModal`, `EditJobModal`.
- [x] **Cron-based scheduling:** _(completed 2026-02-16)_
  - `services/scheduler.py` with asyncio loop (60s tick) using `croniter` to match cron expressions; prevents overlapping runs; logs scheduled triggers to activity log; started/stopped in FastAPI lifespan.
- [x] **Post-backup SHA-256 verification toggle:** _(completed 2026-02-16)_
  - Added `verify_after_copy` to `RunJobRequest`; `_copy_if_needed()` calls `verify_copy()` after each real copy when enabled; "Run with Verification" context menu item in `JobCard` with `ShieldCheck` icon.
- [x] **Cross-Platform: macOS Support** _(completed 2026-04-07)_
  - `config.py` handles macOS (`~/Library/Application Support/Dillo`) and Linux (`$XDG_DATA_HOME/dillo`); platform-aware `protected_drives`
  - `installer/build_macos.sh` produces a `Dillo.app` bundle; launcher cross-platform
- [x] **Feature: Auto-Start on Boot** _(completed 2026-04-07, UI added 2026-04-08)_
  - `services/autostart.py`: Windows Registry, macOS LaunchAgent plist, Linux XDG desktop entry
  - API: `GET/PUT /api/system/autostart`; frontend API client + i18n (EN + DE)
  - Settings page (`/settings`) with toggle switch, language selector, and about section
- [x] **Installer Refinement (Windows - Inno Setup 6)** _(completed 2026-04-07)_
  - `DisableDirPage=no` enabled; `SetupIconFile=dillo.ico` uncommented; desktop shortcut checked by default with icon
- [x] **Feature: Robust Path Validation (Network/Cloud Drive Enhancement)** _(completed 2026-04-07)_
  - Backup engine runs `verify_directory_access()` canary test on both paths before backup starts
  - FolderPicker: auto-validates empty directories via canary; "Verify access" button; green/red feedback
  - Safety Lock updated for cross-platform (Unix path-prefix matching)

### Medium-term (feature completeness)

- [x] **Job edit modal:** _(completed 2026-02-15 — merged into "Editable Backup jobs" feature)_
- [x] **Feature: Local time zone:** _(completed 2026-02-15)_
  - `TZDateTime` TypeDecorator ensures UTC timezone on SQLite reads; frontend `toSafeDate()` helper + `formatTime()` fix guarantee correct UTC→local conversion
- [x] **Logs page enhancements:** _(completed 2026-02-15)_
  - Filter bar with job name dropdown, event type dropdown, date range pickers; expandable error details with chevron toggle; absolute + relative timestamps; `GET /api/activity-logs/job-names` endpoint
- [x] ~~**Exclusion patterns:**~~ _(implemented 2026-02-15, **removed** 2026-02-15 — caused `OperationalError` on existing DB; feature no longer required)_
- [x] **Backup size estimation:** _(completed 2026-02-15)_
  - `GET /api/jobs/{id}/estimate` endpoint with `BackupManager.estimate_backup()`; inline estimate display in `JobCard` with file count, size, time, and up-to-date count; "Estimate Size" context menu action
- [x] **Run on Windows startup:** _(completed 2026-04-07 — covered by Auto-Start on Boot feature)_
  - Cross-platform autostart via `services/autostart.py` + API toggle
- [x] **Desktop icon:** _(completed 2026-04-07 — covered by Inno Setup refinement)_
  - Desktop shortcut checked by default with `dillo.ico` icon

### Long-term (hardening)

- [ ] **Alembic migrations:** Replace `metadata.create_all` with proper schema versioning.
- [ ] **Error retry logic:** Configurable retry with exponential backoff for transient I/O errors (e.g. file locked).
- [ ] **Bandwidth throttling:** Configurable MB/s cap to avoid saturating the disk.
- [ ] **System tray integration:** Package as standalone executable with tray icon (PyInstaller).
- [ ] **E2E tests:** Playwright for frontend, `pytest` + `httpx.AsyncClient` for backend API.

---

## 5. Known Issues

### Resolved

1. **PowerShell `&&` not supported (2026-02-13)**
   - _Problem:_ Shell command chaining with `&&` failed on Windows PowerShell 5.1 (only supported in PS 7+).
   - _Fix:_ Switched to separate sequential commands or PowerShell-native `;` / `New-Item -Force`.

2. **BackgroundTask session lifetime mismatch (2026-02-13)**
   - _Problem:_ FastAPI `BackgroundTasks` run after the request lifecycle completes, so the request-scoped `get_db` session would already be closed.
   - _Fix:_ `BackupManager.run_backup` creates its own session via `async_session_factory()`, fully decoupling from the request lifecycle.

3. **`create-next-app` interactive prompt blocking automation (2026-02-13)**
   - _Problem:_ `npx create-next-app` hung on "Would you like to use React Compiler?" in non-interactive shell.
   - _Fix:_ Piped `echo "No"` into the command.

4. **Uvicorn module path resolution (2026-02-13)**
   - _Problem:_ `uvicorn backend.main:app` couldn't resolve the `backend` package when run from inside `backend/`.
   - _Fix:_ Launch Uvicorn from the project root or use `--app-dir ..` so `backend` is a proper importable package.

## 6. Release Version

- [x] **Windows Installer:** _(completed 2026-02-18, refined 2026-04-07, **v1.0.3 released 2026-05-10**)_
  - Bundle the app and create an executable format for Windows (.exe)
  - PyInstaller backend + Next.js standalone frontend + portable Node.js + Inno Setup installer
  - Build via `python installer/build_windows.py`; current output: `dist/installer/Dillo-Backup-Setup-1.0.3.exe`
  - Installer filename auto-embeds version via `OutputBaseFilename=Dillo-Backup-Setup-{#MyAppVersion}` in the Inno Setup script
  - User data stored in `%LOCALAPPDATA%\Dillo Backup` (database, logs); clean uninstall with data removal option
  - Dedicated `dillo.ico` for setup wizard, desktop shortcut, and Start Menu; user-selectable install directory
- [x] **Mac Installer:** _(completed 2026-04-07)_
  - Build via `python installer/build_macos.py` or `./installer/build_macos.sh`
  - Output: `dist/Dillo.app` bundle + `dist/installer/Dillo-1.0.0.dmg`
  - DMG includes `/Applications` symlink for drag-to-install
  - `dillo.icns` icon in `Contents/Resources/`; `Info.plist` with bundle metadata
  - User data stored in `~/Library/Application Support/Dillo`
- [ ] **Linux Installer:**
  - Bundle the app and create an executable format for Linux (AppImage / .deb)

  ## 7. Repository & Deployment

### Git Setup (2026-02-23)

- **Status**: Repository initialized and pushed to public remote.
- **Remote URL**: [github.com/BCuracao/dillo](https://github.com/BCuracao/dillo)
- **Branding**: All references updated from `PyBackup Sentinel` / `Stashit` to **Dillo**.
- **Security & Safety**:
  - Comprehensive `.gitignore` implemented to prevent leaking SQLite databases (`*.db`), local logs, `.env` files, and OS-specific build artifacts.
  - Production data is strictly separated from the dev environment (using `%LOCALAPPDATA%/Dillo` on Windows and `~/Library/Application Support/Dillo` on macOS).

### Build Pipeline

- **Windows**: Inno Setup 6 (Output: `DilloSetup.exe`)
- **macOS**: DMG Bundle (Output: `Dillo.dmg`)
- **Assets**:
  - `installer/assets/dillo.ico` (Windows)
  - `installer/assets/dillo.icns` (macOS)

### Known Fixes
- **Console window on launch (2026-04-08):** Launcher was built with `--console`; changed to `--windowed` in both `build_windows.py` and `build_macos.py`. Requires rebuild.
- **Color app icon (2026-04-08):** `convert_icons.py` now sources from `dillo-logo-color.png` (color armadillo) instead of the monochrome `dillo-logo.png`. Sidebar logo remains monochrome. Requires `python installer/convert_icons.py` + rebuild.
- **Safety Lock blocks all macOS/Linux backups (2026-04-08):** `"/"` in `protected_drives` caused `startswith("")` to match every path. Fixed: macOS now protects `["/System", "/usr", "/bin", "/sbin"]`; Linux protects `["/usr", "/bin", "/sbin"]`. Safety Lock comparison also hardened against bare `"/"`.
- **Silent background-task failures (2026-04-08):** Pre-flight errors (path validation, safety lock) raised before `JobLog` creation were swallowed by `BackgroundTasks`. Fixed: wrapped in `try/except` that persists an `ERROR` `JobLog` + activity entry. Requires rebuild.
- **Autostart registered wrong executable (2026-04-08):** Registry pointed at `dillo-backend.exe` because `sys.executable` is the API process. Fixed path resolution to `Dillo.exe` / `Dillo`. Existing installs: correct the `Run` value or disable and re-enable autostart after updating.

### Open

- None at this time.
