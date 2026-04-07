"""Production entry point — runs the FastAPI backend via uvicorn.

Used by PyInstaller to create the standalone backend executable.
"""

import uvicorn

from backend.main import app

if __name__ == "__main__":
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=8000,
        log_level="info",
        workers=1,
    )
