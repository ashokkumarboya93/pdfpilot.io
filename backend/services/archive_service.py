"""
ZIP archive helpers for PDFPilot.
"""

from __future__ import annotations

import logging
import uuid
import zipfile
from pathlib import Path

from backend.file_utils import MAX_FILE_SIZE, OUTPUT_DIR, sanitize_filename

logger = logging.getLogger(__name__)

MAX_ARCHIVE_MEMBERS = 100
MAX_ARCHIVE_TOTAL_SIZE = 100 * 1024 * 1024


def archive_files(input_paths: list[str]) -> str:
    """Bundle one or more files into a ZIP archive."""
    sources = [Path(path) for path in input_paths]
    if not sources:
        raise ValueError("At least one file is required to create a ZIP archive")

    output_path = OUTPUT_DIR / f"archive_{uuid.uuid4().hex[:8]}.zip"
    logger.info("Creating ZIP archive: %s", output_path.name)

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source in sources:
            if not source.exists() or not source.is_file():
                raise ValueError(f"File not found: {source.name}")
            archive.write(source, arcname=sanitize_filename(source.name))

    return str(output_path)


def extract_archive(input_path: str) -> list[str]:
    """Extract a ZIP archive into outputs/ using flattened, sanitized filenames."""
    source = Path(input_path)
    if source.suffix.lower() != ".zip":
        raise ValueError("Only ZIP archives can be extracted")

    logger.info("Extracting ZIP archive: %s", source.name)

    extracted_paths: list[str] = []
    total_uncompressed = 0

    with zipfile.ZipFile(source) as archive:
        members = [member for member in archive.infolist() if not member.is_dir()]
        if not members:
            raise ValueError("The ZIP archive does not contain any files")
        if len(members) > MAX_ARCHIVE_MEMBERS:
            raise ValueError(f"ZIP archive contains too many files (max {MAX_ARCHIVE_MEMBERS})")

        for member in members:
            total_uncompressed += member.file_size
            if member.file_size > MAX_FILE_SIZE:
                raise ValueError(f'Archive member "{member.filename}" exceeds the 25MB per-file limit')
            if total_uncompressed > MAX_ARCHIVE_TOTAL_SIZE:
                raise ValueError("ZIP archive expands beyond the allowed extraction size")

            member_name = sanitize_filename(Path(member.filename).name)
            if not member_name:
                continue

            output_name = f"{Path(member_name).stem}_{uuid.uuid4().hex[:8]}{Path(member_name).suffix.lower()}"
            output_path = OUTPUT_DIR / output_name

            with archive.open(member) as src, output_path.open("wb") as dst:
                dst.write(src.read())

            extracted_paths.append(str(output_path))

    if not extracted_paths:
        raise ValueError("The ZIP archive did not contain extractable files")

    return extracted_paths
