"""
PDF compression helpers.
"""

import logging
import uuid
from pathlib import Path

from PyPDF2 import PdfReader, PdfWriter

from backend.file_utils import OUTPUT_DIR

logger = logging.getLogger(__name__)


def compress_pdf(input_path: str) -> str:
    """
    Compress a PDF by rewriting it with compressed page streams.
    """
    source = Path(input_path)
    output_path = OUTPUT_DIR / f"compressed_{uuid.uuid4().hex[:8]}.pdf"

    logger.info("Compressing PDF: %s", source)

    reader = PdfReader(source)
    writer = PdfWriter()

    for page in reader.pages:
        page.compress_content_streams()
        writer.add_page(page)

    if reader.metadata:
        writer.add_metadata(reader.metadata)

    with output_path.open("wb") as handle:
        writer.write(handle)

    original_size = source.stat().st_size
    compressed_size = output_path.stat().st_size
    reduction = round((1 - compressed_size / original_size) * 100, 1) if original_size else 0

    logger.info(
        "Compression complete: %s -> %s bytes (%s%% reduction)",
        original_size,
        compressed_size,
        reduction,
    )
    return str(output_path)
