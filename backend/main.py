"""
PDFPilot - FastAPI backend entry point.
"""

import asyncio
import logging
import sys
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from backend.file_utils import LOG_DIR, OUTPUT_DIR, PROJECT_ROOT, UPLOAD_DIR

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.routes import router


LOG_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "app.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


app = FastAPI(
    title="PDFPilot API",
    description="AI-powered document automation for convert, merge, split, compress, and extract tasks.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/css", StaticFiles(directory=PROJECT_ROOT / "css"), name="css")
app.mount("/js", StaticFiles(directory=PROJECT_ROOT / "js"), name="js")
app.mount("/assets", StaticFiles(directory=PROJECT_ROOT / "assets"), name="assets")
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")
app.mount("/outputs", StaticFiles(directory=OUTPUT_DIR), name="outputs")

app.include_router(router, prefix="/api")
app.mount("/", StaticFiles(directory=PROJECT_ROOT, html=True), name="root")


async def cleanup_old_files() -> None:
    """Delete uploads and outputs older than 24 hours."""
    while True:
        try:
            cutoff = time.time() - (24 * 3600)
            for folder in (UPLOAD_DIR, OUTPUT_DIR):
                for filepath in folder.iterdir():
                    if filepath.is_file() and not filepath.name.startswith("."):
                        if filepath.stat().st_mtime < cutoff:
                            filepath.unlink()
                            logger.info("Cleaned up old file: %s", filepath)
        except Exception as exc:
            logger.error("Cleanup task error: %s", exc)

        await asyncio.sleep(3600)


@app.on_event("startup")
async def startup_event() -> None:
    asyncio.create_task(cleanup_old_files())


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
