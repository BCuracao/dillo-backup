# Dillo Backup

A robust local backup management web application built with **FastAPI** (Python) and **Next.js 15** (TypeScript). Schedule and customize local data backups via a modern dark-mode browser interface.

![Python](https://img.shields.io/badge/Python-3.12+-blue?logo=python&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-15-black?logo=next.js&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-via%20aiosqlite-003B57?logo=sqlite&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

---

## Features

- **Incremental Backups** — Only copies files that are new or modified (mtime + size comparison)
- **Dry Run Mode** — Preview exactly what would be copied without moving any bytes
- **SHA-256 Verification** — Optional integrity check after each file is copied
- **Cron Scheduling** — Schedule jobs hourly, daily, weekly, or monthly via a friendly UI picker
- **Safety Lock** — Prevents accidental writes to the system/OS drive (configurable per platform)
- **Live Dashboard** — Auto-refreshing UI with status badges, real-time progress, and drive monitoring
- **Activity Logging** — Full event history with filterable logs (by job, event type, date range)
- **Toast Notifications** — Non-blocking feedback for all actions
- **Pause / Resume** — Temporarily disable jobs without deleting them
- **Size Estimation** — Preview how many files and bytes a backup would process before running
- **Auto-Start on Boot** — Cross-platform (Windows Registry, macOS LaunchAgent, Linux XDG)
- **i18n** — Full English and German translations (cookie-based locale via `next-intl`)

## Tech Stack

| Layer    | Technology                                   |
| -------- | -------------------------------------------- |
| Backend  | Python 3.12+, FastAPI, SQLAlchemy 2.0        |
| Frontend | Next.js 15 (App Router), Tailwind CSS, TS    |
| Database | SQLite (via aiosqlite)                        |
| i18n     | next-intl (cookie-based, non-routing)         |
| Icons    | Lucide React                                  |

## Quick Start

### Prerequisites

- **Python 3.12+** with `pip`
- **Node.js 18+** with `npm`

### 1. Install Backend

```bash
cd backend
python -m venv venv

# Windows
venv\Scripts\pip install -r requirements.txt

# macOS / Linux
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Install Frontend

```bash
cd frontend
npm install
```

### 3. Launch Both Servers

**Windows:**
```bash
start-dev.bat
```

**macOS / Linux:**
```bash
chmod +x start-dev.sh
./start-dev.sh
```

Or start them separately:

```bash
# Terminal 1 — Backend (from project root)
cd backend
venv\Scripts\python -m uvicorn backend.main:app --reload --port 8000 --app-dir ..

# Terminal 2 — Frontend
cd frontend
npm run dev
```

### 4. Open the App

- **Dashboard:** [http://localhost:3000](http://localhost:3000)
- **API Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)

## Production Build / Installation

### Windows Installer

Build command:

```bash
python installer/build_windows.py              # Full build + Inno Setup installer
python installer/build_windows.py --skip-inno  # Build without installer
```

Output: `dist/installer/Dillo-Backup-Setup-1.0.0.exe`

**Installing:** Double-click `Dillo-Backup-Setup-1.0.0.exe`. The app installs by default to `C:\Program Files\Dillo Backup` and registers under "Add/Remove Programs" as **Dillo Backup**. User data is stored in `%LOCALAPPDATA%\DilloBackup`.

### macOS DMG

Build command (run on a Mac):

```bash
python installer/build_macos.py         # Full build + DMG
./installer/build_macos.sh              # Shell script alternative
```

Output: `dist/installer/Dillo-Backup-1.0.0.dmg` (mounts as **Dillo Backup**)

**Installing:** Double-click the DMG and drag **Dillo Backup.app** into `/Applications`. User data is stored in `~/Library/Application Support/Dillo Backup`.

## API Endpoints

| Method   | Endpoint                         | Description                        |
| -------- | -------------------------------- | ---------------------------------- |
| `POST`   | `/api/jobs`                      | Create a new backup job            |
| `GET`    | `/api/jobs`                      | List all jobs with latest status   |
| `GET`    | `/api/jobs/{id}`                 | Get a single job                   |
| `PATCH`  | `/api/jobs/{id}`                 | Update a job                       |
| `DELETE` | `/api/jobs/{id}`                 | Delete a job                       |
| `POST`   | `/api/jobs/{id}/run`             | Trigger immediate backup           |
| `GET`    | `/api/jobs/{id}/logs`            | Get execution logs for a job       |
| `GET`    | `/api/jobs/{id}/estimate`        | Estimate backup size               |
| `GET`    | `/api/activity-logs`             | Paginated activity logs            |
| `GET`    | `/api/system/drives`             | List available drives/volumes      |
| `GET`    | `/api/system/browse?path=`       | Browse directory contents          |
| `POST`   | `/api/system/validate-path`      | Validate path accessibility        |
| `GET`    | `/api/system/autostart`          | Get auto-start status              |
| `PUT`    | `/api/system/autostart`          | Enable/disable auto-start          |
| `GET`    | `/api/system/health`             | Health check                       |

## Project Structure

```
dillo-backup/
├── backend/
│   ├── config.py                # pydantic-settings, Safety Lock config
│   ├── database.py              # Async SQLAlchemy engine + session
│   ├── main.py                  # FastAPI app, CORS, lifespan
│   ├── models.py                # BackupJob + JobLog + ActivityLog ORM models
│   ├── schemas.py               # Pydantic v2 request/response schemas
│   ├── requirements.txt
│   ├── routers/
│   │   ├── activity.py          # Activity log retrieval + cleanup
│   │   ├── jobs.py              # Job CRUD + run trigger + logs
│   │   └── system.py            # Drive listing, browse, health, autostart
│   └── services/
│       ├── activity_logger.py   # Activity logging (DB + file + rotation)
│       ├── autostart.py         # Cross-platform auto-start management
│       ├── backup_engine.py     # Incremental backup logic
│       ├── path_validator.py    # Multi-strategy dir access verification
│       └── scheduler.py         # Cron-based backup scheduler
├── frontend/
│   ├── app/                     # Next.js App Router pages
│   ├── components/              # React components (JobCard, Sidebar, etc.)
│   ├── hooks/                   # Custom React hooks
│   ├── i18n/                    # next-intl configuration
│   ├── messages/                # en.json + de.json translations
│   └── lib/                     # API client + TypeScript types
├── installer/
│   ├── build_windows.py         # Windows build orchestration
│   ├── build_macos.py           # macOS build + DMG packaging
│   ├── launcher.py              # App launcher (→ DilloBackup.exe / DilloBackup)
│   ├── dillo-backup.iss         # Inno Setup installer script
│   └── convert_icons.py         # PNG → ICO/ICNS converter
├── run_production.py            # Backend PyInstaller entry point
├── start-dev.bat                # Windows dev launcher
├── start-dev.sh                 # Unix dev launcher
├── PROJECT_JOURNAL.md           # Development journal / long-term memory
└── README.md
```

## License

MIT
