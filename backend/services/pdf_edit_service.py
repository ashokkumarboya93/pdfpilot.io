"""
PDF editing helpers.
"""

from __future__ import annotations

import io
import logging
import uuid
from pathlib import Path

from PyPDF2 import PdfReader, PdfWriter
from reportlab.lib.colors import Color
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from backend.services.split_service import parse_page_ranges

logger = logging.getLogger(__name__)

OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "outputs"
OUTPUT_DIR.mkdir(exist_ok=True)


def rotate_pdf(input_path: str, rotation: int = 90) -> str:
    """
    Rotate every page in a PDF by the provided angle.
    """
    source = Path(input_path)
    reader = PdfReader(source)
    writer = PdfWriter()

    for page in reader.pages:
        page.rotate(rotation)
        writer.add_page(page)

    output_path = OUTPUT_DIR / f"rotated_{uuid.uuid4().hex[:8]}.pdf"
    with output_path.open("wb") as handle:
        writer.write(handle)

    logger.info("Rotated PDF by %s degrees: %s", rotation, output_path)
    return str(output_path)


def remove_pages(input_path: str, pages: str) -> str:
    """
    Remove selected pages from a PDF.
    """
    source = Path(input_path)
    reader = PdfReader(source)
    writer = PdfWriter()
    total_pages = len(reader.pages)
    pages_to_remove = set(parse_page_ranges(pages, total_pages))

    if not pages_to_remove:
        raise ValueError("No valid pages were selected for removal")

    for index, page in enumerate(reader.pages):
        if index not in pages_to_remove:
            writer.add_page(page)

    output_path = OUTPUT_DIR / f"pages_removed_{uuid.uuid4().hex[:8]}.pdf"
    with output_path.open("wb") as handle:
        writer.write(handle)

    logger.info("Removed pages %s from %s", sorted(pages_to_remove), source)
    return str(output_path)


def add_watermark(input_path: str, watermark_text: str) -> str:
    """
    Add a diagonal text watermark to every page in a PDF.
    """
    source = Path(input_path)
    reader = PdfReader(source)
    writer = PdfWriter()

    for page in reader.pages:
        watermark_pdf = _create_watermark_page(
            watermark_text=watermark_text,
            width=float(page.mediabox.width),
            height=float(page.mediabox.height),
        )
        watermark_reader = PdfReader(watermark_pdf)
        page.merge_page(watermark_reader.pages[0])
        writer.add_page(page)

    output_path = OUTPUT_DIR / f"watermarked_{uuid.uuid4().hex[:8]}.pdf"
    with output_path.open("wb") as handle:
        writer.write(handle)

    logger.info("Added watermark to %s", source)
    return str(output_path)


def _create_watermark_page(watermark_text: str, width: float, height: float) -> io.BytesIO:
    buffer = io.BytesIO()
    pdf_canvas = canvas.Canvas(buffer, pagesize=(width, height))
    pdf_canvas.saveState()
    pdf_canvas.translate(width / 2, height / 2)
    pdf_canvas.rotate(35)
    pdf_canvas.setFillColor(Color(0.4, 0.4, 0.4, alpha=0.2))
    pdf_canvas.setFont("Helvetica-Bold", 36)
    pdf_canvas.drawCentredString(0, 0, watermark_text)
    pdf_canvas.restoreState()
    pdf_canvas.save()
    buffer.seek(0)
    return buffer
