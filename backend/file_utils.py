"""
Shared file validation and path helpers for PDFPilot.
"""

import glob
import os
import re
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

PROJECT_ROOT = Path(__file__).resolve().parent.parent
UPLOAD_DIR = PROJECT_ROOT / "uploads"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
LOG_DIR = PROJECT_ROOT / "logs"

UPLOAD_DIR.mkdir(exist_ok=True)
OUTPUT_DIR.mkdir(exist_ok=True)
LOG_DIR.mkdir(exist_ok=True)

MAX_FILE_SIZE = 25 * 1024 * 1024

PDF_EXTENSIONS = {".pdf"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tiff", ".webp"}
TEXT_EXTENSIONS = {".txt"}
DOC_EXTENSIONS = {".docx", ".doc"}
PRESENTATION_EXTENSIONS = {".ppt", ".pptx"}
ARCHIVE_EXTENSIONS = {".zip"}
ALLOWED_EXTENSIONS = PDF_EXTENSIONS | IMAGE_EXTENSIONS | TEXT_EXTENSIONS | DOC_EXTENSIONS | PRESENTATION_EXTENSIONS | ARCHIVE_EXTENSIONS
EXTRACTABLE_EXTENSIONS = PDF_EXTENSIONS | IMAGE_EXTENSIONS | TEXT_EXTENSIONS | {".docx"}


def sanitize_filename(filename: str) -> str:
    """Strip path components and unsafe characters from a user-provided filename."""
    safe_name = Path(filename or "").name
    safe_name = re.sub(r"[^A-Za-z0-9._ -]+", "_", safe_name)
    return safe_name or f"upload_{uuid.uuid4().hex}"


def validate_upload(file: UploadFile, allowed_extensions: set[str] | None = None) -> str:
    """Validate file extension and size, then return the extension."""
    ext = Path(file.filename or "").suffix.lower()
    permitted = allowed_extensions or ALLOWED_EXTENSIONS

    if not ext:
        raise HTTPException(status_code=400, detail="Uploaded file must include an extension")
    if ext not in permitted:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    file.file.seek(0, os.SEEK_END)
    size = file.file.tell()
    file.file.seek(0)
    if size > MAX_FILE_SIZE:
        size_mb = size / (1024 * 1024)
        max_mb = MAX_FILE_SIZE / (1024 * 1024)
        raise HTTPException(
            status_code=400,
            detail=f"File too large: {size_mb:.1f}MB (max {max_mb:.0f}MB)",
        )

    return ext


def save_upload(file: UploadFile, allowed_extensions: set[str] | None = None) -> Path:
    """Persist an uploaded file to uploads/ with a server-safe unique name."""
    ext = validate_upload(file, allowed_extensions=allowed_extensions)
    safe_name = sanitize_filename(file.filename or f"upload{ext}")
    unique_name = f"{Path(safe_name).stem}_{uuid.uuid4().hex}{ext}"
    output_path = UPLOAD_DIR / unique_name

    with output_path.open("wb") as handle:
        handle.write(file.file.read())

    return output_path


def resolve_existing_file(filename: str) -> Path | None:
    """Find an existing file in outputs/uploads using an exact or basename match."""
    candidates = [
        OUTPUT_DIR / filename,
        UPLOAD_DIR / filename,
        OUTPUT_DIR / Path(filename).name,
        UPLOAD_DIR / Path(filename).name,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    ext = Path(filename).suffix
    if ext:
        matches = [
            Path(match)
            for match in glob.glob(str(UPLOAD_DIR / f"*{ext}"))
            if Path(match).is_file()
        ]
        if matches:
            return sorted(matches, key=lambda path: path.stat().st_mtime, reverse=True)[0]

    return None


def resolve_existing_files(filenames: list[str]) -> list[Path]:
    """Resolve a list of filenames to existing uploads/outputs."""
    resolved: list[Path] = []
    for name in filenames:
        path = resolve_existing_file(name)
        if not path:
            raise HTTPException(status_code=404, detail=f"File not found on server: {name}")
        resolved.append(path)
    return resolved
